"""Conexion local y trabajador de IA. Python 3, sin dependencias extra."""
from __future__ import annotations

import copy
import json
import socket
import threading
import time

from ia_neo import CerebroNeo, ErrorIA

FASES_CONVERSACION = ('esperando', 'entre_rondas', 'pausa', 'terminada')


class ConexionNeo:
    def __init__(self, host='127.0.0.1', port=5005):
        self.sock = socket.create_connection((host, port), timeout=5)
        self.sock.settimeout(None)
        self.send_lock = threading.Lock()
        self.lock = threading.RLock()
        self.ready = threading.Event()
        self.closed = threading.Event()
        self.estado = None
        self.hello = {}
        self.hablando = False
        self.voice_generation = 0
        self.mute_until = 0.0
        self.on_event = None
        self.on_agent_result = None
        self.on_error = print
        self.on_command = None
        threading.Thread(target=self._leer, daemon=True).start()

    def enviar(self, dato):
        if self.closed.is_set():
            return False
        try:
            with self.send_lock:
                self.sock.sendall((json.dumps(dato, ensure_ascii=True) + '\n').encode('utf-8'))
            return True
        except OSError:
            self.closed.set()
            return False

    def comando(self, accion):
        if self.on_command:
            self.on_command()
        return self.enviar({'type': 'command', 'action': accion})

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.estado)

    def voz_token(self):
        with self.lock:
            return self.voice_generation, (not self.hablando and time.monotonic() >= self.mute_until)

    def voz_valida(self, token):
        with self.lock:
            return (token == self.voice_generation and not self.hablando
                    and time.monotonic() >= self.mute_until)

    def _leer(self):
        reader = self.sock.makefile('rb')
        try:
            while not self.closed.is_set():
                line = reader.readline(16385)
                if not line or len(line) > 16384:
                    break
                try:
                    dato = json.loads(line.decode('utf-8'))
                except (ValueError, UnicodeError):
                    continue
                tipo = dato.get('type')
                if tipo == 'hello':
                    self.hello = dato
                    if dato.get('entorno') == 'virtual':
                        print('CHOREGRAPHE VIRTUAL conectado: voz visible en Robot View/Dialog.')
                    else:
                        print('Robot SIMULADO' if dato.get('simulado') else 'Puente NAOqi conectado')
                elif tipo == 'state':
                    with self.lock:
                        self.estado = dato['state']
                    self.ready.set()
                elif tipo == 'speaking':
                    with self.lock:
                        self.hablando = bool(dato.get('active'))
                        self.voice_generation += 1
                        self.mute_until = time.monotonic() + 0.6
                    if dato.get('active'):
                        print('Neo:', dato.get('text', ''))
                elif tipo == 'event' and self.on_event:
                    self.on_event(dato)
                elif tipo == 'agent_result' and self.on_agent_result:
                    self.on_agent_result(dato)
                elif tipo == 'error':
                    self.on_error(dato.get('message', 'Fallo del puente'))
        except (OSError, ValueError, KeyError):
            pass
        finally:
            reader.close()
            self.closed.set()
            self.ready.set()

    def esperar(self, timeout=6):
        if not self.ready.wait(timeout) or self.estado is None:
            raise RuntimeError('No llego el estado. Usa robot_server_ia.py, no el servidor original.')

    def cerrar(self):
        self.closed.set()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


