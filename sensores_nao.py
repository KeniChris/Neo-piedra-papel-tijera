# -*- coding: utf-8 -*-
"""Camara y microfono NAOqi en Python 2.7; transporte HTTP solo por loopback."""
from __future__ import print_function, unicode_literals

import argparse
import base64
from collections import deque
import json
import math
import os
import socket
import struct
import sys
import threading
import time
import traceback
try:
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
    from SocketServer import ThreadingMixIn
    from urlparse import urlsplit, parse_qs
except ImportError:
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from socketserver import ThreadingMixIn
    from urllib.parse import urlsplit, parse_qs

from naoqi_compat import cadena_naoqi, TIPO_TEXTO

RELOJ = getattr(time, 'monotonic', time.time)


def binario(valor):
    if isinstance(valor, bytes):
        return valor
    if isinstance(valor, TIPO_TEXTO):
        return valor.encode('latin1')
    return bytearray(valor).decode('latin1').encode('latin1')


class BufferAudio(object):
    def __init__(self):
        self.condicion = threading.Condition()
        self.paquetes = deque(maxlen=80)
        self.secuencia = 0
        self.ultimo = 0.0
        self.error = ''
        self.rms = 0

    def recibir(self, canales, muestras, datos):
        with self.condicion:
            try:
                datos = binario(datos)
                if canales != 1 or muestras <= 0 or len(datos) != muestras * 2:
                    raise ValueError('Se esperaba PCM mono de 16 bits a 16000 Hz.')
                valores = struct.unpack('<{}h'.format(muestras), datos)
                self.rms = int(math.sqrt(sum(x * x for x in valores) / float(muestras)))
                self.secuencia += 1
                self.ultimo = RELOJ()
                self.paquetes.append((self.secuencia, datos))
            except (ValueError, TypeError, struct.error) as error:
                self.error = str(error)
            notificar = getattr(self.condicion, 'notify_all', None) or self.condicion.notifyAll
            notificar()

    def estado(self):
        with self.condicion:
            return {'paquetes': self.secuencia, 'rms': self.rms,
                    'edad_seg': round(RELOJ() - self.ultimo, 2) if self.ultimo else None,
                    'error': self.error, 'sample_rate': 16000, 'sample_width': 2, 'canales': 1}

    def desde(self, secuencia):
        with self.condicion:
            if self.secuencia <= secuencia and not self.error:
                self.condicion.wait(0.25)
            if self.error:
                raise RuntimeError(self.error)
            if self.ultimo and RELOJ() - self.ultimo > 3:
                raise RuntimeError('El microfono dejo de enviar muestras.')
            salto = bool(self.paquetes and secuencia < self.paquetes[0][0] - 1)
            lote = [(n, d) for n, d in self.paquetes if n > secuencia]
            datos = b''.join(d for _, d in lote)
            if len(datos) > 128000:
                raise RuntimeError('El lote de audio excede el limite local.')
            return {'secuencia': lote[-1][0] if lote else self.secuencia,
                    'discontinuidad': salto, 'pcm': base64.b64encode(datos).decode('ascii')}


class CamaraNAO(object):
    def __init__(self, proxy, indice=0, fps=15):
        self.proxy = proxy
        self.lock = threading.Lock()
        self.handle = None
        self.ultima_marca = None
        self.ultimo_tamano = None
        nombre = 'NeoCamaraExamen_{}'.format(os.getpid())
        # 1 = QVGA 320x240; 13 = BGR. Se valida tambien el formato recibido.
        self.handle = proxy.subscribeCamera(cadena_naoqi(nombre), int(indice), 1, 13, int(fps))
        if not self.handle:
            raise RuntimeError('ALVideoDevice no devolvio una suscripcion de camara.')

    def frame(self):
        with self.lock:
            fin = RELOJ() + 1.0
            while RELOJ() < fin:
                imagen = self.proxy.getImageRemote(cadena_naoqi(self.handle))
                try:
                    if not imagen or len(imagen) < 7:
                        raise RuntimeError('ALVideoDevice no devolvio una imagen.')
                    ancho, alto = int(imagen[0]), int(imagen[1])
                    if not 1 <= ancho <= 640 or not 1 <= alto <= 480 or imagen[2] != 3 or imagen[3] != 13:
                        raise RuntimeError('Formato de camara inesperado; se requiere BGR de tres canales.')
                    datos = binario(imagen[6])
                    if len(datos) != ancho * alto * 3:
                        raise RuntimeError('Imagen incompleta de ALVideoDevice.')
                    marca = '{}:{}'.format(imagen[4], imagen[5])
                    if marca != self.ultima_marca:
                        self.ultima_marca = marca
                        self.ultimo_tamano = [ancho, alto]
                        return datos, ancho, alto, marca
                finally:
                    self.proxy.releaseImage(cadena_naoqi(self.handle))
                time.sleep(0.01)
            raise RuntimeError('La camara no entrego un fotograma nuevo en un segundo.')

    def cerrar(self):
        if self.handle:
            handle, self.handle = self.handle, None
            self.proxy.unsubscribe(cadena_naoqi(handle))


