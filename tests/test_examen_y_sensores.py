"""Contrato de sensores con SDK y audio simulados; nunca contacta con un NAO real."""
import base64
import contextlib
import copy
import io
import json
from pathlib import Path
import socket
import struct
import tempfile
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from iniciar_examen import cargar_config, argumentos, main as iniciar_examen
from probar_choregraphe import main as probar_choregraphe
from sensores_nao import BufferAudio, CamaraNAO, PeticionSensores, ServidorSensores, SensoresNAO
from sensores_cliente import ClienteSensores, ErrorSensores, FlujoPCM, fuente_audio_nao
from sensores_cliente import CamaraConRespaldo
import iniciar_examen as modulo_examen
import vision_ia
try:
    import speech_recognition as sr_real
except ImportError:
    sr_real = None


class VideoFalso:
    def __init__(self):
        self.numero = 0
        self.cerrado = False
        self.liberadas = 0
        self.incompleta = False

    def subscribeCamera(self, nombre, indice, resolucion, color, fps):
        assert (indice, resolucion, color, fps) == (0, 1, 13, 15)
        return 'CAMARA_FALSA'

    def getImageRemote(self, handle):
        self.numero += 1
        datos = b'\x10\x20\x30' * 4 if not self.incompleta else b'error'
        return [2, 2, 3, 13, 100, self.numero, datos]

    def releaseImage(self, handle):
        self.liberadas += 1

    def unsubscribe(self, handle):
        self.cerrado = True


class PruebasBufferYCamaras(unittest.TestCase):
    @unittest.skipUnless(sr_real, 'Se ejecuta al instalar requirements_examen.txt; no usa internet ni microfonos reales.')
    def test_fuente_nao_con_speechrecognition_real_y_pcm_sintetico(self):
        class AudioSintetico:
            numero = 1
            def estado(self):
                return {'microfono': {'paquetes': self.numero, 'error': '',
                                     'sample_rate': 16000, 'sample_width': 2, 'canales': 1}}
            def json(self, ruta):
                self.numero += 1
                valor = 2000 if 5 <= self.numero <= 14 else 0
                datos = struct.pack('<1024h', *([valor] * 1024))
                return {'secuencia': self.numero, 'discontinuidad': False,
                        'pcm': base64.b64encode(datos).decode('ascii')}
        reconocedor = sr_real.Recognizer()
        reconocedor.energy_threshold = 100
        reconocedor.dynamic_energy_threshold = False
        reconocedor.pause_threshold = .3
        reconocedor.non_speaking_duration = .2
        with fuente_audio_nao(sr_real, AudioSintetico()) as fuente:
            audio = reconocedor.listen(fuente, timeout=2, phrase_time_limit=2)
        self.assertEqual((audio.sample_rate, audio.sample_width), (16000, 2))
        self.assertGreater(len(audio.frame_data), 0)

    def test_camara_valida_datos_bgr_y_libera_el_buffer(self):
        video = VideoFalso()
        camara = CamaraNAO(video)
        imagen, ancho, alto, marca = camara.frame()
        self.assertEqual((len(imagen), ancho, alto), (12, 2, 2))
        self.assertEqual(marca, '100:1')
        video.incompleta = True
        with self.assertRaises(RuntimeError):
            camara.frame()
        self.assertEqual(video.liberadas, 2)
        camara.cerrar()
        self.assertTrue(video.cerrado)

    def test_pcm_mono_continuidad_y_desbordamiento(self):
        audio = BufferAudio()
        pcm = struct.pack('<4h', 100, -100, 100, -100)
        audio.recibir(1, 4, pcm)
        self.assertEqual(audio.estado()['rms'], 100)
        r = audio.desde(0)
        self.assertEqual(base64.b64decode(r['pcm']), pcm)
        self.assertFalse(r['discontinuidad'])
        for _ in range(85):
            audio.recibir(1, 4, pcm)
        self.assertTrue(audio.desde(0)['discontinuidad'])

    def test_audio_con_formato_incorrecto_no_pasa_como_valido(self):
        audio = BufferAudio()
        audio.recibir(4, 10, b'\0' * 80)
        self.assertEqual(audio.secuencia, 0)
        with self.assertRaises(RuntimeError):
            audio.desde(0)


