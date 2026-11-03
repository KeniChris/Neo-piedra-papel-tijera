"""Inicia Naoqi: piedra, papel o tijera, vision y conversacion."""
from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
import sys

from ejecucion_nao import ejecutar
from voz_openai import VOCES

CARPETA = Path(__file__).resolve().parent
PERFIL = CARPETA / 'config' / 'naoqi.json'
PERFIL_LOCAL = CARPETA / 'config' / 'naoqi.local.json'


def validar_ip(valor):
    if not isinstance(valor, str):
        raise ValueError('La IP debe ser una direccion IPv4.')
    direccion = ipaddress.ip_address(valor)
    if (direccion.version != 4 or direccion.is_loopback or
            direccion.is_unspecified or direccion.is_multicast):
        raise ValueError('Introduce la IPv4 del robot conectado a tu red.')
    return valor


def cargar_config(ruta=None):
    ruta = Path(ruta) if ruta else (PERFIL_LOCAL if PERFIL_LOCAL.is_file() else PERFIL)
    try:
        texto = ruta.read_text(encoding='utf-8-sig')
        if len(texto) > 32768:
            raise ValueError('El archivo supera el tamano permitido.')
        config = json.loads(texto)
    except (OSError, ValueError) as error:
        raise ValueError('No se pudo leer la configuracion: {}'.format(error)) from error
    campos = {'robot_ip', 'robot_port', 'puertos_alternativos', 'python_naoqi', 'modelo_codex',
              'camara', 'camara_pc', 'indice_camara_nao', 'microfono', 'voz', 'voz_openai',
              'rondas', 'espera_jugada_seg', 'reintentos_captura', 'movimientos',
              'puerto_control', 'puerto_sensores', 'callback_ip', 'callback_port',
              'puerto_voz', 'respaldo_pc'}
    if not isinstance(config, dict) or set(config) != campos:
        raise ValueError('Usa config/naoqi.json como referencia para los campos.')
    for nombre in ('robot_port', 'puerto_control', 'puerto_sensores', 'callback_port', 'puerto_voz'):
        if type(config[nombre]) is not int or not 1 <= config[nombre] <= 65535:
            raise ValueError('Puerto no valido: ' + nombre)
    if len({config[n] for n in ('puerto_control', 'puerto_sensores', 'callback_port', 'puerto_voz')}) != 4:
        raise ValueError('Control, sensores, callback y voz requieren puertos locales distintos.')
    alternativos = config['puertos_alternativos']
    if (not isinstance(alternativos, list) or len(alternativos) > 3 or
            any(type(p) is not int or not 1 <= p <= 65535 for p in alternativos) or
            len(set(alternativos)) != len(alternativos)):
        raise ValueError('Configura hasta tres puertos alternativos distintos.')
    if config['camara'] not in ('nao', 'pc') or config['microfono'] not in ('nao', 'pc', 'no'):
        raise ValueError('Camara: nao/pc. Microfono: nao/pc/no.')
    if config['voz'] not in ('nao_tts', 'openai') or config['voz_openai'] not in VOCES:
        raise ValueError('Configura voz nao_tts/openai y una voz admitida, como verse.')
    if type(config['rondas']) is not int or config['rondas'] not in (3, 5):
        raise ValueError('La partida debe tener tres o cinco rondas.')
    if type(config['indice_camara_nao']) is not int or config['indice_camara_nao'] not in (0, 1):
        raise ValueError('La camara NAO debe ser 0 o 1.')
    if type(config['reintentos_captura']) is not int or config['reintentos_captura'] not in (0, 1, 2):
        raise ValueError('reintentos_captura debe ser 0, 1 o 2.')
    if (type(config['espera_jugada_seg']) not in (int, float) or
            not 0.5 <= config['espera_jugada_seg'] <= 10):
        raise ValueError('La captura debe durar entre 0.5 y 10 segundos.')
    for nombre in ('movimientos', 'respaldo_pc'):
        if type(config[nombre]) is not bool:
            raise ValueError(nombre + ' debe ser true o false.')
    for nombre in ('python_naoqi', 'modelo_codex', 'camara_pc'):
        if not isinstance(config[nombre], str) or not config[nombre].strip():
            raise ValueError('Texto no valido: ' + nombre)
    for nombre in ('robot_ip', 'callback_ip'):
        if config[nombre] is not None:
            validar_ip(config[nombre])
    return config


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', help='IPv4 del NAO; se solicita si falta.')
    parser.add_argument('--robot-port', type=int, help='Puerto NAOqi del robot.')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--voz', choices=('nao_tts', 'openai'))
    parser.add_argument('--voz-openai', choices=VOCES)
    parser.add_argument('--movimientos', action='store_true')
    parser.add_argument('--rondas', type=int, choices=(3, 5))
    parser.add_argument('--puerto', type=int, help='Puerto local de control; 5005 por defecto.')
    parser.add_argument('--sin-ia', action='store_true', help='Juega con reglas locales sin conversacion.')
    args = parser.parse_args(argv)
    try:
        config = cargar_config(args.config)
        if args.ip:
            config['robot_ip'] = validar_ip(args.ip)
        if not config['robot_ip']:
            config['robot_ip'] = validar_ip(input('IP del NAO > ').strip())
        for argumento, campo in [('voz', 'voz'), ('voz_openai', 'voz_openai'),
                                  ('rondas', 'rondas'), ('puerto', 'puerto_control'),
                                  ('robot_port', 'robot_port')]:
            valor = getattr(args, argumento)
            if valor is not None:
                config[campo] = valor
        if args.robot_port is not None:
            config['puertos_alternativos'] = []
        if args.movimientos:
            config['movimientos'] = True
        for nombre in ('robot_port', 'puerto_control'):
            if not 1 <= config[nombre] <= 65535:
                raise ValueError('Puerto no valido: ' + nombre)
        if len({config[n] for n in ('puerto_control', 'puerto_sensores', 'callback_port', 'puerto_voz')}) != 4:
            raise ValueError('Los puertos locales de control, sensores, callback y voz deben ser distintos.')
        print('Naoqi | NAO V6 | {}:{}'.format(config['robot_ip'], config['robot_port']), flush=True)
        print('Camara: {} | Microfono: {} | Voz: {}'.format(config['camara'], config['microfono'], config['voz']))
        print('Modelo: {} | Movimientos: {}'.format(config['modelo_codex'], config['movimientos']))
        return ejecutar(config, sin_ia=args.sin_ia)
    except (ValueError, OSError, RuntimeError, ImportError) as error:
        print('NO SE INICIO EL JUEGO:', str(error))
        print('Dependencias: python instalar.py')
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\nInicio cancelado.')
        return 130


if __name__ == '__main__':
    sys.exit(main())