class Conversador:
    """Una consulta en curso y una pendiente. La ultima peticion reemplaza la pendiente."""
    def __init__(self, conexion, cerebro=None, comentarios=True):
        self.conexion = conexion
        self.cerebro = cerebro or CerebroNeo()
        self.condicion = threading.Condition()
        self.pendiente = None
        self.request_id = 0
        self.por_confirmar = {}
        self.error = ''
        self.ultimo_tiempo_ms = None
        self.parado = False
        self.en_curso = False
        self.comentarios = comentarios
        conexion.on_event = self.evento
        conexion.on_agent_result = self.confirmacion
        conexion.on_command = self.cancelar
        threading.Thread(target=self._trabajar, daemon=True).start()

    def pedir(self, texto, evento='voz_jugador'):
        estado = self.conexion.snapshot()
        if not estado or estado['fase'] not in FASES_CONVERSACION:
            print('La ronda esta en curso. Conversa antes o despues; pausa sigue disponible.')
            return False
        with self.condicion:
            if evento == 'comentario_ronda' and (self.pendiente is not None or self.en_curso):
                return False
            self.request_id += 1
            self.pendiente = (self.request_id, texto[:800], evento, estado)
            self.condicion.notify()
        return True

    def evento(self, dato):
        if self.comentarios and dato.get('event') == 'comentario_ronda':
            self.pedir('Comenta brevemente la ronda que acaba de terminar.', 'comentario_ronda')

    def cancelar(self):
        # Un comando directo del jugador invalida una decision de IA pendiente.
        with self.condicion:
            self.request_id += 1
            self.pendiente = None

    def confirmacion(self, dato):
        with self.condicion:
            pendiente = self.por_confirmar.pop(dato.get('request_id'), None)
        if pendiente and dato.get('accepted'):
            usuario, partida = pendiente
            actual = self.conexion.snapshot()
            if actual and (partida == 0 or partida == actual['partida']):
                self.cerebro.confirmar_hablado(usuario, dato.get('spoken', ''))
        elif not dato.get('accepted'):
            print('Respuesta de IA descartada: el contexto de la partida cambio.')

    def _vigente(self, request_id, estado):
        actual = self.conexion.snapshot()
        with self.condicion:
            es_ultima = request_id == self.request_id and not self.parado
        return (es_ultima and actual is not None and actual['version'] == estado['version']
                and actual['fase'] in FASES_CONVERSACION and not self.conexion.closed.is_set())

    def _trabajar(self):
        while True:
            with self.condicion:
                while self.pendiente is None and not self.parado:
                    self.condicion.wait()
                if self.parado:
                    return
                request_id, texto, evento, estado = self.pendiente
                self.pendiente = None
                self.en_curso = True
            if not self._vigente(request_id, estado):
                with self.condicion:
                    self.en_curso = False
                continue
            try:
                respuesta = self.cerebro.responder(estado, texto, evento)
            except ErrorIA as error:
                self.error = str(error)
                print('IA NO DISPONIBLE:', self.error)
                with self.condicion:
                    self.en_curso = False
                continue
            with self.condicion:
                self.en_curso = False
            self.ultimo_tiempo_ms = respuesta.pop('latencia_ms')
            self.error = ''
            origen = ('Codex real' if self.cerebro.provider == 'codex' else 'API real')
            if self.cerebro.transporte is not None:
                origen = 'IA SIMULADA (prueba)'
            print('{}: {} ms | accion {}'.format(origen, self.ultimo_tiempo_ms, respuesta['accion']))
            if not self._vigente(request_id, estado):
                print('IA: respuesta antigua descartada antes de enviarla al robot.')
                continue
            with self.condicion:
                self.por_confirmar[request_id] = (texto, estado['partida'])
                # Como maximo unas pocas respuestas en vuelo hacia el puente.
                for viejo in sorted(self.por_confirmar)[:-8]:
                    self.por_confirmar.pop(viejo, None)
            self.conexion.enviar({'type': 'agent', 'request_id': request_id,
                                 'context_version': estado['version'], 'reply': respuesta})

    def cerrar(self):
        with self.condicion:
            self.parado = True
            self.pendiente = None
            self.condicion.notify()


def normalizar(texto):
    import unicodedata
    limpio = ''.join(c for c in unicodedata.normalize('NFD', texto.lower())
                     if unicodedata.category(c) != 'Mn')
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in limpio).split())


COMANDOS = {
    'empezar': 'iniciar', 'empieza': 'iniciar', 'comenzar': 'iniciar',
    'vamos a jugar': 'iniciar', 'siguiente': 'continuar', 'continuar': 'continuar',
    'continua': 'continuar', 'reanudar': 'continuar', 'pausa': 'pausar',
    'pausar': 'pausar', 'espera': 'pausar', 'para': 'pausar',
    'reglas': 'reglas', 'marcador': 'marcador'
}


def procesar_texto(texto, conexion, conversador, requiere_nombre=False):
    limpio = normalizar(texto)
    if limpio.startswith('neo '):
        limpio = limpio[4:].strip()
        dirigido = True
    elif limpio == 'neo':
        limpio = 'hola'
        dirigido = True
    else:
        dirigido = False
    if limpio in COMANDOS:
        conexion.comando(COMANDOS[limpio])
        return True
    if requiere_nombre and not dirigido:
        return False
    if conversador:
        return conversador.pedir(texto)
    print('Modo SIN IA: solo estan disponibles los comandos del juego.')
    return False