class PruebasHTTP(unittest.TestCase):
    def setUp(self):
        self.video = VideoFalso()
        self.sensores = SensoresNAO()
        self.sensores.version = 'VERSION_SDK_SIMULADA'
        self.sensores.camara = CamaraNAO(self.video)
        self.sensores.audio = BufferAudio()
        self.sensores.audio.recibir(1, 1024, b'\0' * 2048)
        self.server = ServidorSensores(('127.0.0.1', 0), PeticionSensores)
        self.server.token = 'SESION_DE_TEST'
        self.server.sensores = self.sensores
        self.hilo = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        self.hilo.start()
        self.cliente = ClienteSensores(self.server.server_port, self.server.token)

    def tearDown(self):
        if self.hilo.is_alive():
            self.server.shutdown()
        self.hilo.join(1)
        self.server.server_close()
        self.sensores.cerrar()

    def test_transporte_http_real_de_imagen_sin_repetir_marcas(self):
        a = self.cliente.frame()
        b = self.cliente.frame()
        self.assertEqual(a[0], b'\x10\x20\x30' * 4)
        self.assertNotEqual(a[3], b[3])
        self.assertEqual(self.cliente.estado()['version_naoqi'], 'VERSION_SDK_SIMULADA')

    def test_una_sesion_equivocada_no_lee_sensores(self):
        otro = ClienteSensores(self.server.server_port, 'OTRA_SESION')
        with self.assertRaisesRegex(ErrorSensores, '403'):
            otro.estado()

    def test_stream_pcm_descarta_audio_anterior_al_turno(self):
        flujo = FlujoPCM(self.cliente)
        pcm = struct.pack('<4h', 1, -2, 3, -4)
        self.sensores.audio.recibir(1, 4, pcm)
        self.assertEqual(flujo.read(4), pcm)
        self.sensores.audio.recibir(1, 4, b'\0' * 8)
        flujo.descartar()
        self.sensores.audio.recibir(1, 4, pcm)
        self.assertEqual(flujo.read(4), pcm)
        flujo.close()
        with self.assertRaises(ErrorSensores):
            flujo.read(4)

    def test_cierre_http_permite_liberar_la_suscripcion(self):
        self.cliente.cerrar()
        self.hilo.join(1)
        self.assertFalse(self.hilo.is_alive())


class PruebasPerfilExamen(unittest.TestCase):
    def test_configuracion_apunta_a_nao9559_y_no_inventa_ip(self):
        perfil = cargar_config()
        self.assertEqual(perfil['robot_port'], 9559)
        self.assertEqual((perfil['camara'], perfil['microfono'], perfil['voz']), ('nao', 'nao', 'nao_tts'))
        self.assertIsNone(perfil['robot_ip'])
        with self.assertRaises(ValueError):
            argumentos(perfil)
        perfil['robot_ip'] = '192.168.0.20'
        args = argumentos(perfil)
        self.assertIn('--camara-nao', args)
        self.assertIn('--microfono-nao', args)
        self.assertIn('--saludo-ia', args)
        self.assertNotIn('--movimientos', args)

    def test_arranque_y_diagnostico_no_cambian_las_fuentes(self):
        with patch('iniciar_examen.iniciar_prueba', return_value=0) as iniciar:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(iniciar_examen(['--ip', '192.168.0.20', '--diagnostico']), 0)
        args = iniciar.call_args.args[0]
        self.assertIn('--solo-diagnostico', args)
        self.assertIn('--microfono-nao', args)
        self.assertIn('--camara-nao', args)

    def test_fuentes_pc_solo_si_se_configuran_expresamente(self):
        p = cargar_config()
        p.update(robot_ip='192.168.0.20', camara='pc', microfono='no')
        args = argumentos(p, sin_ia=True)
        self.assertNotIn('--camara-nao', args)
        self.assertNotIn('--microfono-nao', args)
        self.assertNotIn('--saludo-ia', args)
        self.assertIn('--sin-ia', args)


