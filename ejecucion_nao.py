"""Coordina los procesos del juego y libera sus recursos al salir."""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time

from conexion_naoqi import FALLO_DESTINO
from sensores_cliente import ClienteSensores
from voz_openai import (ErrorVoz, LectorOpenAI, ServicioVoz, comprobar_biblioteca,
                        entorno_sin_claves_api, obtener_clave)

CARPETA = Path(__file__).resolve().parent


def localizar_python_naoqi(valor):
    ruta = Path(valor).expanduser()
    encontrado = str(ruta.resolve()) if ruta.is_file() else shutil.which(valor)
    if not encontrado:
        raise RuntimeError('No existe el Python del SDK NAOqi: ' + valor)
    return encontrado


def puerto_libre(puerto):
    with socket.socket() as conexion:
        try:
            conexion.bind(('127.0.0.1', puerto))
            return True
        except OSError:
            return False


def esperar_puente(proceso, timeout=15, marca='PUENTE_LISTO'):
    listo, terminado = threading.Event(), threading.Event()
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
    fin = time.monotonic() + timeout
    while time.monotonic() < fin:
        if listo.wait(.1):
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


def ejecutar(config, sin_ia=False):
    python_naoqi = localizar_python_naoqi(config['python_naoqi'])
    necesita_sensores = config['camara'] == 'nao' or config['microfono'] == 'nao'
    puertos_locales = [('control', config['puerto_control'])]
    if necesita_sensores:
        puertos_locales += [('sensores', config['puerto_sensores']), ('callback', config['callback_port'])]
    if config['voz'] == 'openai':
        puertos_locales.append(('voz', config['puerto_voz']))
    for nombre, puerto in puertos_locales:
        if not puerto_libre(puerto):
            print('Puerto local de {} ocupado: {}. Cierra la sesion anterior o cambia la configuracion.'.format(nombre, puerto))
            return 1
    entorno_naoqi = entorno_sin_claves_api(os.environ)
    entorno_naoqi['PYTHONIOENCODING'] = 'utf-8'
    puerto_robot = None
    for puerto in [config['robot_port']] + [p for p in config['puertos_alternativos'] if p != config['robot_port']]:
        destino = ['--robot-ip', config['robot_ip'], '--robot-port', str(puerto)]
        try:
            respuesta = subprocess.run([python_naoqi, '-u', str(CARPETA / 'conexion_naoqi.py')] +
                destino + ['--voz', config['voz']], cwd=str(CARPETA), timeout=20,
                check=False, env=entorno_naoqi)
        except subprocess.TimeoutExpired:
            print('NAOqi no respondio en el puerto {}.'.format(puerto))
            continue
        if respuesta.returncode == 0:
            puerto_robot = puerto
            break
        if respuesta.returncode != FALLO_DESTINO:
            return respuesta.returncode
    if puerto_robot is None:
        print('No se pudo conectar con el robot. Revisa su IP, puerto y conexion de red.')
        return FALLO_DESTINO
    destino = ['--robot-ip', config['robot_ip'], '--robot-port', str(puerto_robot)]
    entorno = entorno_sin_claves_api(os.environ)
    for nombre in ('PYTHONPATH', 'PYTHONHOME'):
        entorno.pop(nombre, None)
    entorno['NEO_IA_PROVIDER'] = 'codex'
    entorno['NEO_CODEX_MODEL'] = config['modelo_codex']
    puente = sensor = lector = lector_sensor = cliente_sensores = servicio_voz = None
    camara, microfono = config['camara'], config['microfono']
    try:
        if necesita_sensores:
            token = secrets.token_hex(24)
            entorno_sensor = dict(entorno_naoqi, NEO_SENSORES_TOKEN=token)
            entorno['NEO_SENSORES_TOKEN'] = token
            comando_sensor = [python_naoqi, '-u', str(CARPETA / 'sensores_nao.py')] + destino + [
                '--puerto', str(config['puerto_sensores']), '--indice-camara', str(config['indice_camara_nao']),
                '--callback-port', str(config['callback_port'])]
            if config['callback_ip']:
                comando_sensor += ['--callback-ip', config['callback_ip']]
            if camara != 'nao':
                comando_sensor.append('--sin-camara')
            if microfono != 'nao':
                comando_sensor.append('--sin-microfono')
            if config['respaldo_pc']:
                comando_sensor.append('--tolerar-fallos')
            sensor = subprocess.Popen(comando_sensor, cwd=str(CARPETA), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', bufsize=1, env=entorno_sensor)
            listo, lector_sensor = esperar_puente(sensor, timeout=20, marca='SENSORES_LISTOS')
            if not listo:
                print('No se pudo iniciar el servicio de sensores.')
                return 1
            cliente_sensores = ClienteSensores(config['puerto_sensores'], token)
            estado = cliente_sensores.estado()
            if config['respaldo_pc']:
                if camara == 'nao' and not estado.get('camara', {}).get('activa'):
                    camara = 'pc'
                    print('Camara: usando la laptop.')
                if microfono == 'nao' and not estado.get('microfono'):
                    microfono = 'pc'
                    print('Microfono: usando la laptop.')
        if config['voz'] == 'openai':
            comprobar_biblioteca()
            lector_voz = LectorOpenAI(obtener_clave(), config['voz_openai'],
                registro=CARPETA / 'registros_locales' / 'voz_openai_uso.jsonl')
            servicio_voz = ServicioVoz(lector_voz, config['puerto_voz'], salida='nao')
            entorno_naoqi['NEO_VOZ_TOKEN'] = servicio_voz.token
            print('Voz OpenAI: {} | altavoces NAO | utiliza saldo API.'.format(config['voz_openai']))
            servicio_voz.preparar_cuenta(config['reintentos_captura'])
        comando = [python_naoqi, '-u', str(CARPETA / 'robot_server_ia.py')] + destino + [
            '--puerto', str(config['puerto_control']), '--rondas', str(config['rondas']),
            '--espera', str(config['espera_jugada_seg']), '--reintentos', str(config['reintentos_captura']),
            '--voz', config['voz'], '--puerto-voz', str(config['puerto_voz'])]
        if config['movimientos']:
            comando.append('--movimientos')
        puente = subprocess.Popen(comando, cwd=str(CARPETA), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, encoding='utf-8', errors='replace', bufsize=1, env=entorno_naoqi)
        listo, lector = esperar_puente(puente)
        if not listo:
            print('No se pudo iniciar el puente del juego.')
            return 1
        cliente = [sys.executable, '-u', str(CARPETA / 'vision_ia.py'),
            '--puerto', str(config['puerto_control']), '--camara', config['camara_pc'],
            '--fuente-camara', camara, '--fuente-microfono', 'nao' if microfono == 'nao' else 'pc',
            '--puerto-sensores', str(config['puerto_sensores'])]
        if microfono != 'no':
            cliente.append('--microfono')
        if config['respaldo_pc']:
            cliente.append('--respaldo-pc')
        if sin_ia:
            cliente.append('--sin-ia')
        print('Juego listo | camara {} | microfono {} | Esc para salir.'.format(camara, microfono), flush=True)
        return subprocess.call(cliente, cwd=str(CARPETA), env=entorno)
    except KeyboardInterrupt:
        print('\nCerrando Naoqi.')
        return 130
    except (OSError, ErrorVoz, RuntimeError, subprocess.TimeoutExpired) as error:
        print('No se pudo completar la sesion:', str(error))
        return 1
    finally:
        if puente is not None:
            detener_puente(puente)
            if lector is not None:
                lector.join(timeout=2)
            if puente.stdout is not None:
                puente.stdout.close()
        if sensor is not None:
            if cliente_sensores is not None:
                try:
                    cliente_sensores.cerrar()
                except OSError:
                    pass
            detener_puente(sensor)
            if lector_sensor is not None:
                lector_sensor.join(timeout=2)
            if sensor.stdout is not None:
                sensor.stdout.close()
        if servicio_voz is not None:
            servicio_voz.cerrar()
