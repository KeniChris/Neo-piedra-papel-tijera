"""Instala las dependencias de Naoqi en .venv_neo."""
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
    args = parser.parse_args(argv)
    if not (3, 10) <= sys.version_info[:2] <= (3, 12) or struct.calcsize('P') != 8:
        print('Usa Python 3.11 de 64 bits para instalar Naoqi.')
        return 1
    destino = args.carpeta.resolve()
    if destino.exists() and (not destino.is_dir() or
            (any(destino.iterdir()) and not (destino / 'pyvenv.cfg').exists())):
        print('La carpeta contiene archivos ajenos a un entorno virtual.')
        return 1
    python = destino / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    entorno = os.environ.copy()
    for nombre in ('PYTHONPATH', 'PYTHONHOME'):
        entorno.pop(nombre, None)
    try:
        if (destino / 'pyvenv.cfg').is_file() and python.is_file():
            print('Actualizando el entorno existente:', destino, flush=True)
        elif destino == Path(sys.prefix).resolve():
            print('El entorno activo esta incompleto. Elige otra carpeta con --carpeta.')
            return 1
        else:
            venv.EnvBuilder(with_pip=True, clear=False).create(destino)
        subprocess.run([str(python), '-m', 'pip', 'install', '--only-binary=:all:',
            '-r', str(CARPETA / 'requirements.txt')], check=True, env=entorno)
        subprocess.run([str(python), '-m', 'pip', 'check'], check=True, env=entorno)
        codigo = ('from vision_ia import cargar_dependencias, validar_dependencias; '
                  'from voz_openai import comprobar_biblioteca; '
                  'import speech_recognition; comprobar_biblioteca(); '
                  'raise SystemExit(validar_dependencias(*cargar_dependencias()))')
        subprocess.run([str(python), '-c', codigo], cwd=str(CARPETA), check=True, env=entorno)
    except (OSError, subprocess.CalledProcessError) as error:
        print('No se completo la instalacion:', str(error))
        return 1
    except KeyboardInterrupt:
        print('\nInstalacion interrumpida.')
        return 130
    print('Naoqi instalado. Ejecuta jugar.py con el Python de .venv_neo.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
