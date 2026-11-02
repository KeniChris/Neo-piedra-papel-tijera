"""Regresiones geometricas con landmarks sinteticos; no equivalen a validar una webcam."""
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gestos import GestoEstable, clasificar, d


def mano(extendidos=(), pulgar_arriba=False):
    puntos = [(0, 0)] * 21
    puntos[1:5] = [(-.35, -.2), (-.55, -.45), (-.45, -.65), (-.25, -.72)]
    for indice, x in zip((5, 9, 13, 17), (-.35, 0, .3, .55)):
        puntos[indice] = (x, -.8 if indice != 9 else -1)
        puntos[indice + 1] = (x, -1.3)
        puntos[indice + 2] = (x + .03, -1.7 if indice in extendidos else -.96)
        puntos[indice + 3] = (x + .08, -2 if indice in extendidos else -.72)
    if pulgar_arriba:
        puntos[4] = (-.7, -1.9)
    # Coordenadas normalizadas dentro del encuadre.
    return [SimpleNamespace(x=.5 + x * .15, y=.7 + y * .15, z=0) for x, y in puntos]


class PruebasGeometria(unittest.TestCase):
    def test_puno_con_pulgar_junto_al_indice_es_piedra(self):
        lm = mano()
        self.assertLess(d(lm[4], lm[8]), d(lm[0], lm[9]) * .35)
        self.assertEqual(clasificar(lm), 'piedra')

    def test_papel_tijera_y_gestos_fuera_del_juego(self):
        self.assertEqual(clasificar(mano((5, 9, 13, 17))), 'papel')
        self.assertEqual(clasificar(mano((5, 9))), 'tijera')
        self.assertIsNone(clasificar(mano((5,))))
        self.assertIsNone(clasificar(mano(pulgar_arriba=True)))
        self.assertIsNone(clasificar([]))
        self.assertIsNone(clasificar([SimpleNamespace(x=0, y=0)] * 21))

    def test_geometria_conserva_resultados_al_girar_espejar_y_cambiar_escala(self):
        for dedos, esperado in [((), 'piedra'), ((5, 9), 'tijera'), ((5, 9, 13, 17), 'papel')]:
            for grados in (0, 45, 90, 180):
                for espejo in (-1, 1):
                    angulo = math.radians(grados)
                    lm = [SimpleNamespace(x=2 * (espejo * p.x * math.cos(angulo) - p.y * math.sin(angulo)),
                                          y=2 * (espejo * p.x * math.sin(angulo) + p.y * math.cos(angulo)))
                          for p in mano(dedos)]
                    self.assertEqual(clasificar(lm), esperado)


class PruebasEstabilidad(unittest.TestCase):
    def test_tres_frames_rapidos_no_bastan_sin_tiempo_estable(self):
        filtro = GestoEstable()
        for t in (0, .01, .02):
            self.assertIsNone(filtro.observar('piedra', 'a', t))
        self.assertEqual(filtro.observar('piedra', 'a', .31), 'piedra')

    def test_a_cinco_fps_confirma_sin_exigir_seis_fotogramas(self):
        filtro = GestoEstable()
        self.assertIsNone(filtro.observar('piedra', 'a', 0))
        self.assertIsNone(filtro.observar('piedra', 'a', .2))
        self.assertEqual(filtro.observar('piedra', 'a', .4), 'piedra')
        self.assertEqual(filtro.progreso(), 1)

    def test_reintento_perdida_de_mano_cambio_y_hueco_reinician_la_confirmacion(self):
        for gesto, token, t in [('piedra', 'b', .5), (None, 'a', .5),
                                ('papel', 'a', .5), ('piedra', 'a', 2)]:
            with self.subTest(gesto=gesto, token=token, t=t):
                filtro = GestoEstable()
                for tiempo in (0, .2, .4):
                    filtro.observar('piedra', 'a', tiempo)
                self.assertIsNone(filtro.observar(gesto, token, t))
                self.assertLess(filtro.progreso(), 1)


if __name__ == '__main__':
    unittest.main()
