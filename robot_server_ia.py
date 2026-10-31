# -*- coding: utf-8 -*-
"""Puente NAOqi Python 2.7 / Python 3. API de IA en el otro proceso."""
from __future__ import print_function, unicode_literals

import argparse
import json
import socket
import sys
import threading
import time
try:
    import queue
except ImportError:
    import Queue as queue

from estado_juego import EstadoJuego, JUGADAS, texto_hablable
from naoqi_compat import cadena_naoqi

REGLAS = ('Piedra vence a tijera, tijera vence a papel y papel vence a piedra. '
          'Muestra tu jugada cuando diga ya. Di siguiente para otra ronda, '
          'pausa para esperar, o Neo seguido de una pregunta para conversar.')


class Robot(object):
    def __init__(self, ip, port, simular=False, movimientos=False):
        self.simular = simular
        self.movimientos = movimientos
        if not simular:
            from naoqi import ALProxy
            ip = cadena_naoqi(ip)
            port = int(port)
            self.tts = ALProxy(cadena_naoqi('ALTextToSpeech'), ip, port)
            try:
                self.tts.setLanguage(cadena_naoqi('Spanish'))
            except Exception:
                print('No se pudo seleccionar Spanish; se conserva el idioma de NAOqi.')
            if movimientos:
                self.postura = ALProxy(cadena_naoqi('ALRobotPosture'), ip, port)
                self.motion = ALProxy(cadena_naoqi('ALMotion'), ip, port)
                self.leds = ALProxy(cadena_naoqi('ALLeds'), ip, port)

    def decir(self, texto):
        print('NEO:', texto)
        if self.simular:
            time.sleep(0.01)
        else:
            self.tts.say(cadena_naoqi(texto))

    def ojos(self, color):
        if not self.simular and self.movimientos:
            self.leds.fadeRGB(cadena_naoqi('FaceLeds'), color, 0.3)

    def postura_inicial(self):
        if not self.simular and self.movimientos:
            self.postura.goToPosture(cadena_naoqi('StandInit'), 0.7)

    def brazo(self, pitch, codo, duracion):
        if not self.simular and self.movimientos:
            self.motion.angleInterpolation([cadena_naoqi('RShoulderPitch'), cadena_naoqi('RElbowRoll')],
                [[pitch], [codo]], [[duracion], [duracion]], True)

    def mano(self, abierta):
        if not self.simular and self.movimientos:
            self.motion.setAngles(cadena_naoqi('RHand'), 1.0 if abierta else 0.0, 0.6)
            time.sleep(0.5)

    def preparar(self):
        self.postura_inicial()
        self.mano(False)
        self.brazo(-0.5, 1.0, 0.8)

    def sacudir(self):
        # Mismos angulos, articulaciones y velocidades del archivo recibido.
        for _ in range(3):
            self.brazo(0.3, 1.0, 0.35)
            self.brazo(-0.5, 1.0, 0.35)

    def mostrar(self, jugada):
        if jugada == 'piedra':
            self.mano(False)
            self.brazo(0.0, 0.5, 0.8)
        elif jugada == 'papel':
            self.mano(True)
            self.brazo(0.0, 0.1, 0.8)
        elif jugada == 'tijera':
            self.mano(True)
            self.brazo(-1.2, 0.3, 0.8)


