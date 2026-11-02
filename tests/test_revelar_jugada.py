"""Voz/pose con dobles de prueba; sin comandos al NAO ni consultas de pago."""
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from estado_juego import ANUNCIOS_JUGADA
from personalidad_naoqi import INVITACION_APRETON, JINGLE_VICTORIA
from robot_server_ia import Sesion
from voz_openai import ServicioVoz


class PruebasRevelado(unittest.TestCase):
    def test_pose_y_nombre_avanzan_en_paralelo_con_la_misma_jugada(self):
        voz_empezo, pose_empezo = threading.Event(), threading.Event()
        llamados = []
        def decir(texto):
            llamados.append(('voz', texto))
            voz_empezo.set()
            if not pose_empezo.wait(1):
                raise AssertionError('La pose debe comenzar mientras la voz esta activa')
        def mostrar(jugada):
            llamados.append(('pose', jugada))
            pose_empezo.set()
            if not voz_empezo.wait(1):
                raise AssertionError('La voz debe comenzar sin esperar a terminar la pose')
        conn = Mock()
        sesion = Sesion(conn, SimpleNamespace(decir=decir, mostrar=mostrar))
        sesion.revelar_jugada('piedra')
        self.assertCountEqual(llamados, [('voz', 'Piedra.'), ('pose', 'piedra')])
        estados = [json.loads(c.args[0]) for c in conn.sendall.call_args_list]
        self.assertEqual([e['active'] for e in estados if e['type'] == 'speaking'], [True, False])

    def test_fallos_de_voz_o_pose_se_propagan_y_liberan_el_estado_de_voz(self):
        for fallo in ('decir', 'mostrar'):
            with self.subTest(fallo=fallo):
                robot = Mock()
                getattr(robot, fallo).side_effect = RuntimeError('FALLO_SINTETICO_' + fallo)
                conn = Mock()
                sesion = Sesion(conn, robot)
                with self.assertRaisesRegex(RuntimeError, 'FALLO_SINTETICO'):
                    sesion.revelar_jugada('papel')
                estados = [json.loads(c.args[0]) for c in conn.sendall.call_args_list]
                self.assertFalse(estados[-1]['active'])

    def test_rechaza_gestos_ajenos_al_juego_antes_de_hablar_o_mover(self):
        robot = Mock()
        sesion = Sesion(Mock(), robot)
        with self.assertRaises(ValueError):
            sesion.revelar_jugada('comando_arbitrario')
        robot.decir.assert_not_called()
        robot.mostrar.assert_not_called()

    def test_cache_prepara_los_tres_anuncios_cortos_sin_abrir_el_sdk(self):
        lector = Mock()
        servicio = ServicioVoz(lector, puerto=0)
        try:
            servicio.preparar_cuenta(reintentos=0)
            for texto in ANUNCIOS_JUGADA.values():
                lector.sintetizar.assert_any_call(texto)
            lector.sintetizar.assert_any_call(INVITACION_APRETON)
            lector.sintetizar.assert_any_call(JINGLE_VICTORIA, estilo='cantado')
            self.assertEqual(lector.sintetizar.call_count, 7)
        finally:
            servicio.cerrar()


if __name__ == '__main__':
    unittest.main()
