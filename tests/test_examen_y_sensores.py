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


if __name__ == '__main__':
    unittest.main()
