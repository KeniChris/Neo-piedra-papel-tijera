# -*- coding: utf-8 -*-
"""Inicializa la conexion del SDK. Compatible con Python 2.7 y Python 3."""
from __future__ import print_function, unicode_literals

import argparse
import struct
import sys

from naoqi_compat import cadena_naoqi

FALLO_DESTINO = 70


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--robot-ip', required=True)
    parser.add_argument('--robot-port', type=int, required=True)
    parser.add_argument('--voz', choices=('nao_tts', 'openai'), default='nao_tts')
    args = parser.parse_args()
    print('SDK NAOqi: Python {} | {} bits'.format(sys.version.split()[0], struct.calcsize(b'P') * 8))
    try:
        from naoqi import ALProxy
    except ImportError:
        print('No se puede importar naoqi con este interprete. Configura python_naoqi con el Python del SDK.')
        return 1
    salida = None
    try:
        if args.voz == 'openai':
            from audio_neo import SalidaAudioNAO
            salida = SalidaAudioNAO(args.robot_ip, args.robot_port)
        else:
            ALProxy(cadena_naoqi('ALTextToSpeech'), cadena_naoqi(args.robot_ip), args.robot_port)
        print('NAO conectado en {}:{}'.format(args.robot_ip, args.robot_port))
        return 0
    except Exception as error:
        print('No se pudo conectar con NAOqi: {}: {}'.format(type(error).__name__, error))
        return FALLO_DESTINO
    finally:
        if salida is not None:
            salida.cerrar()


if __name__ == '__main__':
    sys.exit(main())
