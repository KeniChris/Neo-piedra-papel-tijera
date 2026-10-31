"""Lanza Python/NAOqi y el cliente Python 3 desde una sola terminal.

Usa una conexion REAL a NAOqi, como prueba.py; no es el modo --simular.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import secrets
import socket
import subprocess
import sys
import threading
from sensores_cliente import ClienteSensores

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


def esperar_puente(proceso, timeout=15, marca='PUENTE_LISTO'):
    listo = threading.Event()
    terminado = threading.Event()

    def mostrar_salida():
        try:
            for linea in proceso.stdout:
                if linea.strip() == marca:
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
    parser.add_argument('--camara-nao', action='store_true')
    parser.add_argument('--microfono-nao', action='store_true')
    parser.add_argument('--indice-camara-nao', type=int, choices=(0, 1), default=0)
    parser.add_argument('--puerto-sensores', type=int, default=5006)
    parser.add_argument('--callback-ip')
    parser.add_argument('--callback-port', type=int, default=5007)
    parser.add_argument('--solo-diagnostico', action='store_true', help='Comprueba voz y fuentes elegidas sin iniciar la partida.')
    parser.add_argument('--saludo-ia', action='store_true')
    parser.add_argument('--sin-ia', action='store_true')
    parser.add_argument('--camara', default='0')
    parser.add_argument('--sin-comentarios', action='store_true')
    parser.add_argument('--movimientos', action='store_true', help='Activa los movimientos de la partida.')
    parser.add_argument('--rondas', type=int, choices=(3, 5), default=3)
    parser.add_argument('--espera', type=float, default=3.0)
    args = parser.parse_args(argv)
    if args.camara_nao or args.microfono_nao:
        args.vision = True
    if args.microfono_nao:
        args.microfono = True
    if not all(1 <= x <= 65535 for x in (args.robot_port, args.puerto, args.puerto_sensores, args.callback_port)):
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
    if not args.solo_diagnostico and not puerto_libre(args.puerto):
        print('El puerto local {} esta ocupado. Cierra el servidor anterior o elige otro puerto libre, '
              'distinto del de sensores y del callback.'.format(args.puerto))
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
    sensor = None
    lector_sensor = None
    cliente_sensores = None
    try:
        if args.camara_nao or args.microfono_nao:
            if not puerto_libre(args.puerto_sensores):
                print('Puerto local de sensores ocupado:', args.puerto_sensores)
                return 1
            token = secrets.token_hex(24)
            entorno_sensor = entorno_naoqi.copy()
            entorno_sensor['NEO_SENSORES_TOKEN'] = token
            entorno['NEO_SENSORES_TOKEN'] = token
            comando_sensor = [python_naoqi, '-u', str(CARPETA / 'sensores_nao.py')] + destino
            comando_sensor += ['--puerto', str(args.puerto_sensores), '--indice-camara', str(args.indice_camara_nao),
                               '--callback-port', str(args.callback_port)]
            if args.callback_ip:
                comando_sensor += ['--callback-ip', args.callback_ip]
            if not args.camara_nao:
                comando_sensor.append('--sin-camara')
            if not args.microfono_nao:
                comando_sensor.append('--sin-microfono')
            sensor = subprocess.Popen(comando_sensor, cwd=str(CARPETA), stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, encoding='utf-8', errors='replace',
                                      bufsize=1, env=entorno_sensor)
            listo_sensor, lector_sensor = esperar_puente(sensor, timeout=20, marca='SENSORES_LISTOS')
            if not listo_sensor:
                print('No se validaron los sensores NAO. Revisa FALLO SENSORES NAO. No se sustituyen por los del PC.')
                return 1
            cliente_sensores = ClienteSensores(args.puerto_sensores, token)
            estado_sensores = cliente_sensores.estado()
            print('SENSORES_NAO_OK:', json.dumps(estado_sensores, ensure_ascii=False), flush=True)
        else:
            estado_sensores = {'origen': 'pc', 'nota': 'No se probaron los sensores internos del NAO.'}
        carpeta_diagnostico = CARPETA / 'diagnosticos_locales'
        carpeta_diagnostico.mkdir(exist_ok=True)
        (carpeta_diagnostico / 'ultimo_examen.json').write_text(json.dumps({
            'robot_ip': args.robot_ip, 'robot_port': args.robot_port,
            'voz': {'servicio': 'ALTextToSpeech', 'solicitud_aceptada': True, 'audibilidad_confirmada': False},
            'sensores': estado_sensores}, ensure_ascii=False, indent=2), encoding='utf-8')
        if args.solo_diagnostico:
            print('DIAGNOSTICO_COMPLETADO. La audibilidad y la precision de reconocimiento requieren observar la prueba.')
            return 0
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
            if args.camara_nao:
                cliente += ['--fuente-camara', 'nao', '--puerto-sensores', str(args.puerto_sensores)]
            if args.microfono_nao:
                cliente += ['--fuente-microfono', 'nao']
                if not args.camara_nao:
                    cliente += ['--puerto-sensores', str(args.puerto_sensores)]
            if args.saludo_ia:
                cliente.append('--saludo-ia')
            if args.sin_ia:
                cliente.append('--sin-ia')
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
        if sensor is not None:
            if cliente_sensores:
                cliente_sensores.cerrar()
                try:
                    sensor.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
            detener_puente(sensor)
            if lector_sensor:
                lector_sensor.join(timeout=2)
            if sensor.stdout is not None:
                sensor.stdout.close()


if __name__ == '__main__':
    sys.exit(main())
