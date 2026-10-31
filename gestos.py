"""Geometria del vision.py recibido, con proteccion para una palma degenerada."""


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
    if d(lm[4], lm[8]) < palma * 0.35:
        return None
    if not (i or m or a or p):
        return None if pulgar_extendido(lm) else 'piedra'
    if i and m and a and p:
        return 'papel'
    if i and m and not a and not p:
        return 'tijera'
    return None
