# -*- coding: utf-8 -*-
"""Agente local de estrategia mixta; compatible con Python 2.7 y Python 3."""
from __future__ import unicode_literals

from collections import Counter
import random

JUGADAS = ('piedra', 'papel', 'tijera')
VENCE_A = {'piedra': 'tijera', 'papel': 'piedra', 'tijera': 'papel'}


class AgenteJugada(object):
    """Usa solo rondas humanas ya confirmadas; nunca recibe la mano actual."""
    def __init__(self, azar=None):
        self.azar = azar or random.SystemRandom()
        self.historial = []

    def reiniciar(self):
        self.historial = []

    def observar(self, jugada):
        if jugada not in JUGADAS:
            raise ValueError('Jugada observada no valida')
        self.historial = (self.historial + [jugada])[-12:]

    def pesos(self):
        conteos = Counter(self.historial)
        # Las transiciones solo influyen si hay al menos dos precedentes.
        if self.historial:
            ultima = self.historial[-1]
            siguientes = [b for a, b in zip(self.historial, self.historial[1:]) if a == ultima]
            if len(siguientes) >= 2:
                conteos = Counter(siguientes)
        total = float(sum(conteos.values()) + 3)
        # Suavizado + 50% de exploracion: ninguna jugada queda descartada.
        return dict((j, 0.5 / 3 + 0.5 * (conteos[VENCE_A[j]] + 1) / total)
                    for j in JUGADAS)

    def elegir(self, opciones=JUGADAS):
        if tuple(opciones) != JUGADAS:
            raise ValueError('Opciones del agente no validas')
        punto, acumulado = self.azar.random(), 0.0
        pesos = self.pesos()
        for jugada in JUGADAS:
            acumulado += pesos[jugada]
            if punto < acumulado:
                return jugada
        return JUGADAS[-1]
