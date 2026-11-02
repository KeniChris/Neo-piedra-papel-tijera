# -*- coding: utf-8 -*-
"""Comprobacion real de NAOqi; compatible con Python 2.7 y Python 3."""
from __future__ import print_function, unicode_literals

import argparse
import struct
import sys
import traceback

from naoqi_compat import cadena_naoqi

FALLO_DESTINO = 70


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--robot-ip', default='127.0.0.1')
    parser.add_argument('--robot-port', type=int, required=True)
    parser.add_argument('--solo-sdk', action='store_true', help='Importa el SDK sin conectar con un robot.')
    parser.add_argument('--voz', choices=('nao_tts', 'openai'), default='nao_tts')
    parser.add_argument('--salida-voz', choices=('nao', 'pc'), default='nao')
    parser.add_argument('--puerto-voz', type=int, default=5008)
    parser.add_argument('--probar-voz', action='store_true', help='Lee una frase a traves del puente OpenAI; consume API.')
    args = parser.parse_args()
    print('Interprete NAOqi:', sys.executable)
    print('Arquitectura del interprete SDK:', struct.calcsize('P') * 8, 'bits')
    print('Destino: {}:{}'.format(args.robot_ip, args.robot_port))
    try:
        import naoqi
    except ImportError:
        print('FALLO: este interprete no puede importar naoqi.')
        print('Usa el Python y entorno del SDK con los que ejecutabas prueba_naoqui.py.')
        return 1
    print('SDK cargado:', getattr(naoqi, '__file__', '(modulo sin ruta)'))
    if args.solo_sdk:
        print('SDK_OK: importado sin conectar con un robot.')
        return 0
    if args.voz == 'openai':
        from audio_neo import SalidaAudioNAO, ClienteVoz, ErrorPuenteVoz
        salida = None
        try:
            if args.salida_voz == 'nao':
                salida = SalidaAudioNAO(args.robot_ip, args.robot_port)
            else:
                # Comprueba el destino virtual, aunque el audio saldra por la laptop.
                naoqi.ALProxy(cadena_naoqi('ALMemory'), cadena_naoqi(args.robot_ip), int(args.robot_port))
            if args.probar_voz:
                ClienteVoz(args.puerto_voz, salida=salida).decir(
                    'Hola, soy Neo. Esta es mi voz generada por inteligencia artificial.')
                print('VOZ_OPENAI_ENVIADA: reproduccion solicitada en {}. Confirma que se oiga.'.format(args.salida_voz))
            else:
                print('NAOQI_OK: destino disponible para voz OpenAI; no se genero audio ni se probo audibilidad.')
            return 0
        except ErrorPuenteVoz as error:
            print('FALLO VOZ OPENAI:', str(error))
            return 1
        except Exception as error:
            print('FALLO SALIDA AUDIO NAO:', type(error).__name__)
            # Tras empezar la prueba de pago no se repite en otros destinos.
            return 1 if args.probar_voz else FALLO_DESTINO
        finally:
            if salida is not None:
                salida.cerrar()
    etapa = 'crear ALProxy(ALTextToSpeech)'
    try:
        tts = naoqi.ALProxy(cadena_naoqi('ALTextToSpeech'), cadena_naoqi(args.robot_ip), int(args.robot_port))
        print('PROXY_OK: ALTextToSpeech creado.')
        try:
            tts.setLanguage(cadena_naoqi('Spanish'))
        except Exception as error_idioma:
            print('AVISO: setLanguage(Spanish) no disponible; se conserva el idioma actual.')
            print('Detalle de idioma:', repr(error_idioma))
        etapa = 'ALTextToSpeech.say'
        tts.say(cadena_naoqi('Hola, soy Neo. Conexion con NAOqi comprobada.'))
    except Exception as error:
        print('FALLO NAOqi en {}: {}'.format(etapa, type(error).__name__))
        print('Detalle:', repr(error))
        sys.stdout.flush()
        traceback.print_exc()
        if isinstance(error, NotImplementedError):
            print('El SDK rechazo una llamada. Conserva este diagnostico completo para revisar sus argumentos y version.')
        else:
            print('Comprueba la IP, el puerto y que el robot virtual este iniciado.')
        return FALLO_DESTINO
    print('NAOQI_OK: ALTextToSpeech.say termino sin error.')
    print('En el robot virtual comprueba la frase en Robot View o Dialog; puede no haber audio.')
    print('Esta prueba no consulta la IA ni mueve articulaciones.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