def ip_hacia(robot_ip, robot_port):
    ruta = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        ruta.connect((robot_ip, robot_port))
        return ruta.getsockname()[0]
    finally:
        ruta.close()


class SensoresNAO(object):
    def __init__(self):
        self.camara = None
        self.audio = None
        self.broker = None
        self.modulo = None
        self.nombre_audio = None
        self.proxy_audio = None
        self.suscrito_audio = False
        self.version = None
        self.callback_ip = None
        self.callback_port = None
        self.salida_audio = {'volumen': None, 'silenciado': None}

    def abrir(self, ip, port, camara=True, microfono=True, indice=0, callback_ip=None, callback_port=5007):
        from naoqi import ALProxy
        ip_sdk = cadena_naoqi(ip)
        try:
            self.version = ALProxy(cadena_naoqi('ALSystem'), ip_sdk, int(port)).systemVersion()
        except Exception:
            self.version = 'no consultable'
        try:
            salida = ALProxy(cadena_naoqi('ALAudioDevice'), ip_sdk, int(port))
            self.salida_audio = {'volumen': int(salida.getOutputVolume()),
                                 'silenciado': bool(salida.isAudioOutMuted())}
        except Exception:
            pass
        if self.salida_audio['volumen'] == 0 or self.salida_audio['silenciado'] is True:
            raise RuntimeError('La salida de audio del NAO esta silenciada o con volumen cero. Ajustala antes de jugar.')
        if camara:
            self.camara = CamaraNAO(ALProxy(cadena_naoqi('ALVideoDevice'), ip_sdk, int(port)), indice)
            self.camara.frame()
        if microfono:
            from naoqi import ALBroker, ALModule
            self.audio = BufferAudio()
            self.callback_ip = callback_ip or ip_hacia(ip, port)
            self.callback_port = int(callback_port)
            self.broker = ALBroker(cadena_naoqi('NeoBroker_{}'.format(os.getpid())),
                cadena_naoqi(self.callback_ip), self.callback_port, ip_sdk, int(port))
            receptor = self.audio

            class ModuloAudio(ALModule):
                def __init__(self, nombre):
                    ALModule.__init__(self, cadena_naoqi(nombre))

                def processRemote(self, nbOfChannels, nbrOfSamplesByChannel, timeStamp, inputBuffer):
                    """Recibe los paquetes PCM de ALAudioDevice."""
                    receptor.recibir(nbOfChannels, nbrOfSamplesByChannel, inputBuffer)

            self.nombre_audio = 'NeoMicrofono_{}'.format(os.getpid())
            self.modulo = ModuloAudio(self.nombre_audio)
            # El SDK clasico busca el objeto Python en el espacio global.
            setattr(sys.modules['__main__'], self.nombre_audio, self.modulo)
            self.proxy_audio = ALProxy(cadena_naoqi('ALAudioDevice'), ip_sdk, int(port))
            # FRONTCHANNEL = 3; mono, 16 kHz, PCM16.
            self.proxy_audio.setClientPreferences(cadena_naoqi(self.nombre_audio), 16000, 3, 0)
            self.proxy_audio.subscribe(cadena_naoqi(self.nombre_audio))
            self.suscrito_audio = True
            fin = RELOJ() + 5
            with self.audio.condicion:
                while not self.audio.secuencia and not self.audio.error and RELOJ() < fin:
                    self.audio.condicion.wait(0.1)
            if not self.audio.secuencia or self.audio.error:
                raise RuntimeError('No llegaron muestras del microfono NAO. Revisa la IP de retorno {} y '
                                   'el puerto {} del Python NAOqi en la red privada de Windows.'.format(
                                       self.callback_ip, self.callback_port))

    def estado(self):
        return {'origen': 'nao', 'version_naoqi': self.version,
                'salida_audio': self.salida_audio,
                'camara': {'activa': self.camara is not None,
                           'tamano': self.camara.ultimo_tamano if self.camara else None},
                'microfono': self.audio.estado() if self.audio else None,
                'callback_ip': self.callback_ip, 'callback_port': self.callback_port}

    def cerrar(self):
        if self.suscrito_audio:
            try:
                self.proxy_audio.unsubscribe(cadena_naoqi(self.nombre_audio))
            except Exception:
                pass
            self.suscrito_audio = False
        if self.broker:
            try:
                self.broker.shutdown()
            except Exception:
                pass
            self.broker = None
        if self.nombre_audio and hasattr(sys.modules['__main__'], self.nombre_audio):
            delattr(sys.modules['__main__'], self.nombre_audio)
        self.modulo = None
        if self.camara:
            try:
                self.camara.cerrar()
            except Exception:
                pass
            finally:
                self.camara = None


