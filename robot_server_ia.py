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

from estado_juego import ANUNCIOS_JUGADA, AVISO_REINTENTO, EstadoJuego, JUGADAS, texto_hablable
from audio_neo import ErrorPuenteVoz
from naoqi_compat import cadena_naoqi
from personalidad_naoqi import (NOMBRE, SALUDO, INVITACION_APRETON, JINGLE_VICTORIA,
                                TIEMPO_APRETON, comentario_ronda)

REGLAS = ('Piedra vence a tijera, tijera vence a papel y papel vence a piedra. '
          'Muestra tu jugada cuando diga ya. Di siguiente para otra ronda, '
          'pausa para esperar, o haz una pregunta para conversar.')


class Robot(object):
    def __init__(self, ip, port, simular=False, movimientos=False, entorno='configurado', voz='nao_tts', puerto_voz=5008):
        self.simular = simular
        self.movimientos = movimientos
        self.entorno = entorno
        self.voz = voz
        self.salida_voz = 'nao'
        self.audio = None
        if not simular:
            from naoqi import ALProxy
            if voz == 'openai':
                from audio_neo import ClienteVoz, SalidaAudioNAO
                salida = SalidaAudioNAO(ip, port)
                self.audio = ClienteVoz(puerto_voz, salida=salida)
            ip = cadena_naoqi(ip)
            port = int(port)
            if voz == 'nao_tts':
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
        print(NOMBRE + ':', texto)
        if self.simular:
            time.sleep(0.01)
        elif self.audio is not None:
            self.audio.decir(texto)
        else:
            self.tts.say(cadena_naoqi(texto))

    def cantar(self, texto):
        if self.audio is not None and not self.simular:
            print(NOMBRE + ' canta:', texto)
            self.audio.cantar(texto)
        else:
            # La voz nativa lee el estribillo; no se promete una melodia.
            self.decir(texto)

    def cerrar(self):
        if self.audio is not None:
            self.audio.cerrar()

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

    def celebrar(self):
        if self.simular or not self.movimientos:
            return
        try:
            self.mano(True)
            for _ in range(2):
                self.brazo(-0.5, 1.0, 0.8)
                self.brazo(0.0, 0.5, 0.8)
        finally:
            self.postura_inicial()

    def ofrecer_mano(self, cancelar=None):
        if self.simular or not self.movimientos:
            return
        cancelar = cancelar if cancelar is not None else threading.Event()
        try:
            if cancelar.is_set():
                return
            # Reutiliza la pose de papel; mantiene la mano abierta.
            self.mostrar('papel')
            cancelar.wait(TIEMPO_APRETON)
        finally:
            self.postura_inicial()


