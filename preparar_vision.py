"""Prepara un entorno local para vision sin modificar el Python del SDK NAOqi."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import struct
import subprocess
import sys
import venv

CARPETA = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--carpeta', type=Path, default=CARPETA / '.venv_neo')
    parser.add_argument('--examen', action='store_true', help='Incluye transcripcion del audio recibido del NAO.')
    args = parser.parse_args(argv)
    if not (3, 10) <= sys.version_info[:2] <= (3, 12) or struct.calcsize('P') != 8:
        print('Prepara esta version con Python 3.11 de 64 bits, como el de tu terminal actual.')
        return 1
    destino = args.carpeta.resolve()
    if destino.exists() and (not destino.is_dir() or
            (any(destino.iterdir()) and not (destino / 'pyvenv.cfg').exists())):
        print('La carpeta elegida contiene otros archivos y no es un entorno virtual. Elige otra con --carpeta.')
        return 1
    print('Python de origen:', sys.executable, flush=True)
    print('Preparando entorno de vision en:', destino, flush=True)
    python_vision = destino / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    entorno = os.environ.copy()
    for nombre in ('PYTHONPATH', 'PYTHONHOME'):
        entorno.pop(nombre, None)
    try:
        venv.EnvBuilder(with_pip=True, clear=False).create(destino)
        requisitos = 'requirements_examen.txt' if args.examen else 'requirements_vision.txt'
        subprocess.run([str(python_vision), '-m', 'pip', 'install', '--only-binary=:all:',
                        '-r', str(CARPETA / requisitos)], check=True, env=entorno)
        subprocess.run([str(python_vision), '-m', 'pip', 'check'], check=True, env=entorno)
        subprocess.run([str(python_vision), str(CARPETA / 'vision_ia.py'), '--diagnostico'],
                       cwd=str(CARPETA), check=True, env=entorno)
        if args.examen:
            subprocess.run([str(python_vision), '-c',
                            'import speech_recognition as sr; print("TRANSCRIPCION_OK:", sr.__version__)'],
                           check=True, env=entorno)
    except (OSError, subprocess.CalledProcessError) as error:
        print('No se completo la preparacion:', type(error).__name__)
        print('Conserva el error de instalacion o diagnostico que aparece arriba.')
        return 1
    except KeyboardInterrupt:
        print('\nPreparacion interrumpida. Puedes ejecutar de nuevo el mismo comando.')
        return 130
    print('Entorno de vision listo. Usa ese mismo Python para lanzar la prueba.')
    if args.examen:
        print('Siguiente paso: usa ese Python con iniciar_examen.py --verificar-config')
    elif sys.platform == 'win32':
        print('& "{}" probar_choregraphe.py --robot-ip 127.0.0.1 --robot-port 61778 --vision'.format(python_vision))
    else:
        print(str(python_vision) + ' probar_choregraphe.py --robot-port PUERTO_ACTUAL --vision')
    return 0


if __name__ == '__main__':
    sys.exit(main())
