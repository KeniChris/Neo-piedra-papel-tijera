"""Mute y boton con estado local y GUI falsa; sin microfonos ni ventanas reales."""
import contextlib
import io
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cliente_neo import ConexionNeo
from vision_ia import alternar_microfono, crear_boton_microfono, descartar_audio_pc


def conexion_local():
    conexion = ConexionNeo.__new__(ConexionNeo)
    conexion.lock = threading.RLock()
    conexion.hablando = False
    conexion.microfono_silenciado = False
    conexion.voice_generation = 0
    conexion.mute_until = 0
    return conexion


class PruebasMute(unittest.TestCase):
    def test_mute_invalida_audio_pendiente_incluso_tras_reactivar(self):
        c = conexion_local()
        with patch('cliente_neo.time.monotonic', return_value=10):
            anterior, libre = c.voz_token()
            self.assertTrue(libre)
            self.assertTrue(c.alternar_microfono())
            self.assertFalse(c.voz_token()[1])
            self.assertFalse(c.voz_valida(anterior))
            self.assertFalse(c.alternar_microfono())
            self.assertFalse(c.voz_token()[1])  # Margen para vaciar audio anterior.
        with patch('cliente_neo.time.monotonic', return_value=11):
            actual, libre = c.voz_token()
            self.assertTrue(libre)
            self.assertTrue(c.voz_valida(actual))
            self.assertFalse(c.voz_valida(anterior))
            c.hablando = True
            self.assertFalse(c.voz_token()[1])
            self.assertFalse(c.voz_valida(actual))

    def test_boton_clic_y_tecla_comparten_el_estado_del_microfono(self):
        c, cv2 = conexion_local(), Mock(EVENT_LBUTTONDOWN=1)
        area = crear_boton_microfono(cv2, 'VENTANA_FALSA', c, True)
        area['rect'] = (100, 100, 330, 140)
        clic = cv2.setMouseCallback.call_args.args[1]
        with contextlib.redirect_stdout(io.StringIO()):
            clic(1, 101, 101, None, None)
            self.assertTrue(c.microfono_silenciado)
            clic(1, 1, 1, None, None)
            self.assertTrue(c.microfono_silenciado)
            self.assertFalse(alternar_microfono(c))
            area['habilitado'] = False
            clic(1, 101, 101, None, None)
            self.assertFalse(c.microfono_silenciado)

    def test_descarta_audio_pc_acumulado_al_reanudar(self):
        stream = Mock(pyaudio_stream=Mock(get_read_available=Mock(return_value=800)))
        descartar_audio_pc(SimpleNamespace(stream=stream))
        stream.read.assert_called_once_with(800)
        stream.reset_mock()
        stream.pyaudio_stream.get_read_available.return_value = 0
        descartar_audio_pc(SimpleNamespace(stream=stream))
        stream.read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