class Sesion(object):
    def __init__(self, conn, robot, rondas=3, espera=6.0, reintentos=1):
        self.conn = conn
        self.robot = robot
        self.estado = EstadoJuego(rondas)
        self.espera = espera
        self.reintentos = reintentos
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
        self._voz(texto)

    def cantar(self, texto):
        self._voz(texto, cantado=True)

    def _voz(self, texto, cantado=False):
        texto = texto_hablable(texto, 450)
        if not texto or self.closed.is_set():
            return
        with self.speech_lock:
            self.enviar({'type': 'speaking', 'active': True, 'text': texto})
            try:
                if cantado:
                    self.robot.cantar(texto)
                else:
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
                    if dato.get('type') == 'command':
                        with self.lock:
                            dato['_version_recibida'] = self.estado.version
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
                self.decir('No pude confirmar la jugada. Conservamos esta ronda y los puntos. Di continuar.')
            else:
                self.decir('Pausamos. Di continuar cuando estes listo.')

    def revelar_jugada(self, jugada):
        """Inicia voz y pose juntas; el argumento viene de la eleccion previa."""
        if jugada not in JUGADAS:
            raise ValueError('Jugada de revelacion no valida')
        self.voz_y_movimiento(ANUNCIOS_JUGADA[jugada], lambda: self.robot.mostrar(jugada))

    def voz_y_movimiento(self, texto, movimiento, cantado=False):
        if self.closed.is_set():
            return
        errores_voz = []
        def anunciar():
            try:
                self._voz(texto, cantado)
            except Exception as error:
                errores_voz.append(error)
        voz = threading.Thread(target=anunciar)
        voz.daemon = True
        voz.start()
        try:
            # Mismas poses, angulos y velocidades del programa recibido.
            # Solo envia comandos de motor si se activo --movimientos.
            movimiento()
        finally:
            voz.join()
        if errores_voz:
            raise errores_voz[0]

    def cerrar_partida(self):
        puntos = self.estado.marcador
        if puntos['neo'] > puntos['jugador']:
            self.voz_y_movimiento(JINGLE_VICTORIA, self.robot.celebrar, cantado=True)
        elif puntos['jugador'] > puntos['neo']:
            self.voz_y_movimiento(INVITACION_APRETON,
                                 lambda: self.robot.ofrecer_mano(self.pause_requested))
        else:
            self.decir('Empate final. Dejamos el duelo pendiente y mi ego intacto.')

    def ronda(self):
        with self.lock:
            if not self.estado.preparar_ronda():
                return
        self.pause_requested.clear()
        self.publicar()
        self.robot.ojos(0x0000FF)
        self.robot.preparar()
        errores_voz = []
        def cuenta_atras():
            try:
                self.decir('Piedra, papel o tijera.')
            except Exception as error:
                errores_voz.append(error)
        voz = threading.Thread(target=cuenta_atras)
        voz.daemon = True
        voz.start()
        self.robot.sacudir()
        voz.join()
        if errores_voz:
            raise errores_voz[0]
        if self.closed.is_set():
            return
        if self.pause_requested.is_set():
            self.pausar('peticion_jugador')
            return
        resultado = None
        for intento in range(self.reintentos + 1):
            if intento:
                self.decir(AVISO_REINTENTO)
            if self.closed.is_set() or self.pause_requested.is_set():
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
                token = self.estado.abrir_captura()
            self.publicar()
            self.enviar({'type': 'capture_window', 'capture_id': token, 'seconds': self.espera,
                         'attempt': intento + 1, 'attempts': self.reintentos + 1})
            self.vision_ready.wait(self.espera)
            if self.closed.is_set():
                return
            if self.pause_requested.is_set():
                self.pausar('peticion_jugador')
                return
            with self.lock:
                resultado = self.estado.registrar(*self.vision) if self.vision else None
                if resultado is None and intento < self.reintentos:
                    self.estado.preparar_reintento()
            if resultado is not None:
                break
            if intento < self.reintentos:
                self.publicar()
        if resultado is None:
            self.pausar('sin_jugada_valida')
            return
        with self.lock:
            terminada = self.estado.fase == 'terminada'
            if terminada:
                self.estado.cambiar_fase('cierre')
        self.publicar()
        try:
            try:
                self.revelar_jugada(resultado['neo'])
            except ErrorPuenteVoz as error:
                if not terminada:
                    raise
                self.notificar_fallo_voz(error, {})
            colores = {'empate': 0xFFFF00, 'jugador': 0xFF0000, 'neo': 0x00FF00}
            self.robot.ojos(colores[resultado['ganador']])
            cierre = self.estado.frase_final() if terminada else 'Di siguiente cuando quieras continuar.'
            try:
                self.decir('Tú sacaste {}. {} {} {}'.format(resultado['jugador'],
                           comentario_ronda(resultado['ganador'], resultado['numero']),
                           self.estado.frase_marcador(), cierre))
            except ErrorPuenteVoz as error:
                if not terminada:
                    raise
                self.notificar_fallo_voz(error, {})
            if terminada:
                self.cerrar_partida()
        finally:
            if terminada:
                with self.lock:
                    self.estado.cambiar_fase('terminada')
                self.publicar()
        if not terminada:
            self.enviar({'type': 'event', 'event': 'comentario_ronda', 'state': self.estado.snapshot()})

    def ejecutar(self, accion, texto=''):
        if accion == 'iniciar':
            with self.lock:
                if not self.estado.iniciar():
                    return False, ''
            self.publicar()
            frase = texto or ('Jugaremos {} rondas validas, incluidos los empates. '
                              'Trae tu mejor jugada, que yo vengo a ganar.').format(self.estado.max_rondas)
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
            if dato.get('action') != 'pausar' and dato.get('_version_recibida', self.estado.version) != self.estado.version:
                self.enviar({'type': 'error', 'message': 'La ronda cambio; repite el comando cuando termine el aviso.'})
                return
            self.ejecutar(dato.get('action'))

    def notificar_fallo_voz(self, error, dato):
        """Una frase fallida no invalida una ronda ya registrada."""
        print('VOZ OPENAI NO DISPONIBLE:', str(error))
        with self.lock:
            if self.estado.fase in ('cuenta_atras', 'capturando'):
                self.estado.pausar('fallo_voz')
            fase = self.estado.fase
        self.publicar()
        if fase == 'pausa':
            ayuda = 'Conservamos la ronda y los puntos. Di continuar o pulsa C para reanudar.'
        elif fase == 'entre_rondas':
            ayuda = 'La ronda y el marcador estan guardados. Di siguiente o pulsa N para continuar.'
        elif fase == 'terminada':
            ayuda = 'La partida termino; el resultado y el marcador siguen en pantalla.'
        elif fase == 'cierre':
            ayuda = 'La partida ya esta puntuada; estamos terminando el cierre.'
        else:
            ayuda = 'Los comandos del juego siguen disponibles.'
        self.enviar({'type': 'error', 'source': 'voz',
                     'message': 'No se completo la voz OpenAI. ' + ayuda +
                     ' No se reintento la frase ni se cambio de proveedor.'})
        if dato.get('type') == 'agent':
            self.enviar({'type': 'agent_result', 'request_id': dato.get('request_id'),
                         'accepted': False, 'reason': 'voz_no_reproducida'})

    def run(self):
        lector = threading.Thread(target=self.recibir)
        lector.daemon = True
        lector.start()
        self.enviar({'type': 'hello', 'protocol': 1, 'simulado': self.robot.simular,
                     'movimientos': self.robot.movimientos, 'entorno': getattr(self.robot, 'entorno', 'configurado'),
                     'voz': getattr(self.robot, 'voz', 'nao_tts'), 'salida_voz': getattr(self.robot, 'salida_voz', 'nao')})
        self.publicar()
        self.decir(SALUDO)
        while not self.closed.is_set():
            try:
                dato = self.commands.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self.procesar(dato)
            except ErrorPuenteVoz as error:
                self.notificar_fallo_voz(error, dato)
            except Exception as error:
                print('Fallo del puente:', type(error).__name__)
                if getattr(self.robot, 'voz', 'nao_tts') == 'openai':
                    print('Detalle de voz:', str(error))
                with self.lock:
                    self.estado.pausar('fallo_puente')
                self.publicar()
                self.enviar({'type': 'error', 'message': 'Fallo de voz o movimiento. Revisa la consola NAOqi.'})
                if dato.get('type') == 'agent':
                    self.enviar({'type': 'agent_result', 'request_id': dato.get('request_id'),
                                 'accepted': False, 'reason': 'fallo_puente'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--robot-ip', required=True)
    parser.add_argument('--robot-port', type=int, default=9561)
    parser.add_argument('--puerto', type=int, default=5005)
    parser.add_argument('--rondas', type=int, choices=(3, 5), default=3)
    parser.add_argument('--espera', type=float, default=6.0)
    parser.add_argument('--reintentos', type=int, choices=(0, 1, 2), default=1)
    parser.add_argument('--movimientos', action='store_true', help='Activa los movimientos del script original.')
    parser.add_argument('--voz', choices=('nao_tts', 'openai'), default='nao_tts')
    parser.add_argument('--puerto-voz', type=int, default=5008)
    args = parser.parse_args()
    if not 0.5 <= args.espera <= 10:
        parser.error('--espera debe estar entre 0.5 y 10 segundos.')
    robot = Robot(args.robot_ip, args.robot_port, False, args.movimientos, 'nao', args.voz, args.puerto_voz)
    servidor = socket.socket()
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind(('127.0.0.1', args.puerto))
    servidor.listen(1)
    print('Puente de juego en 127.0.0.1:{} | movimientos={}'.format(args.puerto, args.movimientos))
    print('NAOqi destino: {}:{}'.format(args.robot_ip, args.robot_port))
    # El lanzador espera esta linea antes de abrir el cliente; no crea una
    # conexion de prueba que dispare un saludo o una sesion de juego extra.
    print('PUENTE_LISTO')
    sys.stdout.flush()
    try:
        while True:
            conn, _ = servidor.accept()
            try:
                Sesion(conn, robot, args.rondas, args.espera, args.reintentos).run()
            finally:
                conn.close()
    except KeyboardInterrupt:
        print('Puente cerrado.')
    finally:
        servidor.close()
        robot.cerrar()


if __name__ == '__main__':
    main()

