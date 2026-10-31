"""Perfil de examen para NAO V6 y NAOqi 2.8; no modifica el firmware del robot."""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys

from probar_choregraphe import main as iniciar_prueba, localizar_python_naoqi
from comprobar_naoqi import FALLO_DESTINO

CARPETA = Path(__file__).resolve().parent
CONFIG_PREDETERMINADA = CARPETA / 'config' / 'neo_examen.json'


def cargar_config(ruta=CONFIG_PREDETERMINADA):
    try:
        datos = Path(ruta).read_text(encoding='utf-8-sig')
        if len(datos) > 32768:
            raise ValueError('Archivo demasiado largo')
        config = json.loads(datos)
    except (OSError, ValueError) as error:
        raise ValueError('No se pudo leer el perfil JSON del examen: {}'.format(error)) from error
    requeridos = {'robot_ip', 'robot_port', 'modelo', 'choregraphe_version', 'python_naoqi', 'modelo_codex',
                  'camara', 'indice_camara_nao', 'microfono', 'voz', 'rondas', 'espera_jugada_seg',
                  'movimientos', 'puerto_control', 'puerto_sensores', 'callback_ip', 'callback_port', 'saludo_ia'}
    if not isinstance(config, dict) or set(config) - {'respaldo_choregraphe', 'puerto_virtual'} != requeridos:
        raise ValueError('El perfil tiene campos faltantes o desconocidos. Usa config/neo_examen.json como referencia.')
    config.setdefault('respaldo_choregraphe', False)
    config.setdefault('puerto_virtual', None)
    if type(config['respaldo_choregraphe']) is not bool:
        raise ValueError('respaldo_choregraphe debe ser true o false.')
    if config['puerto_virtual'] is not None:
        validar_puerto_virtual(config['puerto_virtual'])
    for nombre in ('robot_port', 'puerto_control', 'puerto_sensores', 'callback_port'):
        if type(config[nombre]) is not int or not 1 <= config[nombre] <= 65535:
            raise ValueError('Puerto no valido: ' + nombre)
    if len({config[x] for x in ('puerto_control', 'puerto_sensores', 'callback_port')}) != 3:
        raise ValueError('Los puertos locales de control, sensores y callback deben ser distintos.')
    if config['camara'] not in ('nao', 'pc') or config['microfono'] not in ('nao', 'pc', 'no'):
        raise ValueError('Camara debe ser nao/pc y microfono nao/pc/no.')
    if config['voz'] != 'nao_tts':
        raise ValueError('Este perfil implementa voz nao_tts; no contiene un agente de voz Gemini.')
    if type(config['rondas']) is not int or config['rondas'] not in (3, 5):
        raise ValueError('Rondas debe ser 3 o 5.')
    if type(config['indice_camara_nao']) is not int or config['indice_camara_nao'] not in (0, 1):
        raise ValueError('Indice de camara NAO debe ser 0 o 1.')
    if type(config['espera_jugada_seg']) not in (int, float) or not 0.5 <= config['espera_jugada_seg'] <= 10:
        raise ValueError('La ventana de jugada debe estar entre 0.5 y 10 segundos.')
    for nombre in ('movimientos', 'saludo_ia'):
        if type(config[nombre]) is not bool:
            raise ValueError(nombre + ' debe ser true o false.')
    for nombre in ('modelo', 'choregraphe_version', 'python_naoqi', 'modelo_codex'):
        if not isinstance(config[nombre], str) or not config[nombre].strip():
            raise ValueError('Texto no valido: ' + nombre)
    for nombre in ('robot_ip', 'callback_ip'):
        if config[nombre] is not None:
            validar_ip(config[nombre])
    return config


def validar_ip(valor):
    if not isinstance(valor, str) or ipaddress.ip_address(valor).version != 4 or valor == '0.0.0.0':
        raise ValueError('Introduce una direccion IPv4 real, por ejemplo la que informa el robot.')
    return valor


def validar_puerto_virtual(valor):
    if type(valor) is not int or not 1 <= valor <= 65535:
        raise ValueError('El puerto virtual debe ser el entero que muestra Choregraphe en Preferences > Virtual Robot.')
    return valor


def argumentos(config, diagnostico=False, sin_ia=False, entorno='fisico'):
    if not config['robot_ip']:
        raise ValueError('Falta la IP actual del robot fisico.')
    resultado = ['--robot-ip', config['robot_ip'], '--robot-port', str(config['robot_port']),
        '--python-naoqi', config['python_naoqi'], '--puerto', str(config['puerto_control']),
        '--puerto-sensores', str(config['puerto_sensores']), '--callback-port', str(config['callback_port']),
        '--indice-camara-nao', str(config['indice_camara_nao']), '--rondas', str(config['rondas']),
        '--espera', str(config['espera_jugada_seg']), '--vision', '--entorno', entorno]
    if config.get('respaldo_choregraphe') or entorno == 'virtual':
        resultado.append('--respaldo-pc')
    if config['camara'] == 'nao':
        resultado.append('--camara-nao')
    if config['microfono'] == 'nao':
        resultado.append('--microfono-nao')
    elif config['microfono'] == 'pc':
        resultado.append('--microfono')
    if config['callback_ip']:
        resultado += ['--callback-ip', config['callback_ip']]
    if config['movimientos']:
        resultado.append('--movimientos')
    if config['saludo_ia'] and not sin_ia:
        resultado.append('--saludo-ia')
    if diagnostico:
        resultado.append('--solo-diagnostico')
    if sin_ia:
        resultado.append('--sin-ia')
    return resultado


