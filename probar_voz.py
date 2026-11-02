"""Escucha la voz OpenAI en tu laptop, sin robot, camara ni consulta a Codex."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import wave

from voz_openai import (ErrorVoz, FRASE_PRUEBA, LectorOpenAI, MODELO, ReproductorPC,
                        TASA, VOCES, comprobar_biblioteca, obtener_clave)

CARPETA = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--solo-config', action='store_true', help='Comprueba biblioteca, sin API ni dispositivos.')
    parser.add_argument('--voz', choices=VOCES, default='marin')
    parser.add_argument('--texto', default=FRASE_PRUEBA)
    args = parser.parse_args(argv)
    try:
        comprobar_biblioteca()
        if args.solo_config:
            print('VOZ_OPENAI_CONFIG_OK: biblioteca disponible; no se comprobo clave, saldo, voz ni hardware.')
            return 0
        reproductor = ReproductorPC()
        reproductor.reproducir()  # Comprueba el dispositivo antes de generar audio de pago.
        clave = obtener_clave()
        print('Modelo {} | voz {} | una consulta de voz con saldo API.'.format(MODELO, args.voz), flush=True)
        lector = LectorOpenAI(clave, args.voz, registro=CARPETA / 'diagnosticos_locales' / 'voz_openai_uso.jsonl')
        pcm = lector.sintetizar(args.texto)
        carpeta = CARPETA / 'grabaciones'
        carpeta.mkdir(exist_ok=True)
        ruta = carpeta / 'neo_voz_openai.wav'
        with wave.open(str(ruta), 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(TASA)
            wav.writeframes(pcm)
        reproductor.reproducir(pcm)
        print('VOZ_OPENAI_REPRODUCIDA_PC. Confirma que la escuchaste. WAV local:', ruta)
        print('Esta prueba no contacto con el NAO ni cambio el modelo de conversacion.')
        return 0
    except (ErrorVoz, OSError, ValueError) as error:
        print('NO SE COMPLETO LA PRUEBA DE VOZ:', str(error))
        return 1
    except (EOFError, KeyboardInterrupt):
        print('\nPrueba de voz cancelada.')
        return 130


if __name__ == '__main__':
    sys.exit(main())
