"""Diagnosticos con modulos de prueba; sin camara ni red."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import preparar_vision
import vision_ia


class PruebasDependenciasVision(unittest.TestCase):
    def test_solo_camara_no_arranca_codex_naoqi_ni_microfono(self):
        with patch.object(sys, 'argv', ['vision_ia.py', '--solo-camara', '--camara', '1']), \
             patch('vision_ia.cargar_dependencias', return_value=('cv', 'mp', 'hands')), \
             patch('vision_ia.probar_solo_camara', return_value=0) as camara, \
             patch('vision_ia.CerebroNeo') as ia, patch('vision_ia.ConexionNeo') as nao, \
             patch('vision_ia.escuchar') as micro, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(vision_ia.main(), 0)
        camara.assert_called_once_with('cv', 'mp', 'hands', '1')
        ia.assert_not_called()
        nao.assert_not_called()
        micro.assert_not_called()

    def test_identifica_importacion_y_causa_original(self):
        for modulo in ('cv2', 'mediapipe'):
            with self.subTest(modulo=modulo):
                def cargar(nombre):
                    if nombre == modulo:
                        raise ImportError('DETALLE_DE_LA_DEPENDENCIA')
                    return SimpleNamespace()
                with patch('vision_ia.importlib.import_module', side_effect=cargar):
                    with self.assertRaises(vision_ia.ErrorVision) as error:
                        vision_ia.cargar_dependencias()
                self.assertIn(modulo, str(error.exception))
                self.assertIn('DETALLE_DE_LA_DEPENDENCIA', str(error.exception))

    def test_detecta_mediapipe_sin_api_legacy_y_muestra_origen(self):
        mp = SimpleNamespace(__version__='VERSION_DE_PRUEBA', __file__='ruta_del_modulo_de_prueba')
        with patch('vision_ia.importlib.import_module', side_effect=[SimpleNamespace(), mp]):
            with self.assertRaises(vision_ia.ErrorVision) as error:
                vision_ia.cargar_dependencias()
        self.assertIn('VERSION_DE_PRUEBA', str(error.exception))
        self.assertIn('ruta_del_modulo_de_prueba', str(error.exception))
        self.assertIn('mp.solutions.hands.Hands', str(error.exception))

    def test_diagnostico_no_crea_ia_ni_conexion_robot(self):
        with patch.object(sys, 'argv', ['vision_ia.py', '--diagnostico']):
            with patch('vision_ia.cargar_dependencias', return_value=('cv', 'mp', 'hands')):
                with patch('vision_ia.diagnosticar', return_value=0) as diagnostico:
                    with patch('vision_ia.CerebroNeo') as ia, patch('vision_ia.ConexionNeo') as robot:
                        with contextlib.redirect_stdout(io.StringIO()):
                            self.assertEqual(vision_ia.main(), 0)
                        ia.assert_not_called()
                        robot.assert_not_called()
                        diagnostico.assert_called_once_with('cv', 'mp', 'hands')


class PruebasPreparador(unittest.TestCase):
    def test_reutiliza_venv_activo_windows_sin_sobrescribir_python(self):
        with tempfile.TemporaryDirectory() as t:
            destino = Path(t) / 'Proyecto con espacios' / '.venv_neo'
            ejecutable = destino / 'Scripts' / 'python.exe'
            ejecutable.parent.mkdir(parents=True)
            ejecutable.write_bytes(b'EJECUTABLE_DE_PRUEBA_BLOQUEADO')
            (destino / 'pyvenv.cfg').write_text('home = PYTHON_BASE_DE_PRUEBA\n')
            with patch('preparar_vision.sys.platform', 'win32'), \
                 patch('preparar_vision.sys.prefix', str(destino)), \
                 patch('preparar_vision.sys.executable', str(ejecutable)), \
                 patch('preparar_vision.venv.EnvBuilder', side_effect=PermissionError('No sobrescribir python.exe')) as crear, \
                 patch('preparar_vision.subprocess.run') as ejecutar, \
                 contextlib.redirect_stdout(io.StringIO()) as salida:
                self.assertEqual(preparar_vision.main(['--carpeta', str(destino), '--examen']), 0)
            crear.assert_not_called()
            self.assertEqual(ejecutable.read_bytes(), b'EJECUTABLE_DE_PRUEBA_BLOQUEADO')
            comandos = [c.args[0] for c in ejecutar.call_args_list]
            self.assertTrue(all(c[0] == str(ejecutable) for c in comandos))
            self.assertEqual(comandos[0][1:6], ['-m', 'pip', 'install', '--only-binary=:all:', '-r'])
            self.assertEqual(Path(comandos[0][-1]).name, 'requirements_examen.txt')
            self.assertIn('--diagnostico', comandos[2])
            self.assertEqual(comandos[-1][-1], '--solo-config')
            self.assertIn('Reutilizando el entorno existente', salida.getvalue())

    def test_primera_preparacion_todavia_crea_un_venv(self):
        with tempfile.TemporaryDirectory() as t:
            destino = Path(t) / '.venv_nuevo'
            with patch('preparar_vision.venv.EnvBuilder') as crear, \
                 patch('preparar_vision.subprocess.run'), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(preparar_vision.main(['--carpeta', str(destino)]), 0)
            crear.return_value.create.assert_called_once_with(destino)

    def test_error_incluye_el_detalle_del_sistema(self):
        with tempfile.TemporaryDirectory() as t:
            with patch('preparar_vision.venv.EnvBuilder', side_effect=PermissionError('ARCHIVO_BLOQUEADO_DE_PRUEBA')), \
                 patch('preparar_vision.subprocess.run') as ejecutar, \
                 contextlib.redirect_stdout(io.StringIO()) as salida:
                self.assertEqual(preparar_vision.main(['--carpeta', str(Path(t) / 'nuevo')]), 1)
            ejecutar.assert_not_called()
            self.assertIn('PermissionError', salida.getvalue())
            self.assertIn('ARCHIVO_BLOQUEADO_DE_PRUEBA', salida.getvalue())


if __name__ == '__main__':
    unittest.main()