class PruebasSDKSimulado(unittest.TestCase):
    def test_registro_del_callback_y_cierre_del_broker(self):
        video = VideoFalso()
        log = []

        class ModuloFalso:
            def __init__(self, nombre):
                self.nombre = nombre

        class AudioFalso:
            def setClientPreferences(self, nombre, frecuencia, canal, deinterleaved):
                self.nombre = nombre
                assert (frecuencia, canal, deinterleaved) == (16000, 3, 0)
            def subscribe(self, nombre):
                receptor = getattr(sys.modules['__main__'], nombre)
                receptor.processRemote(1, 4, [0, 0], struct.pack('<4h', 1, 2, 3, 4))
            def unsubscribe(self, nombre):
                log.append('audio_cerrado')

        audio = AudioFalso()
        broker = SimpleNamespace(shutdown=lambda: log.append('broker_cerrado'))
        def proxy(nombre, ip, port):
            return {'ALSystem': SimpleNamespace(systemVersion=lambda: '2.8.SIMULADO'),
                    'ALVideoDevice': video, 'ALAudioDevice': audio}[nombre]
        sdk = SimpleNamespace(ALProxy=proxy, ALBroker=lambda *args: broker, ALModule=ModuloFalso)
        sensores = SensoresNAO()
        with patch.dict(sys.modules, {'naoqi': sdk}):
            sensores.abrir('127.0.0.1', 9559, callback_ip='127.0.0.1')
        nombre = sensores.nombre_audio
        self.assertEqual(sensores.estado()['microfono']['paquetes'], 1)
        self.assertTrue(hasattr(sys.modules['__main__'], nombre))
        sensores.cerrar()
        self.assertFalse(hasattr(sys.modules['__main__'], nombre))
        self.assertEqual(log, ['audio_cerrado', 'broker_cerrado'])
        self.assertTrue(video.cerrado)

    def test_salida_silenciada_no_se_da_por_lista(self):
        sdk = SimpleNamespace(ALProxy=lambda modulo, *args:
            SimpleNamespace(systemVersion=lambda: 'SIMULADA') if modulo == 'ALSystem' else
            SimpleNamespace(getOutputVolume=lambda: 0, isAudioOutMuted=lambda: True))
        sensores = SensoresNAO()
        with patch.dict(sys.modules, {'naoqi': sdk}):
            with self.assertRaisesRegex(RuntimeError, 'volumen cero'):
                sensores.abrir('127.0.0.1', 9559, camara=False, microfono=False)
        sensores.cerrar()


SDK_DE_PROCESO = '''import json, os, struct, sys
def log(valor):
    with open(os.environ['NEO_SDK_TEST_LOG'], 'a') as f:
        f.write(json.dumps(valor) + '\\n')
class ALModule(object):
    def __init__(self, nombre): self.nombre = nombre
class ALBroker(object):
    def __init__(self, *args): pass
    def shutdown(self): log('broker_cerrado')
class Proxy(object):
    def __init__(self, modulo): self.modulo=modulo; self.frame=0
    def setLanguage(self, idioma): pass
    def say(self, texto): log('voz_solicitada')
    def getOutputVolume(self): return 60
    def isAudioOutMuted(self): return False
    def systemVersion(self): return 'SDK_SIMULADO'
    def subscribeCamera(self, *args): return 'CAM_TEST'
    def getImageRemote(self, handle):
        self.frame += 1
        return [2,2,3,13,100,self.frame,b'\\0'*12]
    def releaseImage(self, handle): pass
    def setClientPreferences(self, nombre, *args): self.nombre=nombre
    def subscribe(self, nombre):
        getattr(sys.modules['__main__'], nombre).processRemote(1,4,[0,0],struct.pack('<4h',1,2,3,4))
    def unsubscribe(self, nombre): log(self.modulo + '_cerrado')
def ALProxy(modulo, ip, port):
    log(modulo)
    return Proxy(modulo)
'''


class PruebaDiagnosticoEnProcesos(unittest.TestCase):
    def test_diagnostico_arranca_sensores_y_los_libera_sin_juego_ni_movimientos(self):
        puertos = []
        sockets = []
        for _ in range(3):
            s = socket.socket()
            s.bind(('127.0.0.1', 0))
            sockets.append(s)
            puertos.append(s.getsockname()[1])
        for s in sockets:
            s.close()
        with tempfile.TemporaryDirectory() as t:
            raiz = Path(t)
            (raiz/'naoqi.py').write_text(SDK_DE_PROCESO, encoding='utf-8')
            log = raiz/'llamadas.jsonl'
            import os
            entorno = {'PYTHONPATH': str(raiz), 'NEO_SDK_TEST_LOG': str(log)}
            with patch.dict(os.environ, entorno), patch('probar_choregraphe.subprocess.call') as cliente:
                resultado = probar_choregraphe([
                    '--robot-ip', '127.0.0.1', '--robot-port', '9559', '--python-naoqi', sys.executable,
                    '--puerto', str(puertos[0]), '--puerto-sensores', str(puertos[1]),
                    '--callback-port', str(puertos[2]), '--camara-nao', '--microfono-nao',
                    '--solo-diagnostico', '--movimientos'])
            self.assertEqual(resultado, 0)
            cliente.assert_not_called()
            llamadas = [json.loads(x) for x in log.read_text().splitlines()]
            self.assertIn('ALVideoDevice_cerrado', llamadas)
            self.assertIn('ALAudioDevice_cerrado', llamadas)
            self.assertIn('broker_cerrado', llamadas)
            self.assertNotIn('ALMotion', llamadas)
            with self.assertRaises(OSError):
                socket.create_connection(('127.0.0.1', puertos[1]), timeout=.2)


