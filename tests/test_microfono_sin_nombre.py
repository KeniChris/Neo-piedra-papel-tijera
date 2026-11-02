"""Entrada de voz con reconocedor y microfonos falsos; sin audio ni red reales."""
import contextlib
import io
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vision_ia
from cliente_neo import procesar_texto


class PruebasMicrofonoSinNombre(unittest.TestCase):
    def escuchar(self, texto, origen='pc', rechazar=None):
        conexion = SimpleNamespace(closed=threading.Event(), comando=Mock(),
                                   voz_token=Mock(return_value=(7, True)),
                                   voz_valida=Mock(return_value=True))
        if rechazar == 'antes_transcripcion':
            conexion.voz_valida.side_effect = [True, False]
        elif rechazar == 'despues_transcripcion':
            conexion.voz_valida.side_effect = [True, True, False]
        conversador = Mock()
        conexion.comando.side_effect = lambda _: conexion.closed.set()
        conversador.pedir.side_effect = lambda _: conexion.closed.set() or True
        reconocedor = Mock()
        # Una segunda escucha denuncia que la primera peticion fue ignorada.
        reconocedor.listen.side_effect = [object(), AssertionError('La frase no se proceso')]
        reconocedor.recognize_google.return_value = texto
        if rechazar == 'antes_transcripcion':
            reconocedor.listen.side_effect = lambda *a, **k: conexion.closed.set() or object()
        elif rechazar == 'despues_transcripcion':
            reconocedor.recognize_google.side_effect = lambda *a, **k: conexion.closed.set() or texto
        fuente = Mock()
        fuente.__enter__ = Mock(return_value=fuente)
        fuente.__exit__ = Mock(return_value=False)
        sr = SimpleNamespace(Recognizer=lambda: reconocedor, Microphone=lambda: fuente,
                             WaitTimeoutError=type('EsperaFalsa', (Exception,), {}),
                             UnknownValueError=type('TranscripcionFalsa', (Exception,), {}),
                             RequestError=type('RedFalsa', (Exception,), {}))
        with patch.dict(sys.modules, {'speech_recognition': sr}):
            with patch('vision_ia.ClienteSensores'), patch('vision_ia.fuente_audio_nao', return_value=fuente):
                with contextlib.redirect_stdout(io.StringIO()):
                    vision_ia.escuchar_fuente(conexion, conversador, origen, 5006, {})
        return conexion, conversador, reconocedor

    def test_preguntas_del_microfono_pc_y_nao_se_envian_sin_nombrar_al_robot(self):
        for origen in ('pc', 'nao'):
            with self.subTest(origen=origen):
                conexion, conversador, reconocedor = self.escuchar('Cuentame una broma', origen)
                conversador.pedir.assert_called_once_with('Cuentame una broma')
                conexion.comando.assert_not_called()
                reconocedor.recognize_google.assert_called_once()

    def test_comando_de_juego_por_audio_sigue_sin_consultar_la_ia(self):
        conexion, conversador, _ = self.escuchar('siguiente')
        conexion.comando.assert_called_once_with('continuar')
        conversador.pedir.assert_not_called()

    def test_audio_invalidado_por_voz_del_robot_no_se_transcribe_ni_procesa(self):
        conexion, conversador, reconocedor = self.escuchar('Soy Naoqi', rechazar='antes_transcripcion')
        reconocedor.recognize_google.assert_not_called()
        conexion.comando.assert_not_called()
        conversador.pedir.assert_not_called()

    def test_transcripcion_tardia_invalidada_por_voz_del_robot_no_se_procesa(self):
        conexion, conversador, reconocedor = self.escuchar('Soy Naoqi', rechazar='despues_transcripcion')
        reconocedor.recognize_google.assert_called_once()
        conexion.comando.assert_not_called()
        conversador.pedir.assert_not_called()

    def test_entrada_vacia_no_solicita_una_respuesta(self):
        conexion, conversador = Mock(), Mock()
        self.assertFalse(procesar_texto('   ... ', conexion, conversador))
        conexion.comando.assert_not_called()
        conversador.pedir.assert_not_called()


if __name__ == '__main__':
    unittest.main()