def ejecutar_virtual(config, diagnostico=False, sin_ia=False):
    puerto = config.get('puerto_virtual')
    if puerto is None:
        print('Abre Choregraphe con el robot virtual iniciado. Copia el puerto de Edit > Preferences > Virtual Robot.')
        try:
            puerto = int(input('Puerto ACTUAL del robot virtual de Choregraphe > ').strip())
        except ValueError as error:
            raise ValueError('El puerto virtual es un numero, no una IP.') from error
    validar_puerto_virtual(puerto)
    virtual = dict(config, robot_ip='127.0.0.1', robot_port=puerto, camara='pc',
                   microfono='pc' if config['microfono'] != 'no' else 'no', callback_ip=None)
    print('RESPALDO: CHOREGRAPHE VIRTUAL en 127.0.0.1:{}'.format(puerto), flush=True)
    print('Camara y microfono: laptop. Voz: texto en Robot View/Dialog; el virtual puede no emitir audio.')
    return iniciar_prueba(argumentos(virtual, diagnostico, sin_ia, entorno='virtual'))


def ejecutar_con_respaldo(config, diagnostico=False, sin_ia=False):
    resultado = iniciar_prueba(argumentos(config, diagnostico, sin_ia))
    if resultado == FALLO_DESTINO and config.get('respaldo_choregraphe'):
        print('El destino fisico fallo durante el arranque. Intentando una vez el virtual de Choregraphe.', flush=True)
        return ejecutar_virtual(config, diagnostico, sin_ia)
    return resultado


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=CONFIG_PREDETERMINADA)
    parser.add_argument('--ip')
    parser.add_argument('--verificar-config', action='store_true', help='Comprueba software sin conectar con el robot.')
    parser.add_argument('--diagnostico', action='store_true', help='Conecta y comprueba voz y sensores sin iniciar el juego.')
    parser.add_argument('--movimientos', action='store_true')
    parser.add_argument('--sin-ia', action='store_true', help='Prueba explicita del juego sin un modelo de conversacion.')
    parser.add_argument('--virtual', action='store_true', help='Ensaya directamente el respaldo de Choregraphe con fuentes PC.')
    parser.add_argument('--puerto-virtual', type=int, help='Puerto actual del virtual; si falta, se pide al necesitarlo.')
    args = parser.parse_args(argv)
    try:
        config = cargar_config(args.config)
        if args.ip:
            config['robot_ip'] = validar_ip(args.ip)
        if args.movimientos:
            config['movimientos'] = True
        if args.puerto_virtual is not None:
            config['puerto_virtual'] = validar_puerto_virtual(args.puerto_virtual)
        print('Perfil: {} | Choregraphe {} | puerto {}'.format(
            config['modelo'], config['choregraphe_version'], config['robot_port']))
        print('Fuentes: camara={} microfono={} voz={}'.format(config['camara'], config['microfono'], config['voz']))
        print('Modelo:', config['modelo_codex'], '| movimientos:', config['movimientos'])
        if args.verificar_config:
            from vision_ia import cargar_dependencias
            cargar_dependencias()
            if config['microfono'] != 'no':
                import speech_recognition
                if config['microfono'] == 'pc':
                    speech_recognition.Microphone.get_pyaudio()
                elif config['respaldo_choregraphe']:
                    try:
                        speech_recognition.Microphone.get_pyaudio()
                    except (ImportError, AttributeError, OSError):
                        print('AVISO: falta PyAudio para el microfono PC de respaldo; quedaran disponibles las teclas y T.')
            python_naoqi = localizar_python_naoqi(config['python_naoqi'])
            subprocess.run([python_naoqi, str(CARPETA / 'comprobar_naoqi.py'),
                            '--robot-port', str(config['robot_port']), '--solo-sdk'], check=True)
            if not args.sin_ia:
                from codex_neo import CodexLocal, ErrorCodex
                try:
                    CodexLocal(modelo=config['modelo_codex']).verificar_sesion()
                except ErrorCodex as error:
                    raise RuntimeError(str(error)) from error
            print('CONFIGURACION_OK: software disponible; no se conecto con el robot ni se consulto al modelo.')
            if not config['robot_ip']:
                print('Pendiente para el examen: introducir la IP actual del robot.')
            if config['respaldo_choregraphe'] and config['puerto_virtual'] is None:
                print('Respaldo: el puerto actual de Choregraphe se pedira al necesitarlo.')
            return 0
        os.environ['NEO_CODEX_MODEL'] = config['modelo_codex']
        if args.virtual:
            return ejecutar_virtual(config, args.diagnostico, args.sin_ia)
        if not config['robot_ip']:
            config['robot_ip'] = validar_ip(input('IP actual del NAO fisico > ').strip())
        return ejecutar_con_respaldo(config, args.diagnostico, args.sin_ia)
    except (ValueError, OSError, RuntimeError, ImportError, subprocess.CalledProcessError) as error:
        print('NO SE INICIO EL EXAMEN:', type(error).__name__, str(error))
        print('Para preparar las bibliotecas: python preparar_vision.py --examen')
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\nInicio cancelado.')
        return 130


if __name__ == '__main__':
    sys.exit(main())
