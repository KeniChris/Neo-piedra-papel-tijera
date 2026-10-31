"""Politicas y lanzador con NAOqi FALSO; sin Choregraphe ni robot reales."""
import contextlib
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cliente_neo import ConexionNeo, Conversador
from estado_juego import EstadoJuego
from ia_neo import CerebroNeo, ErrorIA, FUNCION, RUTA_POLITICAS
from probar_choregraphe import main as probar_choregraphe


def respuesta_falsa(texto='Soy una respuesta simulada de prueba.'):
    return {'status': 'completed', 'output': [{'type': 'function_call',
            'name': FUNCION, 'arguments': json.dumps({'accion': 'hablar', 'texto': texto})}]}


class PruebasPoliticas(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.ruta = Path(self.temporal.name) / 'personalidad.md'
        self.ruta.write_text('PERSONA_UNO: humor amable y español.', encoding='utf-8-sig')

    def test_lee_utf8_bom_y_recarga_siguiente_consulta(self):
        solicitudes = []
        def transporte(payload):
            solicitudes.append(payload)
            return respuesta_falsa()
        b = CerebroNeo(politicas=self.ruta, transporte=transporte)
        b.responder(EstadoJuego().snapshot(), 'hola')
        huella = b.politicas_huella
        self.ruta.write_text('PERSONA_DOS: español y tono curioso.', encoding='utf-8')
        b.responder(EstadoJuego().snapshot(), 'otra pregunta')
        self.assertIn('PERSONA_UNO', solicitudes[0]['input'][0]['content'])
        self.assertIn('PERSONA_DOS', solicitudes[1]['input'][0]['content'])
        self.assertNotIn('PERSONA_UNO', solicitudes[1]['input'][0]['content'])
        self.assertNotEqual(b.politicas_huella, huella)

    def test_ruta_predeterminada_no_depende_de_cwd(self):
        anterior = Path.cwd()
        try:
            os.chdir(self.temporal.name)
            with patch.dict(os.environ, {'NEO_POLITICAS': ''}):
                b = CerebroNeo(transporte=lambda _: respuesta_falsa())
            self.assertEqual(b.politicas_path, RUTA_POLITICAS)
            self.assertIn('Neo: personalidad', b.payload(EstadoJuego().snapshot(), 'hola')['input'][0]['content'])
        finally:
            os.chdir(anterior)

    def test_variable_de_entorno_y_error_antes_de_contactar_modelo(self):
        with patch.dict(os.environ, {'NEO_POLITICAS': str(self.ruta)}):
            b = CerebroNeo(transporte=lambda _: self.fail('No debe consultar con politicas invalidas'))
        self.assertEqual(b.politicas_path, self.ruta)
        for contenido in (b'', b'\xff\xfe', b'a' * 32769):
            with self.subTest(contenido=len(contenido)):
                self.ruta.write_bytes(contenido)
                with self.assertRaises(ErrorIA):
                    b.responder(EstadoJuego().snapshot(), 'hola')
        self.ruta.unlink()
        with self.assertRaises(ErrorIA):
            b.responder(EstadoJuego().snapshot(), 'hola')

    def test_ambos_transportes_reciben_markdown_y_formato_correcto(self):
        solicitudes = []
        b = CerebroNeo(politicas=self.ruta, provider='openai',
                       transporte=lambda p: solicitudes.append(p) or respuesta_falsa())
        b.responder(EstadoJuego().snapshot(), 'hola')
        prompt_api = solicitudes[0]['input'][0]['content']
        self.assertIn('PERSONA_UNO', prompt_api)
        self.assertIn('exactamente una llamada interactuar_con_jugador', prompt_api)

        class CodexFalso:
            def responder(self, instrucciones, entrada, schema):
                self.instrucciones = instrucciones
                return {'accion': 'hablar', 'texto': 'Respuesta simulada.'}
        falso = CodexFalso()
        b.codex = falso
        b.responder(EstadoJuego().snapshot(), 'hola')
        self.assertIn('PERSONA_UNO', falso.instrucciones)
        self.assertIn('exactamente un objeto JSON con accion y texto', falso.instrucciones)
        self.assertNotIn('exactamente una llamada', falso.instrucciones)


SDK_FALSO = '''from __future__ import print_function
import json, os
def anotar(dato):
    with open(os.environ['NEO_PRUEBA_LOG_SDK'], 'a') as f:
        f.write(json.dumps(dato) + '\\n')
class VozFalsa(object):
    def setLanguage(self, idioma):
        anotar({'idioma': idioma})
    def say(self, texto):
        if isinstance(texto, bytes):
            texto = texto.decode('utf-8')
        anotar({'frase': texto})
def ALProxy(modulo, ip, puerto):
    anotar({'proxy': modulo, 'ip': ip, 'puerto': puerto})
    if modulo != 'ALTextToSpeech':
        raise AssertionError('La prueba sin movimientos no debe crear ' + modulo)
    return VozFalsa()
'''


class PruebasLanzador(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        raiz = Path(self.temporal.name)
        (raiz / 'naoqi.py').write_text(SDK_FALSO, encoding='utf-8')
        self.log = raiz / 'sdk.jsonl'
        self.entorno = {'NEO_PRUEBA_LOG_SDK': str(self.log),
                       'PYTHONPATH': str(raiz) + os.pathsep + os.environ.get('PYTHONPATH', '')}
        self.argumentos = ['--python-naoqi', sys.executable, '--robot-ip', '127.0.0.1',
                          '--robot-port', '54321']

    def leer_log(self):
        return [json.loads(x) for x in self.log.read_text(encoding='utf-8').splitlines()]

    def test_solo_conexion_usa_destino_y_no_arranca_cliente(self):
        with patch.dict(os.environ, self.entorno), patch('subprocess.call') as cliente:
            self.assertEqual(probar_choregraphe(self.argumentos + ['--solo-conexion']), 0)
            cliente.assert_not_called()
        eventos = self.leer_log()
        self.assertIn({'proxy': 'ALTextToSpeech', 'ip': '127.0.0.1', 'puerto': 54321}, eventos)
        self.assertEqual(sum('frase' in x for x in eventos), 1)

    def test_lanzador_puente_tcp_confirmacion_y_cierre_con_sdk_falso(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            puerto = s.getsockname()[1]
        respuesta = 'Probé conexión, acentos y políticas: ¡bien!'

        def cliente_de_prueba(comando, **kwargs):
            self.assertIn('--robot', comando)
            self.assertEqual(kwargs['env']['NEO_CODEX_MODEL'], 'gpt-6-luna')
            self.assertNotIn('PYTHONPATH', kwargs['env'])
            self.assertNotIn('PYTHONHOME', kwargs['env'])
            c = ConexionNeo(port=puerto)
            b = None
            try:
                c.esperar()
                b = Conversador(c, CerebroNeo(transporte=lambda _: respuesta_falsa(respuesta)), comentarios=False)
                b.pedir('Mensaje de integración simulada')
                fin = time.monotonic() + 5
                while not b.cerebro.historia and time.monotonic() < fin:
                    time.sleep(0.02)
                self.assertTrue(b.cerebro.historia, 'Debe recibir confirmacion del puente')
                self.assertEqual(c.snapshot()['marcador'], {'neo': 0, 'jugador': 0})
                return 0
            finally:
                if b:
                    b.cerrar()
                c.cerrar()

        with patch.dict(os.environ, dict(self.entorno, NEO_CODEX_MODEL='gpt-6-luna')):
            with patch('subprocess.call', side_effect=cliente_de_prueba):
                self.assertEqual(probar_choregraphe(self.argumentos + ['--puerto', str(puerto)]), 0)
        eventos = self.leer_log()
        self.assertIn({'frase': respuesta}, eventos)
        self.assertEqual(sum('proxy' in x for x in eventos), 2)
        with self.assertRaises(OSError):
            socket.create_connection(('127.0.0.1', puerto), timeout=0.2)

    def test_interprete_inexistente_informa_sin_ejecutar(self):
        with patch('subprocess.run') as lanzar, contextlib.redirect_stdout(io.StringIO()) as salida:
            resultado = probar_choregraphe(['--python-naoqi', str(Path(self.temporal.name) / 'no_existe'),
                                           '--robot-port', '54321', '--solo-conexion'])
        self.assertEqual(resultado, 1)
        self.assertIn('No existe el interprete', salida.getvalue())
        lanzar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
