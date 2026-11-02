"""OpenAI y SDK FALSOS; HTTP local real y PCM sintetico. Sin pagos ni hardware."""
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audio_neo import ClienteVoz, ErrorAudio, ErrorPuenteVoz, SalidaAudioNAO, convertir_24mono_a_48estereo
from comprobar_naoqi import main as comprobar, FALLO_DESTINO
from iniciar_examen import main as examen
from robot_server_ia import Robot, Sesion
from voz_openai import (ErrorVoz, LectorOpenAI, ServicioVoz, coste_estimado,
                        entorno_sin_claves_api, obtener_clave)

PCM = struct.pack('<hhh', -100, 0, 100)
USO = {'input_tokens': 30, 'output_tokens': 22, 'total_tokens': 52,
       'input_token_details': {'text_tokens': 30},
       'output_token_details': {'audio_tokens': 20, 'text_tokens': 2}}


class WebSocketFalso:
    def __init__(self, texto='Hola, soy Neo.', pcm=PCM, estado='completed'):
        self.eventos = iter([
            {'type': 'session.created'},
            {'type': 'session.updated', 'session': {'audio': {'output': {
                'format': {'type': 'audio/pcm', 'rate': 24000}}}}},
            {'type': 'response.output_audio.delta', 'delta': base64.b64encode(pcm).decode('ascii')},
            {'type': 'response.output_audio_transcript.done', 'transcript': texto},
            {'type': 'response.done', 'response': {'status': estado, 'usage': USO}},
        ])
        self.enviados = []
        self.cerrado = False

    def recv(self):
        return json.dumps(next(self.eventos))

    def send(self, dato):
        self.enviados.append(json.loads(dato))

    def settimeout(self, valor):
        pass

    def close(self):
        self.cerrado = True


class PruebasRealtime(unittest.TestCase):
    def test_flujo_pcm_transcripcion_y_cache_sin_nueva_consulta(self):
        ws = WebSocketFalso()
        conectar = Mock(return_value=ws)
        with tempfile.TemporaryDirectory() as t:
            registro = Path(t) / 'uso.jsonl'
            lector = LectorOpenAI('CLAVE_FALSA_SOLO_TESTS', conectar=conectar, registro=registro)
            self.assertEqual(lector.sintetizar('Hola, soy Neo.'), PCM)
            self.assertEqual(lector.sintetizar('Hola, soy Neo.'), PCM)
            filas = [json.loads(x) for x in registro.read_text().splitlines()]
            self.assertFalse(filas[0]['cache_local'])
            self.assertTrue(filas[1]['cache_local'])
            self.assertEqual(filas[1]['usd_estimado'], 0)
            self.assertNotIn('CLAVE_FALSA', registro.read_text())
            self.assertNotIn('Hola', registro.read_text())
        self.assertEqual(lector.solicitudes, 1)
        self.assertEqual(conectar.call_count, 1)
        self.assertTrue(ws.cerrado)
        update, item, response = ws.enviados
        self.assertIsNone(update['session']['audio']['input']['turn_detection'])
        self.assertEqual(update['session']['tools'], [])
        self.assertEqual(item['item']['content'], [{'type': 'input_text', 'text': 'Hola, soy Neo.'}])
        self.assertEqual(response['response']['output_modalities'], ['audio'])

    def test_resultado_cambiado_no_se_reproduce_ni_se_cachea(self):
        for transcripcion, pcm, estado in [('Gano yo.', PCM, 'completed'),
                                             ('Ganaste.', b'\x00', 'completed'),
                                             ('Ganaste.', PCM, 'incomplete')]:
            with self.subTest(transcripcion=transcripcion, estado=estado):
                ws = WebSocketFalso(transcripcion, pcm, estado)
                lector = LectorOpenAI('FALSA', conectar=Mock(return_value=ws))
                with self.assertRaises(ErrorVoz):
                    lector.sintetizar('Ganaste.')
                self.assertFalse(lector._cache)
                self.assertTrue(ws.cerrado)

    def test_numeros_y_puntuacion_no_cambian_el_significado(self):
        lector = LectorOpenAI('FALSA', conectar=Mock(return_value=WebSocketFalso('Jugaremos tres rondas.')))
        self.assertEqual(lector.sintetizar('Jugaremos 3 rondas.'), PCM)

    def test_error_de_red_no_filtra_clave_ni_reintenta(self):
        conectar = Mock(side_effect=RuntimeError('Authorization: Bearer CLAVE_SECRETA_DE_PRUEBA'))
        lector = LectorOpenAI('CLAVE_SECRETA_DE_PRUEBA', conectar=conectar)
        with self.assertRaises(ErrorVoz) as error:
            lector.sintetizar('Hola.')
        self.assertNotIn('CLAVE_SECRETA', str(error.exception))
        self.assertEqual(conectar.call_count, 1)

    def test_saldo_agotado_es_error_de_voz_sin_otra_consulta(self):
        ws = WebSocketFalso()
        ws.eventos = iter([{'type': 'error', 'error': {'code': 'credit_balance_exhausted', 'message': 'SECRETO'}}])
        lector = LectorOpenAI('FALSA', conectar=Mock(return_value=ws))
        with self.assertRaisesRegex(ErrorVoz, 'saldo'):
            lector.sintetizar('Hola.')
        self.assertEqual(lector.solicitudes, 0)
        self.assertTrue(ws.cerrado)

    def test_clave_oculta_y_entorno_de_hijos_sin_claves(self):
        with patch.dict(os.environ, {}, clear=True), patch('getpass.getpass', return_value='CLAVE_FALSA') as entrada:
            self.assertEqual(obtener_clave(), 'CLAVE_FALSA')
            entrada.assert_called_once()
        limpio = entorno_sin_claves_api({'OPENAI_API_KEY': 'a', 'CODEX_API_KEY': 'b',
                                        'OPENAI_ADMIN_KEY': 'c', 'PYTHONPATH': 'sdk'})
        self.assertEqual(limpio, {'PYTHONPATH': 'sdk'})
        self.assertAlmostEqual(coste_estimado(USO), .0004228)


