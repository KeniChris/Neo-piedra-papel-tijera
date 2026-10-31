# -*- coding: utf-8 -*-
"""Reglas deterministas. Compatible con Python 2.7 y Python 3."""
from __future__ import unicode_literals

import copy
import random
import re

JUGADAS = ('piedra', 'papel', 'tijera')
GANA = set([('piedra', 'tijera'), ('papel', 'piedra'), ('tijera', 'papel')])
ACCIONES = ('hablar', 'iniciar', 'pausar', 'continuar', 'reglas', 'marcador')


def texto_hablable(texto, limite=280):
    """Texto plano: quita etiquetas de control de la voz NAOqi."""
    if not isinstance(texto, type('')):
        try:
            texto = texto.decode('utf-8', 'replace')
        except (AttributeError, UnicodeError):
            return ''
    texto = re.sub(r'\\[^\\]*\\', ' ', texto)
    texto = texto.replace('\\', ' ').replace('<', ' ').replace('>', ' ')
    texto = re.sub(r'[\x00-\x1f\x7f]', ' ', texto)
    return ' '.join(texto.split())[:limite].strip()


class EstadoJuego(object):
    def __init__(self, rondas=3, elegir=None):
        if rondas not in (3, 5):
            raise ValueError('La partida debe tener 3 o 5 rondas validas.')
        self.elegir = elegir or random.choice
        self.max_rondas = rondas
        self.fase = 'esperando'
        self.version = 0
        self.partida = 0
        self.completadas = 0
        self.marcador = {'neo': 0, 'jugador': 0}
        self.ultima_ronda = None
        self.motivo_pausa = None
        self._jugada_neo = None
        self._intento = 0
        self.capture_id = None

    def cambiar_fase(self, fase):
        self.fase = fase
        self.version += 1
        if fase != 'capturando':
            self.capture_id = None

    def iniciar(self):
        if self.fase not in ('esperando', 'terminada'):
            return False
        self.partida += 1
        self.completadas = 0
        self.marcador = {'neo': 0, 'jugador': 0}
        self.ultima_ronda = None
        self.motivo_pausa = None
        self._jugada_neo = None
        self.cambiar_fase('entre_rondas')
        return True

    def preparar_ronda(self):
        if self.fase not in ('entre_rondas', 'pausa'):
            return False
        if self.completadas >= self.max_rondas:
            return False
        # Elegida ANTES de recibir el gesto humano. Se conserva al reintentar.
        if self._jugada_neo is None:
            self._jugada_neo = self.elegir(JUGADAS)
            if self._jugada_neo not in JUGADAS:
                raise ValueError('Eleccion del robot no valida')
        self.motivo_pausa = None
        self.cambiar_fase('cuenta_atras')
        return True

    def abrir_captura(self):
        if self.fase != 'cuenta_atras':
            return None
        self._intento += 1
        self.cambiar_fase('capturando')
        self.capture_id = '{}:{}:{}'.format(self.partida, self.completadas + 1, self._intento)
        return self.capture_id

    def pausar(self, motivo='peticion_jugador'):
        if self.fase in ('esperando', 'terminada'):
            return False
        self.motivo_pausa = motivo
        self.cambiar_fase('pausa')
        return True

    def registrar(self, humano, capture_id):
        if (self.fase != 'capturando' or capture_id != self.capture_id
                or humano not in JUGADAS):
            return None
        robot = self._jugada_neo
        if humano == robot:
            resultado = 'empate'
        elif (humano, robot) in GANA:
            resultado = 'jugador'
            self.marcador['jugador'] += 1
        else:
            resultado = 'neo'
            self.marcador['neo'] += 1
        self.completadas += 1
        self.ultima_ronda = {'numero': self.completadas, 'jugador': humano,
                             'neo': robot, 'ganador': resultado}
        self._jugada_neo = None
        self.cambiar_fase('terminada' if self.completadas >= self.max_rondas else 'entre_rondas')
        return copy.deepcopy(self.ultima_ronda)

    def permite_agente(self, version, accion):
        if (isinstance(version, bool) or not isinstance(version, int)
                or version != self.version or accion not in ACCIONES):
            return False
        if self.fase not in ('esperando', 'entre_rondas', 'pausa', 'terminada'):
            return False
        if accion == 'iniciar':
            return self.fase in ('esperando', 'terminada')
        if accion == 'continuar':
            return self.fase in ('entre_rondas', 'pausa')
        if accion == 'pausar':
            return self.fase in ('entre_rondas', 'pausa')
        return True

    def snapshot(self):
        return {'version': self.version, 'partida': self.partida, 'fase': self.fase,
                'rondas_totales': self.max_rondas, 'rondas_completadas': self.completadas,
                'marcador': dict(self.marcador), 'ultima_ronda': copy.deepcopy(self.ultima_ronda),
                'motivo_pausa': self.motivo_pausa, 'capture_id': self.capture_id}

    def frase_marcador(self):
        return 'Marcador: Neo {}, jugador {}. Llevamos {} de {} rondas.'.format(
            self.marcador['neo'], self.marcador['jugador'], self.completadas, self.max_rondas)

    def frase_final(self):
        if self.marcador['neo'] > self.marcador['jugador']:
            return 'Terminó la partida. Ganó Neo.'
        if self.marcador['jugador'] > self.marcador['neo']:
            return 'Terminó la partida. Ganó el jugador. Felicidades.'
        return 'Terminó la partida. Quedamos empatados.'
