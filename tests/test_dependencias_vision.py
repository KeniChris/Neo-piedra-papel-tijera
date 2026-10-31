"""Diagnosticos con modulos de prueba; sin camara ni red."""
import contextlib
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import preparar_vision
import vision_ia


class PruebasDependenciasVision(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