class PruebasPuenteYSalida(unittest.TestCase):
    def test_http_real_rechaza_token_y_transporta_pcm_al_sdk(self):
        lector = Mock()
        lector.sintetizar.return_value = PCM
        servicio = ServicioVoz(lector, puerto=0)
        try:
            salida = Mock()
            with self.assertRaises(ErrorPuenteVoz):
                ClienteVoz(servicio.puerto, token='OTRA_SESION', salida=salida).decir('Hola.')
            lector.sintetizar.assert_not_called()
            ClienteVoz(servicio.puerto, servicio.token, salida).decir('Hola, soy Neo.')
            salida.reproducir.assert_called_once_with(PCM)
        finally:
            servicio.cerrar()
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', servicio.puerto), timeout=.2)

    def test_virtual_espera_reproduccion_pc_sin_salida_nao(self):
        empezo, finalizar = threading.Event(), threading.Event()
        def reproducir(pcm):
            self.assertEqual(pcm, PCM)
            empezo.set()
            finalizar.wait(2)
        servicio = ServicioVoz(Mock(sintetizar=Mock(return_value=PCM)), puerto=0, salida='pc',
                               reproductor=SimpleNamespace(reproducir=reproducir))
        errores = []
        def hablar():
            try:
                ClienteVoz(servicio.puerto, servicio.token).decir('Hola.')
            except Exception as error:
                errores.append(error)
        hilo = threading.Thread(target=hablar)
        try:
            hilo.start()
            self.assertTrue(empezo.wait(2))
            self.assertTrue(hilo.is_alive(), 'La confirmacion debe esperar a la reproduccion')
        finally:
            finalizar.set()
            hilo.join(2)
            servicio.cerrar()
        self.assertFalse(errores)

    def test_conversion_tramas_y_restauracion_de_tasa_incluso_si_falla(self):
        self.assertEqual(convertir_24mono_a_48estereo(PCM), b''.join(PCM[i:i+2] * 4 for i in range(0, 6, 2)))
        audio = Mock()
        audio.getOutputVolume.return_value = 50
        audio.isAudioOutMuted.return_value = False
        audio.getParameter.return_value = 44100
        audio.sendRemoteBufferToOutput.return_value = True
        sesion = Mock(service=Mock(return_value=audio))
        salida = SalidaAudioNAO('IP_FALSA', 9559, sesion=sesion)
        with patch('audio_neo.time.sleep'):
            salida.reproducir(PCM * 2000)
        for llamada in audio.sendRemoteBufferToOutput.call_args_list:
            frames, bloque = llamada.args
            self.assertIsInstance(bloque, bytearray)
            self.assertLessEqual(frames, 16384)
            self.assertEqual(len(bloque), frames * 4)
            self.assertLessEqual(len(bloque), 16384)
        self.assertEqual(audio.setParameter.call_args_list[-1].args, ('outputSampleRate', 44100))
        audio.sendRemoteBufferToOutput.return_value = False
        with self.assertRaises(ErrorAudio):
            salida.reproducir(PCM)
        self.assertEqual(audio.setParameter.call_args_list[-1].args, ('outputSampleRate', 44100))
        audio.setOutputVolume.assert_not_called()

    def test_fallo_de_nube_no_se_confunde_con_puerto_fisico(self):
        sdk = SimpleNamespace(ALProxy=Mock(), __file__='SDK_FALSO')
        argv = ['comprobar_naoqi.py', '--robot-port', '9559', '--voz', 'openai', '--probar-voz']
        with patch.dict(sys.modules, {'naoqi': sdk}), patch('audio_neo.SalidaAudioNAO') as salida:
            with patch('audio_neo.ClienteVoz') as cliente, patch.object(sys, 'argv', argv):
                cliente.return_value.decir.side_effect = ErrorPuenteVoz('Saldo API agotado.')
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(comprobar(), 1)
                salida.return_value.cerrar.assert_called_once()
        with patch.dict(sys.modules, {'naoqi': sdk}), patch('audio_neo.SalidaAudioNAO', side_effect=RuntimeError):
            with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(comprobar(), 1)  # No repetir una prueba de pago en otro puerto.
            with patch.object(sys, 'argv', argv[:-1]), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(comprobar(), FALLO_DESTINO)  # Preflight sin consulta de pago.

    def test_fallo_cuenta_atras_no_abre_captura(self):
        robot = Robot('', 0, simular=True)
        robot.decir = Mock(side_effect=ErrorAudio('PCM rechazado'))
        sesion = Sesion(Mock(), robot)
        sesion.estado.iniciar()
        with self.assertRaises(ErrorAudio):
            sesion.ronda()
        self.assertNotEqual(sesion.estado.fase, 'capturando')
        self.assertEqual(sesion.estado.snapshot()['marcador'], {'neo': 0, 'jugador': 0})

    def test_perfil_openai_sigue_con_luna_y_restaura_clave(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'FALSA'}), patch('iniciar_examen.comprobar_biblioteca'), \
             patch('iniciar_examen.iniciar_prueba', return_value=0) as iniciar:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(examen(['--ip', '192.0.2.10', '--voz', 'openai']), 0)
            args = iniciar.call_args.args[0]
            self.assertEqual(args[args.index('--voz') + 1], 'openai')
            self.assertEqual(os.environ['NEO_CODEX_MODEL'], 'gpt-6-luna')
            self.assertEqual(os.environ['OPENAI_API_KEY'], 'FALSA')

    def test_bridge_real_en_subproceso_entrega_texto_a_voz_pc_con_sdk_falso(self):
        """TCP real del juego -> Python SDK separado -> HTTP real -> PCM sintetico PC."""
        from cliente_neo import ConexionNeo
        import probar_choregraphe
        with tempfile.TemporaryDirectory() as t:
            raiz = Path(t)
            (raiz / 'naoqi.py').write_text('def ALProxy(*args): return object()\n')
            pcm_recibidos = []
            servicio = ServicioVoz(Mock(sintetizar=Mock(return_value=PCM)), puerto=0, salida='pc',
                                   reproductor=SimpleNamespace(reproducir=pcm_recibidos.append))
            with socket.socket() as s:
                s.bind(('127.0.0.1', 0))
                puerto = s.getsockname()[1]
            cmd = [sys.executable, '-u', 'robot_server_ia.py', '--robot-port', '61778', '--puerto', str(puerto),
                   '--voz', 'openai', '--puerto-voz', str(servicio.puerto), '--entorno', 'virtual']
            env = entorno_sin_claves_api(os.environ)
            env.update(PYTHONPATH=str(raiz), NEO_VOZ_TOKEN=servicio.token)
            proceso = subprocess.Popen(cmd, cwd=str(Path(__file__).resolve().parents[1]), env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            conexion = None
            try:
                listo, lector_hilo = probar_choregraphe.esperar_puente(proceso)
                self.assertTrue(listo)
                conexion = ConexionNeo(port=puerto)
                conexion.esperar()
                fin = time.monotonic() + 2
                while not pcm_recibidos and time.monotonic() < fin:
                    time.sleep(.01)
                self.assertTrue(pcm_recibidos)
                self.assertEqual(conexion.hello['voz'], 'openai')
                self.assertEqual(conexion.hello['salida_voz'], 'pc')
                self.assertFalse(conexion.hello['simulado'])
            finally:
                if conexion:
                    conexion.cerrar()
                probar_choregraphe.detener_puente(proceso)
                servicio.cerrar()
                lector_hilo.join(2)
