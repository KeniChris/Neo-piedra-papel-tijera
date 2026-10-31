"""Primera comprobacion REAL de Codex o API, sin camara ni robot."""
import argparse
import sys

from estado_juego import EstadoJuego
from ia_neo import CerebroNeo, ErrorIA


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--modelo', default=None)
    args = parser.parse_args()
    try:
        cerebro = CerebroNeo(model=args.modelo)
        respuesta = cerebro.responder(
            EstadoJuego().snapshot(),
            'Hola Neo, presentate brevemente y dime si podemos jugar tres rondas.')
    except ErrorIA as error:
        print('IA NO CONECTADA:', error)
        return 1
    print('CODEX REAL: respuesta recibida' if cerebro.provider == 'codex' else 'API REAL: respuesta recibida')
    print('Modelo:', cerebro.model)
    print('Politicas:', cerebro.politicas_path.name, '| version de contenido:', cerebro.politicas_huella)
    print('Latencia de la consulta: {} ms'.format(respuesta['latencia_ms']))
    print('Accion propuesta (NO ejecutada):', respuesta['accion'])
    print('Neo responderia:', respuesta['texto'])
    print('Esta prueba no ha contactado con el robot ni utilizado la camara.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
