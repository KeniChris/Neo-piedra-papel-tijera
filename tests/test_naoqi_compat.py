"""Regresion de tipos con SDK FALSO; no ejecuta Python 2 ni Choregraphe."""
import contextlib
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comprobar_naoqi import main as comprobar
from naoqi_compat import cadena_naoqi
from robot_server_ia import Robot


class SDKClasicoFalso:
    """Exige bytes UTF-8 para reproducir el limite del SDK clasico."""
    __file__ = 'SDK_FALSO_PARA_TESTS'

    def __init__(self):
        self.proxies = []
        self.frases = []
        self.metodos = []

    def exigir_cadena(self, texto):
        if not isinstance(texto, bytes):
            raise NotImplementedError('Wrong type: el SDK de prueba exige bytes, no Unicode')
        texto.decode('utf-8')

    def ALProxy(self, modulo, ip, puerto):
        self.exigir_cadena(modulo)
        self.exigir_cadena(ip)
        if not isinstance(puerto, int):
            raise NotImplementedError('El puerto debe ser entero')
        self.proxies.append(modulo)
        return self

    def setLanguage(self, idioma):
        self.exigir_cadena(idioma)

    def say(self, texto):
        self.exigir_cadena(texto)
        self.frases.append(texto.decode('utf-8'))

    def fadeRGB(self, grupo, color, duracion):
        self.exigir_cadena(grupo)
        self.metodos.append('luces')

    def goToPosture(self, nombre, velocidad):
        self.exigir_cadena(nombre)
        self.metodos.append('postura')

    def angleInterpolation(self, nombres, angulos, tiempos, absoluto):
        for nombre in nombres:
            self.exigir_cadena(nombre)
        self.metodos.append('brazo')

    def setAngles(self, nombre, angulo, velocidad):
        self.exigir_cadena(nombre)
        self.metodos.append('mano')


class PruebasCompatibilidadNAOqi(unittest.TestCase):
    def test_conversion_utf8_y_cadenas_python3(self):
        with patch('naoqi_compat.PYTHON_2', True):
            self.assertEqual(cadena_naoqi('¡Ganó Neo!'), '¡Ganó Neo!'.encode('utf-8'))
            self.assertEqual(cadena_naoqi(b'ALTextToSpeech'), b'ALTextToSpeech')
        with patch('naoqi_compat.PYTHON_2', False):
            self.assertIsInstance(cadena_naoqi('¡Ganó Neo!'), str)
            self.assertEqual(cadena_naoqi('¡Ganó Neo!'.encode('utf-8')), '¡Ganó Neo!')

    def test_diagnostico_con_limite_de_tipos_python2_simulado(self):
        sdk = SDKClasicoFalso()
        # El doble reproduce primero el fallo que los mocks anteriores aceptaban.
        with self.assertRaises(NotImplementedError):
            sdk.ALProxy('ALTextToSpeech', '127.0.0.1', 62213)
        with patch.dict(sys.modules, {'naoqi': sdk}), patch('naoqi_compat.PYTHON_2', True):
            with patch.object(sys, 'argv', ['comprobar_naoqi.py', '--robot-port', '62213']):
                with contextlib.redirect_stdout(io.StringIO()) as salida:
                    self.assertEqual(comprobar(), 0)
        self.assertIn('NAOQI_OK', salida.getvalue())
        self.assertEqual(sdk.proxies, [b'ALTextToSpeech'])

    def test_puente_convierte_nombres_idioma_frases_y_movimientos(self):
        sdk = SDKClasicoFalso()
        with patch.dict(sys.modules, {'naoqi': sdk}), patch('naoqi_compat.PYTHON_2', True):
            with patch('robot_server_ia.time.sleep'), contextlib.redirect_stdout(io.StringIO()):
                robot = Robot('127.0.0.1', 62213, movimientos=True)
                robot.decir('Tú ganaste; yo perdí.')
                robot.preparar()
                robot.sacudir()
                robot.mostrar('tijera')
                robot.ojos(0x00FF00)
        self.assertEqual(sdk.frases, ['Tú ganaste; yo perdí.'])
        self.assertEqual(len(sdk.proxies), 4)
        self.assertTrue({'postura', 'brazo', 'mano', 'luces'}.issubset(sdk.metodos))

    def test_error_muestra_etapa_y_excepcion_completas(self):
        for etapa in ('proxy', 'say'):
            with self.subTest(etapa=etapa):
                def fallar(*args):
                    raise NotImplementedError('DETALLE_SDK_NO_OCULTO')
                voz = SimpleNamespace(setLanguage=lambda _: None, say=fallar)
                sdk = SimpleNamespace(__file__='SDK_FALSO', ALProxy=fallar if etapa == 'proxy' else lambda *args: voz)
                with patch.dict(sys.modules, {'naoqi': sdk}):
                    with patch.object(sys, 'argv', ['comprobar_naoqi.py', '--robot-port', '62213']):
                        with contextlib.redirect_stdout(io.StringIO()) as salida, contextlib.redirect_stderr(io.StringIO()) as error:
                            self.assertEqual(comprobar(), 70)
                esperado = 'crear ALProxy' if etapa == 'proxy' else 'ALTextToSpeech.say'
                self.assertIn(esperado, salida.getvalue())
                self.assertIn('DETALLE_SDK_NO_OCULTO', salida.getvalue())
                self.assertIn('NotImplementedError', error.getvalue())


if __name__ == '__main__':
    unittest.main()
