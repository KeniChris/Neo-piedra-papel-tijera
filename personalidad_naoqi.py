# -*- coding: utf-8 -*-
"""Nombre y dialogos del controlador. Compatible con Python 2.7 y Python 3."""
from __future__ import unicode_literals

NOMBRE = 'Naoqi'
FRASE_PRUEBA = 'Estoy listo para jugar.'
SALUDO = 'Soy Naoqi. No me vas a ganar tan fácil. Di empezar y lo comprobamos.'
INVITACION_APRETON = ('Me ganaste. Mi orgullo necesita reiniciarse, pero primero dame la mano. '
                      'Buen duelo, rival.')
JINGLE_VICTORIA = 'Gané, gané, Naoqi está de pie. Buen rival, revancha otra vez.'
TIEMPO_APRETON = 10.0

COMENTARIOS = {
    'neo': ('Gané esta ronda. Mi modestia vuelve en unos segundos.',
            'Punto para mí. Esa jugada venía con actualización incluida.',
            'Gané esta ronda. Estoy intentando no presumir, sin mucho éxito.'),
    'jugador': ('Ganaste esta ronda. Mi revancha ya esta cargando.',
                'Buen punto. Mi ego robótico acaba de pedir soporte técnico.',
                'Ganaste esta ronda. Acepto la derrota parcial con elegancia digital.'),
    'empate': ('Empatamos. Estamos compartiendo la misma neurona estratégica.',
               'Empate. Hasta para llevarme la contraria me copias.',
               'Empatamos. Esto parece un duelo de espejos.')
}


def comentario_ronda(ganador, numero):
    frases = COMENTARIOS[ganador]
    return frases[(numero - 1) % len(frases)]
