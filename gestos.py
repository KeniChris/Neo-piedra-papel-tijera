"""Clasificacion geometrica y estabilidad temporal; no requiere entrenamiento."""

import time

JUGADAS = ('piedra', 'papel', 'tijera')


class GestoEstable:
    """Confirma un gesto por tiempo y muestras, sin reutilizar otra captura."""
    def __init__(self, duracion=0.30, minimo_muestras=3, hueco_maximo=0.8):
        self.duracion = duracion
        self.minimo_muestras = minimo_muestras
        self.hueco_maximo = hueco_maximo
        self.reiniciar()

    def reiniciar(self):
        self.token = None
        self.gesto = None
        self.inicio = None
        self.ultimo = None
        self.muestras = 0

    def observar(self, gesto, token, ahora=None):
        ahora = time.monotonic() if ahora is None else ahora
        if token != self.token or (self.ultimo is not None and
                (ahora < self.ultimo or ahora - self.ultimo > self.hueco_maximo)):
            self.reiniciar()
        self.token = token
        self.ultimo = ahora
        if not token or gesto not in JUGADAS:
            self.gesto, self.inicio, self.muestras = None, None, 0
            return None
        if gesto != self.gesto:
            self.gesto, self.inicio, self.muestras = gesto, ahora, 1
        else:
            self.muestras += 1
        if self.muestras >= self.minimo_muestras and ahora - self.inicio >= self.duracion:
            return gesto
        return None

    def progreso(self, ahora=None):
        if self.inicio is None:
            return 0.0
        ahora = self.ultimo if ahora is None else ahora
        return min(1.0, max(0.0, (ahora - self.inicio) / self.duracion),
                   self.muestras / float(self.minimo_muestras))


def d(a, b):
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5


def dedos_extendidos(lm):
    muneca = lm[0]
    pares = [(8, 6), (12, 10), (16, 14), (20, 18)]
    return [d(lm[t], muneca) > d(lm[p], muneca) * 1.1 for t, p in pares]


def pulgar_extendido(lm):
    palma = d(lm[0], lm[9])
    sep = min(d(lm[4], lm[5]), d(lm[4], lm[9]))
    alejado = d(lm[4], lm[0]) > d(lm[3], lm[0]) * 1.05
    return sep > palma * 0.55 and alejado


def clasificar(lm):
    if len(lm) != 21:
        return None
    palma = d(lm[0], lm[9])
    if palma < 1e-6:
        return None
    i, m, a, p = dedos_extendidos(lm)
    if not (i or m or a or p):
        return None if pulgar_extendido(lm) else 'piedra'
    # El pulgar puede tocar el indice en un puno normal. La guarda de
    # pinza solo aplica despues de comprobar los cuatro dedos doblados.
    if d(lm[4], lm[8]) < palma * 0.35:
        return None
    if i and m and a and p:
        return 'papel'
    if i and m and not a and not p:
        return 'tijera'
    return None