class Sesion(object):
    def __init__(self, conn, robot, rondas=3, espera=3.0):
        self.conn = conn
        self.robot = robot
        self.estado = EstadoJuego(rondas)
        self.espera = espera
        self.closed = threading.Event()
        self.pause_requested = threading.Event()
        self.vision_ready = threading.Event()
        self.lock = threading.RLock()
        self.send_lock = threading.Lock()
        self.speech_lock = threading.Lock()
        self.commands = queue.Queue(maxsize=32)
        self.vision = None
        self.vision_mano = False

    def enviar(self, dato):
        if self.closed.is_set():
            return
        try:
            with self.send_lock:
                self.conn.sendall((json.dumps(dato, ensure_ascii=True) + '\n').encode('utf-8'))
        except (socket.error, IOError):
            self.closed.set()
            self.pause_requested.set()
            self.vision_ready.set()

    def publicar(self):
        with self.lock:
            snapshot = self.estado.snapshot()
        self.enviar({'type': 'state', 'state': snapshot})
        return snapshot

    def decir(self, texto):
        texto = texto_hablable(texto, 450)
        if not texto or self.closed.is_set():
            return
        with self.speech_lock:
            self.enviar({'type': 'speaking', 'active': True, 'text': texto})
            try:
                self.robot.decir(texto)
            finally:
                self.enviar({'type': 'speaking', 'active': False})

    def recibir(self):
        reader = self.conn.makefile('rb')
        try:
            while not self.closed.is_set():
                raw = reader.readline(8193)
                if not raw or len(raw) > 8192:
                    break
                try:
                    dato = json.loads(raw.decode('utf-8'))
                except (ValueError, UnicodeError):
                    continue
                if not isinstance(dato, dict):
                    continue
                if dato.get('type') == 'vision':
                    with self.lock:
                        if (self.estado.fase == 'capturando'
                                and dato.get('capture_id') == self.estado.capture_id):
                            self.vision_mano = self.vision_mano or bool(dato.get('hand_present'))
                            if self.vision is None and dato.get('gesture') in JUGADAS:
                                self.vision = (dato['gesture'], self.estado.capture_id)
                                self.vision_ready.set()
                    continue
                if dato.get('type') == 'command' and dato.get('action') == 'pausar':
                    self.pause_requested.set()
                    self.vision_ready.set()
                if dato.get('type') in ('command', 'agent'):
                    try:
                        self.commands.put_nowait(dato)
                    except queue.Full:
                        self.enviar({'type': 'error', 'message': 'Cola de comandos ocupada.'})
        except (socket.error, IOError):
            pass
        finally:
            reader.close()
            self.closed.set()
            self.pause_requested.set()
            self.vision_ready.set()

    def pausar(self, motivo):
        with self.lock:
            if self.estado.fase == 'pausa':
                return
            cambio = self.estado.pausar(motivo)
        if cambio:
            self.publicar()
            if motivo == 'sin_jugada_valida':
                self.decir('No vi una jugada valida a tiempo. Pausamos. Di continuar para reintentar.')
            else:
                self.decir('Pausamos. Di continuar cuando estes listo.')

    def ronda(self):
        with self.lock:
            if not self.estado.preparar_ronda():
                return
        self.pause_requested.clear()
        self.publicar()
        self.robot.ojos(0x0000FF)
        self.robot.preparar()
        voz = threading.Thread(target=self.decir, args=('Piedra, papel o tijera.',))
        voz.daemon = True
        voz.start()
        self.robot.sacudir()
        voz.join()
        if self.closed.is_set():
            return
        if self.pause_requested.is_set():
            self.pausar('peticion_jugador')
            return
        self.decir('Ya.')
        if self.closed.is_set() or self.pause_requested.is_set():
            self.pausar('peticion_jugador')
            return
        with self.lock:
            self.vision = None
            self.vision_mano = False
            self.vision_ready.clear()
            self.estado.abrir_captura()
        self.publicar()
        self.vision_ready.wait(self.espera)
        if self.closed.is_set():
            return
        if self.pause_requested.is_set():
            self.pausar('peticion_jugador')
            return
        with self.lock:
            resultado = self.estado.registrar(*self.vision) if self.vision else None
        if resultado is None:
            self.pausar('sin_jugada_valida')
            return
        self.publicar()
        self.robot.mostrar(resultado['neo'])
        colores = {'empate': 0xFFFF00, 'jugador': 0xFF0000, 'neo': 0x00FF00}
        self.robot.ojos(colores[resultado['ganador']])
        frases = {'empate': 'Empatamos.', 'jugador': 'Ganaste esta ronda.', 'neo': 'Gané esta ronda.'}
        self.decir('Tú sacaste {} y yo {}. {}'.format(resultado['jugador'], resultado['neo'],
                                                     frases[resultado['ganador']]))
        self.decir(self.estado.frase_marcador())
        if self.estado.fase == 'terminada':
            self.decir(self.estado.frase_final())
        else:
            self.decir('Di siguiente cuando quieras continuar.')
        self.enviar({'type': 'event', 'event': 'comentario_ronda', 'state': self.estado.snapshot()})

    def ejecutar(self, accion, texto=''):
        if accion == 'iniciar':
            with self.lock:
                if not self.estado.iniciar():
                    return False, ''
            self.publicar()
            frase = texto or 'Jugaremos {} rondas validas, incluidos los empates.'.format(self.estado.max_rondas)
            self.decir(frase)
            self.ronda()
            return True, frase
        if accion == 'continuar':
            if self.estado.fase not in ('entre_rondas', 'pausa'):
                return False, ''
            if texto:
                self.decir(texto)
            self.ronda()
            return True, texto
        if accion == 'pausar':
            self.pausar('peticion_jugador')
            return True, 'Pausamos.'
        if accion == 'reglas':
            frase = REGLAS + ' Jugaremos {} rondas validas.'.format(self.estado.max_rondas)
        elif accion == 'marcador':
            frase = self.estado.frase_marcador()
        elif accion == 'hablar':
            frase = texto
        else:
            return False, ''
        self.decir(frase)
        return True, frase

    def procesar(self, dato):
        if dato.get('type') == 'agent':
            args = dato.get('reply')
            accion = args.get('accion') if isinstance(args, dict) else None
            with self.lock:
                permitido = self.estado.permite_agente(dato.get('context_version'), accion)
            if not permitido or not isinstance(args, dict) or set(args) != set(['accion', 'texto']):
                self.enviar({'type': 'agent_result', 'request_id': dato.get('request_id'),
                             'accepted': False, 'reason': 'contexto_o_accion_no_validos'})
                return
            texto = texto_hablable(args.get('texto', ''))
            if not texto:
                return
            # Puntos y movimientos no son parametros de esta interfaz.
            ok, hablado = self.ejecutar(accion, texto)
            self.enviar({'type': 'agent_result', 'request_id': dato.get('request_id'),
                         'accepted': ok, 'spoken': hablado, 'action': accion})
        else:
            self.ejecutar(dato.get('action'))

    def run(self):
        lector = threading.Thread(target=self.recibir)
        lector.daemon = True
        lector.start()
        self.enviar({'type': 'hello', 'protocol': 1, 'simulado': self.robot.simular,
                     'movimientos': self.robot.movimientos})
        self.publicar()
        self.decir('Hola, soy Neo. Di empezar para jugar, o Neo seguido de una pregunta para conversar.')
        while not self.closed.is_set():
            try:
                dato = self.commands.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self.procesar(dato)
            except Exception as error:
                print('Fallo del puente:', type(error).__name__)
                with self.lock:
                    self.estado.pausar('fallo_puente')
                self.publicar()
                self.enviar({'type': 'error', 'message': 'Fallo de voz o movimiento. Revisa la consola NAOqi.'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--robot-ip', default='127.0.0.1')
    parser.add_argument('--robot-port', type=int, default=54743)
    parser.add_argument('--puerto', type=int, default=5005)
    parser.add_argument('--rondas', type=int, choices=(3, 5), default=3)
    parser.add_argument('--espera', type=float, default=3.0)
    parser.add_argument('--simular', action='store_true', help='Sin NAOqi: solo imprime lo que diria Neo.')
    parser.add_argument('--movimientos', action='store_true', help='Activa los movimientos del script original.')
    args = parser.parse_args()
    if not 0.5 <= args.espera <= 10:
        parser.error('--espera debe estar entre 0.5 y 10 segundos.')
    robot = Robot(args.robot_ip, args.robot_port, args.simular, args.movimientos)
    servidor = socket.socket()
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind(('127.0.0.1', args.puerto))
    servidor.listen(1)
    print('Puente local en 127.0.0.1:{} | simulado={} | movimientos={}'.format(
        args.puerto, args.simular, args.movimientos))
    print('NAOqi destino: {}:{}'.format(args.robot_ip, args.robot_port))
    # El lanzador espera esta linea antes de abrir el cliente; no crea una
    # conexion de prueba que dispare un saludo o una sesion de juego extra.
    print('PUENTE_LISTO')
    sys.stdout.flush()
    try:
        while True:
            conn, _ = servidor.accept()
            try:
                Sesion(conn, robot, args.rondas, args.espera).run()
            finally:
                conn.close()
    except KeyboardInterrupt:
        print('Puente cerrado.')
    finally:
        servidor.close()


if __name__ == '__main__':
    main()
