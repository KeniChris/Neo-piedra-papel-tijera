"""Conversa por texto con Codex o API y, opcionalmente, por NAOqi."""
import argparse
import sys
import time

from cliente_neo import ConexionNeo, Conversador, procesar_texto
from estado_juego import EstadoJuego
from ia_neo import CerebroNeo, ErrorIA


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--robot', action='store_true', help='Envia las respuestas al puente de Neo.')
    parser.add_argument('--puerto', type=int, default=5005)
    args = parser.parse_args()
    try:
        cerebro = CerebroNeo()
    except ErrorIA as error:
        print(error)
        return 1
    print('IA: {} | Modelo: {}'.format(cerebro.provider, cerebro.model))
    print('Politicas: {} | se recargan en cada consulta.'.format(cerebro.politicas_path))
    conexion = None
    conversador = None
    try:
        if args.robot:
            conexion = ConexionNeo(port=args.puerto)
            conexion.esperar()
            conversador = Conversador(conexion, cerebro, comentarios=False)
            print('Escribe mensajes. Se usa la voz de Neo; no hay camara en esta prueba.')
        else:
            print('{} real en consola. No hay robot, camara ni jugadas observadas.'.format(cerebro.provider))
        print('Escribe salir para terminar.')
        while conexion is None or not conexion.closed.is_set():
            texto = input('Tu > ').strip()
            if texto.lower() in ('salir', 'exit'):
                break
            if not texto:
                continue
            if conversador:
                procesar_texto(texto, conexion, conversador)
                time.sleep(0.1)
            else:
                try:
                    respuesta = cerebro.responder(EstadoJuego().snapshot(), texto)
                    print('Neo:', respuesta['texto'])
                    print('Accion NO ejecutada:', respuesta['accion'], '|', respuesta['latencia_ms'], 'ms')
                    cerebro.confirmar_hablado(texto, respuesta['texto'])
                except ErrorIA as error:
                    print('IA NO DISPONIBLE:', error)
    except (OSError, RuntimeError) as error:
        print('No se pudo conectar con el puente:', error)
        return 1
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        if conversador:
            conversador.cerrar()
        if conexion:
            conexion.cerrar()
    return 0


if __name__ == '__main__':
    sys.exit(main())
