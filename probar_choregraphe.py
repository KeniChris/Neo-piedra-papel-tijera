"""Lanza Python/NAOqi y el cliente Python 3 desde una sola terminal.

Usa una conexion REAL a NAOqi, como prueba.py; no es el modo --simular.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading

CARPETA = Path(__file__).resolve().parent


def localizar_python_naoqi(valor):
    ruta = Path(valor).expanduser()
    encontrado = str(ruta.resolve()) if ruta.is_file() else shutil.which(valor)
    if not encontrado:
        raise RuntimeError('No existe el interprete NAOqi: {}. Usa --python-naoqi RUTA_AL_PYTHON_DEL_SDK.'.format(valor))
    return encontrado


def puerto_libre(puerto):
    # Solo comprueba el puerto local del puente, no abre una sesion en el robot.
    with socket.socket() as prueba:
        try:
            prueba.bind(('127.0.0.1', puerto))
        except OSError:
            return False
    return True


def esperar_puente(proceso, timeout=15):
    listo = threading.Event()
    terminado = threading.Event()

    def mostrar_salida():
        try:
            for linea in proceso.stdout:
                if linea.strip() == 'PUENTE_LISTO':
                    listo.set()
                else:
                    print('[NAOqi] ' + linea.rstrip(), flush=True)
        except (OSError, ValueError):
            pass
        finally:
            proceso.stdout.close()
            terminado.set()

    lector = threading.Thread(target=mostrar_salida, daemon=True)
    lector.start()
    # La espera es corta y acotada; no contacta con otro robot ni busca puertos.
    import time
    fin = time.monotonic() + timeout
    while time.monotonic() < fin:
        if listo.wait(0.1):
            return True, lector
        if terminado.is_set() or proceso.poll() is not None:
            return False, lector
    return False, lector


def detener_puente(proceso):
    if proceso.poll() is None:
        proceso.terminate()
        try:
            proceso.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proceso.kill()
            proceso.wait(timeout=3)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--robot-ip', default='127.0.0.1')
    parser.add_argument('--robot-port', type=int, required=True,
                        help='Puerto que muestra Choregraphe en Preferences > Virtual Robot.')
    parser.add_argument('--python-naoqi', default=os.environ.get('NEO_PYTHON_NAOQI', r'C:\Python27\python.exe'))
    parser.add_argument('--puerto', type=int, default=5005, help='Puerto local del puente; distinto del puerto NAOqi.')
    parser.add_argument('--solo-conexion', action='store_true', help='Prueba ALTextToSpeech y termina, sin IA.')
    parser.add_argument('--vision', action='store_true', help='Abre vision_ia.py en vez de la conversacion por texto.')
    parser.add_argument('--microfono', action='store_true', help='Requiere --vision y SpeechRecognition/PyAudio.')
    parser.add_argument('--camara', default='0')
    parser.add_argument('--sin-comentarios', action='store_true')
    parser.add_argument('--movimientos', action='store_true', help='Activa los movimientos de la partida.')
    parser.add_argument('--rondas', type=int, choices=(3, 5), default=3)
    parser.add_argument('--espera', type=float, default=3.0)
    args = parser.parse_args(argv)
    if not all(1 <= x <= 65535 for x in (args.robot_port, args.puerto)):
        parser.error('Los puertos deben estar entre 1 y 65535.')
    if not 0.5 <= args.espera <= 10:
        parser.error('--espera debe estar entre 0.5 y 10 segundos.')
    if args.microfono and not args.vision:
        parser.error('--microfono se utiliza junto a --vision.')
    if args.solo_conexion and (args.vision or args.movimientos):
        parser.error('--solo-conexion solo comprueba la voz; omite --vision y --movimientos.')
    try:
        python_naoqi = localizar_python_naoqi(args.python_naoqi)
    except RuntimeError as error:
        print(error)
        return 1

    print('Conexion NAOqi real: {}:{}'.format(args.robot_ip, args.robot_port), flush=True)
    print('Python NAOqi:', python_naoqi, flush=True)
    print('Python del cliente:', sys.executable, flush=True)
    destino = ['--robot-ip', args.robot_ip, '--robot-port', str(args.robot_port)]
    try:
        comprobacion = subprocess.run(
            [python_naoqi, '-u', str(CARPETA / 'comprobar_naoqi.py')] + destino,
            cwd=str(CARPETA), timeout=20, check=False)
    except subprocess.TimeoutExpired:
        print('NAOqi no respondio en 20 segundos. Comprueba que Choregraphe este abierto y el puerto sea correcto.')
        return 1
    except OSError as error:
        print('No se pudo iniciar el Python de NAOqi:', error)
        return 1
    if comprobacion.returncode:
        return comprobacion.returncode
    if args.solo_conexion:
        return 0
    if not puerto_libre(args.puerto):
        print('El puerto local {} esta ocupado. Cierra el servidor anterior o elige --puerto 5006.'.format(args.puerto))
        return 1

    # Este lanzador es para las pruebas actuales con Codex y Luna. Se conserva
    # cualquier modelo que el usuario ya haya seleccionado explicitamente.
    entorno = os.environ.copy()
    # El cliente Python 3 usa sus paquetes instalados. El puente Python 2
    # conserva por separado el PYTHONPATH que pueda necesitar el SDK NAOqi.
    for nombre in ('PYTHONPATH', 'PYTHONHOME'):
        entorno.pop(nombre, None)
    entorno['NEO_IA_PROVIDER'] = 'codex'
    entorno['NEO_CODEX_MODEL'] = entorno.get('NEO_CODEX_MODEL') or 'gpt-6-luna'
    entorno_naoqi = os.environ.copy()
    # Python 2.7 usa ASCII al escribir a una tuberia si no se indica otra
    # codificacion. Los anuncios con "gané" o "tú" deben llegar completos.
    entorno_naoqi['PYTHONIOENCODING'] = 'utf-8'
    comando = [python_naoqi, '-u', str(CARPETA / 'robot_server_ia.py')] + destino
    comando += ['--puerto', str(args.puerto), '--rondas', str(args.rondas), '--espera', str(args.espera)]
    if args.movimientos:
        comando.append('--movimientos')
    puente = None
    lector = None
    try:
        puente = subprocess.Popen(comando, cwd=str(CARPETA), stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, encoding='utf-8', errors='replace',
                                  bufsize=1, env=entorno_naoqi)
        listo, lector = esperar_puente(puente)
        if not listo:
            print('El puente no llego a estar listo. Revisa los mensajes [NAOqi].')
            return 1
        if args.vision:
            cliente = [sys.executable, '-u', str(CARPETA / 'vision_ia.py'),
                       '--puerto', str(args.puerto), '--camara', args.camara]
            if args.microfono:
                cliente.append('--microfono')
            if args.sin_comentarios:
                cliente.append('--sin-comentarios')
        else:
            cliente = [sys.executable, '-u', str(CARPETA / 'conversar.py'),
                       '--robot', '--puerto', str(args.puerto)]
        print('Abriendo cliente con {}. Para terminar: salir en texto, Esc en video.'.format(
            entorno['NEO_CODEX_MODEL']), flush=True)
        return subprocess.call(cliente, cwd=str(CARPETA), env=entorno)
    except KeyboardInterrupt:
        print('\nPrueba interrumpida. Cerrando el puente de esta prueba.')
        return 130
    except OSError as error:
        print('No se pudo iniciar la prueba:', error)
        return 1
    finally:
        if puente is not None:
            detener_puente(puente)
            if lector is not None:
                lector.join(timeout=2)
            if puente.stdout is not None:
                puente.stdout.close()


if __name__ == '__main__':
    sys.exit(main())