class ServidorSensores(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class PeticionSensores(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def responder(self, codigo, datos, tipo='application/json', cabeceras=None):
        if tipo == 'application/json':
            datos = json.dumps(datos, ensure_ascii=True).encode('utf-8')
        self.send_response(codigo)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(datos)))
        self.send_header('Cache-Control', 'no-store')
        for nombre, valor in (cabeceras or {}).items():
            self.send_header(nombre, str(valor))
        self.end_headers()
        self.wfile.write(datos)

    def autorizado(self):
        if self.headers.get('X-Neo-Token') != self.server.token:
            self.responder(403, {'error': 'sesion_no_valida'})
            return False
        return True

    def do_GET(self):
        if not self.autorizado():
            return
        url = urlsplit(self.path)
        sensores = self.server.sensores
        try:
            if url.path == '/estado':
                self.responder(200, sensores.estado())
            elif url.path == '/camara' and sensores.camara:
                datos, ancho, alto, marca = sensores.camara.frame()
                self.responder(200, datos, 'application/octet-stream',
                    {'X-Neo-Ancho': ancho, 'X-Neo-Alto': alto, 'X-Neo-Marca': marca, 'X-Neo-Formato': 'BGR8'})
            elif url.path == '/audio' and sensores.audio:
                secuencia = int(parse_qs(url.query).get('desde', ['0'])[0])
                self.responder(200, sensores.audio.desde(secuencia))
            else:
                self.responder(404, {'error': 'fuente_no_habilitada'})
        except Exception as error:
            self.responder(503, {'error': str(error)})

    def do_POST(self):
        if not self.autorizado():
            return
        if self.path == '/cerrar':
            self.responder(200, {'cerrando': True})
            hilo = threading.Thread(target=self.server.shutdown)
            hilo.daemon = True
            hilo.start()
        else:
            self.responder(404, {'error': 'operacion_no_valida'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--robot-ip', required=True)
    parser.add_argument('--robot-port', type=int, default=9559)
    parser.add_argument('--puerto', type=int, default=5006)
    parser.add_argument('--indice-camara', type=int, choices=(0, 1), default=0)
    parser.add_argument('--sin-camara', action='store_true')
    parser.add_argument('--sin-microfono', action='store_true')
    parser.add_argument('--callback-ip')
    parser.add_argument('--callback-port', type=int, default=5007)
    args = parser.parse_args()
    token = os.environ.get('NEO_SENSORES_TOKEN', '')
    if not token:
        parser.error('Inicia este proceso mediante probar_choregraphe.py o iniciar_examen.py.')
    sensores, servidor = SensoresNAO(), None
    try:
        sensores.abrir(args.robot_ip, args.robot_port, not args.sin_camara,
                       not args.sin_microfono, args.indice_camara, args.callback_ip, args.callback_port)
        servidor = ServidorSensores(('127.0.0.1', args.puerto), PeticionSensores)
        servidor.sensores, servidor.token = sensores, token
        print('Sensores NAO:', json.dumps(sensores.estado(), ensure_ascii=True))
        print('SENSORES_LISTOS')
        sys.stdout.flush()
        servidor.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    except Exception as error:
        print('FALLO SENSORES NAO:', type(error).__name__, repr(error))
        traceback.print_exc()
        return 1
    finally:
        if servidor:
            servidor.server_close()
        sensores.cerrar()
    return 0


if __name__ == '__main__':
    sys.exit(main())