class PruebasRespaldo(unittest.TestCase):
    def test_fallo_fisico_intenta_virtual_con_fuentes_pc(self):
        with patch('iniciar_examen.iniciar_prueba', side_effect=[70, 70, 0]) as iniciar:
            with patch('builtins.input', return_value='61778') as entrada, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(iniciar_examen(['--ip', '192.0.2.20', '--sin-ia']), 0)
        primero, alternativo, segundo = [c.args[0] for c in iniciar.call_args_list]
        self.assertIn('192.0.2.20', primero)
        self.assertIn('--camara-nao', primero)
        self.assertIn('9561', alternativo)
        self.assertIn('--camara-nao', alternativo)
        self.assertIn('127.0.0.1', segundo)
        self.assertIn('61778', segundo)
        self.assertIn('virtual', segundo)
        self.assertIn('--microfono', segundo)
        self.assertNotIn('--camara-nao', segundo)
        self.assertNotIn('--microfono-nao', segundo)
        entrada.assert_called_once()

    def test_no_cambia_destino_tras_cierre_error_local_o_cancelacion(self):
        for codigo in (0, 1, 130):
            with self.subTest(codigo=codigo), patch('iniciar_examen.iniciar_prueba', return_value=codigo) as iniciar:
                with patch('builtins.input') as entrada, contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(iniciar_examen(['--ip', '192.0.2.20', '--sin-ia']), codigo)
                iniciar.assert_called_once()
                entrada.assert_not_called()

    def test_fallo_del_virtual_no_crea_bucle_de_reintentos(self):
        with patch('iniciar_examen.iniciar_prueba', side_effect=[70, 70, 70]) as iniciar:
            with patch('builtins.input') as entrada, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(iniciar_examen(['--ip', '192.0.2.20', '--puerto-virtual', '61778']), 70)
            self.assertEqual(iniciar.call_count, 3)
            entrada.assert_not_called()

    def test_virtual_directo_no_pide_ip_fisica(self):
        with patch('iniciar_examen.iniciar_prueba', return_value=0) as iniciar:
            with patch('builtins.input') as entrada, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(iniciar_examen(['--virtual', '--puerto-virtual', '61778', '--diagnostico']), 0)
        entrada.assert_not_called()
        iniciar.assert_called_once()
        self.assertIn('--solo-diagnostico', iniciar.call_args.args[0])
        self.assertNotIn('--camara-nao', iniciar.call_args.args[0])

    def test_puerto_virtual_invalido_no_conecta(self):
        with patch('iniciar_examen.iniciar_prueba') as iniciar, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(iniciar_examen(['--virtual', '--puerto-virtual', '0']), 1)
        iniciar.assert_not_called()

    def test_perfil_anterior_conserva_respaldo_desactivado(self):
        p = cargar_config()
        p.pop('respaldo_choregraphe')
        p.pop('puerto_virtual')
        p.pop('puertos_fisicos_alternativos')
        with tempfile.TemporaryDirectory() as t:
            ruta = Path(t) / 'perfil.json'
            ruta.write_text(json.dumps(p), encoding='utf-8')
            anterior = cargar_config(ruta)
            self.assertFalse(anterior['respaldo_choregraphe'])
            self.assertEqual(anterior['puertos_fisicos_alternativos'], [])

    def test_9561_conectado_conserva_nao_fisico_y_evitar_virtual(self):
        perfil = cargar_config()
        perfil['robot_ip'] = '192.0.2.20'
        with patch('iniciar_examen.iniciar_prueba', side_effect=[70, 0]) as iniciar:
            with patch('builtins.input') as entrada, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(modulo_examen.ejecutar_con_respaldo(perfil), 0)
        entrada.assert_not_called()
        args = [c.args[0] for c in iniciar.call_args_list]
        self.assertEqual([a[a.index('--robot-port') + 1] for a in args], ['9559', '9561'])
        for a in args:
            self.assertIn('--camara-nao', a)
            self.assertIn('--microfono-nao', a)
            self.assertEqual(a[a.index('--entorno') + 1], 'fisico')
        self.assertEqual(perfil['robot_port'], 9559)

    def test_error_local_en_otro_puerto_no_lanza_virtual(self):
        for codigo in (1, 130):
            with self.subTest(codigo=codigo), patch('iniciar_examen.iniciar_prueba', side_effect=[70, codigo]) as iniciar:
                with patch('builtins.input') as entrada, contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(iniciar_examen(['--ip', '192.0.2.20']), codigo)
                entrada.assert_not_called()
                self.assertEqual(iniciar.call_count, 2)

    def test_puerto_principal_no_se_repite_en_respaldo(self):
        perfil = cargar_config()
        perfil.update(robot_ip='192.0.2.20', puertos_fisicos_alternativos=[9559, 9561], puerto_virtual=61778)
        with patch('iniciar_examen.iniciar_prueba', side_effect=[70, 70, 0]) as iniciar:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(modulo_examen.ejecutar_con_respaldo(perfil), 0)
        args = [c.args[0] for c in iniciar.call_args_list]
        self.assertEqual([a[a.index('--robot-port') + 1] for a in args], ['9559', '9561', '61778'])

    def test_camara_fallida_conserva_microfono_nao(self):
        def proxy(modulo, *args):
            if modulo == 'ALVideoDevice':
                raise RuntimeError('CAMARA_SIMULADA_AVERIADA')
            return SimpleNamespace(systemVersion=lambda: 'SDK_SIMULADO', getOutputVolume=lambda: 60,
                                   isAudioOutMuted=lambda: False)
        def abrir_audio(sensores, *args):
            sensores.audio = BufferAudio()
            sensores.audio.recibir(1, 4, b'\0' * 8)
        sensores = SensoresNAO()
        with patch.dict(sys.modules, {'naoqi': SimpleNamespace(ALProxy=proxy)}):
            with patch.object(SensoresNAO, 'abrir_microfono', autospec=True, side_effect=abrir_audio) as audio:
                sensores.abrir('192.0.2.20', 9559, tolerar_fallos=True)
        audio.assert_called_once()
        self.assertIsNone(sensores.camara)
        self.assertEqual(sensores.estado()['microfono']['paquetes'], 1)
        self.assertIn('CAMARA_SIMULADA_AVERIADA', sensores.estado()['fallos']['camara'])
        sensores.cerrar()

    def test_microfono_fallido_conserva_camara_nao(self):
        video = VideoFalso()
        def proxy(modulo, *args):
            return video if modulo == 'ALVideoDevice' else SimpleNamespace(
                systemVersion=lambda: 'SDK_SIMULADO', getOutputVolume=lambda: 60, isAudioOutMuted=lambda: False)
        sensores = SensoresNAO()
        with patch.dict(sys.modules, {'naoqi': SimpleNamespace(ALProxy=proxy)}):
            with patch.object(SensoresNAO, 'abrir_microfono', side_effect=OSError('MICROFONO_SIMULADO_AVERIADO')):
                sensores.abrir('192.0.2.20', 9559, tolerar_fallos=True)
        self.assertTrue(sensores.estado()['camara']['activa'])
        self.assertIsNone(sensores.audio)
        self.assertFalse(video.cerrado)
        sensores.cerrar()
        self.assertTrue(video.cerrado)

    def test_camara_rota_sin_respaldo_mantiene_error(self):
        def proxy(modulo, *args):
            if modulo == 'ALVideoDevice':
                raise RuntimeError('CAMARA_SIMULADA_AVERIADA')
            return SimpleNamespace(systemVersion=lambda: 'SDK_SIMULADO', getOutputVolume=lambda: 60,
                                   isAudioOutMuted=lambda: False)
        with patch.dict(sys.modules, {'naoqi': SimpleNamespace(ALProxy=proxy)}):
            with self.assertRaisesRegex(RuntimeError, 'CAMARA_SIMULADA_AVERIADA'):
                SensoresNAO().abrir('192.0.2.20', 9559)

    def test_camara_cambia_a_pc_una_vez_y_se_identifica(self):
        from unittest.mock import Mock
        remoto = Mock()
        remoto.isOpened.return_value = True
        remoto.read.side_effect = ErrorSensores('CAMARA_SIMULADA_INTERRUMPIDA')
        pc = Mock()
        pc.isOpened.return_value = True
        pc.read.return_value = (True, 'IMAGEN_PC_SIMULADA')
        cv = Mock(VideoCapture=Mock(return_value=pc))
        with patch('sensores_cliente.ClienteSensores'), patch('sensores_cliente.CamaraRemota', return_value=remoto):
            camara = CamaraConRespaldo(cv, origen='nao', permitir_respaldo=True)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(camara.read(), (True, 'IMAGEN_PC_SIMULADA'))
            self.assertTrue(camara.cambio)
            self.assertEqual(camara.origen, 'pc')
            camara.read()
        remoto.release.assert_called_once()
        cv.VideoCapture.assert_called_once()
        camara.release()
        pc.release.assert_called_once()

    def test_microfono_cae_a_pc_y_si_falla_quedan_teclas(self):
        for error_pc in (False, True):
            estado = {}
            conexion = SimpleNamespace(closed=threading.Event())
            errores = [ErrorSensores('MIC_NAO_SIMULADO'), OSError('MIC_PC_SIMULADO') if error_pc else None]
            with self.subTest(error_pc=error_pc), patch('vision_ia.escuchar_fuente', side_effect=errores) as escuchar:
                with contextlib.redirect_stdout(io.StringIO()):
                    vision_ia.escuchar(conexion, None, origen='nao', estado_microfono=estado, permitir_respaldo=True)
                self.assertEqual([x.args[2] for x in escuchar.call_args_list], ['nao', 'pc'])
                self.assertEqual(estado['origen'], 'no' if error_pc else 'pc')

    def test_fallo_fisico_y_virtual_con_puente_tcp_real_y_sdk_simulado(self):
        import os
        from cliente_neo import ConexionNeo
        with tempfile.TemporaryDirectory() as t:
            raiz = Path(t)
            sdk = SDK_DE_PROCESO.replace('def ALProxy(modulo, ip, port):\n',
                'def ALProxy(modulo, ip, port):\n'
                '    log({"ip":ip,"puerto":port,"modulo":modulo})\n'
                '    if ip == "192.0.2.20": raise RuntimeError("DESTINO_FISICO_SIMULADO_CAIDO")\n')
            (raiz / 'naoqi.py').write_text(sdk, encoding='utf-8')
            log = raiz / 'sdk.jsonl'
            perfil = cargar_config()
            perfil.update(robot_ip='192.0.2.20', python_naoqi=sys.executable, puerto_virtual=61778)
            sockets = [socket.socket() for _ in range(3)]
            for s in sockets:
                s.bind(('127.0.0.1', 0))
            for clave, s in zip(('puerto_control', 'puerto_sensores', 'callback_port'), sockets):
                perfil[clave] = s.getsockname()[1]
                s.close()
            ruta = raiz / 'perfil.json'
            ruta.write_text(json.dumps(perfil), encoding='utf-8')
            def cliente_prueba(comando, **kwargs):
                self.assertIn('--respaldo-pc', comando)
                self.assertNotIn('nao', comando)
                conexion = ConexionNeo(port=perfil['puerto_control'])
                try:
                    conexion.esperar()
                    self.assertEqual(conexion.hello['entorno'], 'virtual')
                    self.assertFalse(conexion.hello['simulado'])  # Conexion real al SDK FALSO de este test.
                    self.assertEqual(conexion.snapshot()['marcador'], {'neo': 0, 'jugador': 0})
                    return 0
                finally:
                    conexion.cerrar()
            with patch.dict(os.environ, {'PYTHONPATH': str(raiz), 'NEO_SDK_TEST_LOG': str(log)}):
                with patch('probar_choregraphe.subprocess.call', side_effect=cliente_prueba), patch('builtins.input') as entrada:
                    self.assertEqual(iniciar_examen(['--config', str(ruta), '--sin-ia']), 0)
            entrada.assert_not_called()
            llamadas = [json.loads(x) for x in log.read_text().splitlines()]
            destinos = [x['ip'] for x in llamadas if isinstance(x, dict)]
            self.assertEqual(destinos, ['192.0.2.20', '192.0.2.20', '127.0.0.1', '127.0.0.1'])
            puertos_fisicos = [x['puerto'] for x in llamadas if isinstance(x, dict) and x['ip'] == '192.0.2.20']
            self.assertEqual(puertos_fisicos, [9559, 9561])
            with self.assertRaises(OSError):
                socket.create_connection(('127.0.0.1', perfil['puerto_control']), timeout=.2)


if __name__ == '__main__':
    unittest.main()
