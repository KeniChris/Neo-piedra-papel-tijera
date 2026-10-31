"""Cliente Python 3 del puente local de camara y audio del NAO."""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request


class ErrorSensores(OSError):
    pass


class ClienteSensores:
    def __init__(self, puerto=5006, token=None):
        if not 1 <= int(puerto) <= 65535:
            raise ErrorSensores('Puerto de sensores no valido.')
        self.base = 'http://127.0.0.1:{}'.format(int(puerto))
        self.token = token or os.environ.get('NEO_SENSORES_TOKEN', '')
        if not self.token:
            raise ErrorSensores('Falta la sesion del puente de sensores. Usa iniciar_examen.py.')

    def solicitar(self, ruta, limite=262144, metodo='GET'):
        request = urllib.request.Request(self.base + ruta, method=metodo,
                                         headers={'X-Neo-Token': self.token})
        try:
            with urllib.request.urlopen(request, timeout=3) as respuesta:
                datos = respuesta.read(limite + 1)
                cabeceras = respuesta.headers
        except urllib.error.HTTPError as error:
            detalle = ''
            try:
                detalle = json.loads(error.read(4096).decode('utf-8')).get('error', '')
            except (ValueError, UnicodeError, AttributeError):
                pass
            raise ErrorSensores('Puente de sensores HTTP {}: {}'.format(error.code, detalle)) from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ErrorSensores('No responde el puente local de sensores NAO.') from error
        if len(datos) > limite:
            raise ErrorSensores('El puente de sensores devolvio mas datos de los permitidos.')
        return datos, cabeceras

    def json(self, ruta):
        datos, _ = self.solicitar(ruta)
        try:
            valor = json.loads(datos.decode('utf-8'))
            if not isinstance(valor, dict):
                raise ValueError('Se esperaba un objeto')
            return valor
        except (ValueError, UnicodeError) as error:
            raise ErrorSensores('Respuesta JSON no valida del puente de sensores.') from error

    def estado(self):
        estado = self.json('/estado')
        if estado.get('origen') != 'nao':
            raise ErrorSensores('La fuente no se identifica como el puente de sensores NAO.')
        return estado

    def frame(self):
        datos, cabeceras = self.solicitar('/camara', limite=640 * 480 * 3)
        try:
            ancho, alto = int(cabeceras['X-Neo-Ancho']), int(cabeceras['X-Neo-Alto'])
            marca = cabeceras['X-Neo-Marca']
            if (not 1 <= ancho <= 640 or not 1 <= alto <= 480 or not marca or
                    cabeceras['X-Neo-Formato'] != 'BGR8' or len(datos) != ancho * alto * 3):
                raise ValueError('Formato incorrecto')
        except (ValueError, KeyError, TypeError) as error:
            raise ErrorSensores('Fotograma NAO incompleto o con formato inesperado.') from error
        return datos, ancho, alto, marca

    def cerrar(self):
        try:
            self.solicitar('/cerrar', metodo='POST')
        except ErrorSensores:
            pass


class CamaraRemota:
    def __init__(self, cliente):
        self.cliente = cliente
        self.cerrada = False
        self.ultima_marca = None

    def isOpened(self):
        return not self.cerrada and self.cliente.estado().get('camara', {}).get('activa', False)

    def read(self):
        if self.cerrada:
            return False, None
        import numpy as np
        datos, ancho, alto, marca = self.cliente.frame()
        if marca == self.ultima_marca:
            raise ErrorSensores('La camara NAO repitio un fotograma; no se contara como una deteccion nueva.')
        self.ultima_marca = marca
        return True, np.frombuffer(datos, dtype=np.uint8).reshape(alto, ancho, 3).copy()

    def release(self):
        self.cerrada = True


class CamaraConRespaldo:
    """Mantiene NAO mientras funcione y cambia una vez a la webcam autorizada."""
    def __init__(self, cv2, origen='pc', fuente=0, puerto=5006, permitir_respaldo=False):
        self.cv2, self.fuente = cv2, fuente
        self.origen = origen
        self.permitir_respaldo = permitir_respaldo
        self.cambio = False
        self.cap = None
        try:
            self.cap = CamaraRemota(ClienteSensores(puerto)) if origen == 'nao' else cv2.VideoCapture(fuente)
            if origen == 'nao' and not self.cap.isOpened():
                raise ErrorSensores('La camara NAO no esta activa.')
        except (OSError, RuntimeError) as error:
            if origen != 'nao' or not permitir_respaldo:
                raise
            self.activar_pc(error)

    def activar_pc(self, error):
        if self.cap:
            self.cap.release()
        print('RESPALDO CAMARA: {}. Intentando webcam PC.'.format(error), flush=True)
        self.origen = 'pc'
        self.cambio = True
        self.cap = self.cv2.VideoCapture(self.fuente)
        if not self.cap.isOpened():
            raise ErrorSensores('La webcam PC de respaldo tampoco se pudo abrir.')

    def isOpened(self):
        return self.cap.isOpened()

    def read(self):
        try:
            ok, frame = self.cap.read()
            if self.origen == 'nao' and not ok:
                raise ErrorSensores('La camara NAO dejo de entregar imagenes.')
            return ok, frame
        except (OSError, RuntimeError) as error:
            if self.origen != 'nao' or not self.permitir_respaldo:
                raise
            self.activar_pc(error)
            return self.cap.read()

    def release(self):
        if self.cap:
            self.cap.release()


class FlujoPCM:
    def __init__(self, cliente):
        self.cliente = cliente
        self.buffer = bytearray()
        self.secuencia = 0
        self.cerrado = False
        self.descartar()

    def descartar(self):
        estado = self.cliente.estado().get('microfono')
        if not estado or estado.get('error') or estado.get('paquetes', 0) < 1:
            raise ErrorSensores('El microfono NAO no esta entregando audio valido.')
        if (estado.get('sample_rate'), estado.get('sample_width'), estado.get('canales')) != (16000, 2, 1):
            raise ErrorSensores('El audio NAO debe ser PCM mono de 16 bits y 16000 Hz.')
        self.secuencia = estado['paquetes']
        self.buffer.clear()

    def read(self, muestras):
        if self.cerrado or not 1 <= muestras <= 16384:
            raise ErrorSensores('Lectura de microfono no valida.')
        longitud = muestras * 2
        fin = time.monotonic() + 2
        while len(self.buffer) < longitud:
            if time.monotonic() >= fin:
                raise ErrorSensores('No llegaron muestras nuevas del microfono NAO.')
            respuesta = self.cliente.json('/audio?desde={}'.format(self.secuencia))
            try:
                secuencia = respuesta['secuencia']
                if type(secuencia) is not int or secuencia < self.secuencia or respuesta.get('discontinuidad'):
                    raise ValueError('Perdida de continuidad')
                datos = base64.b64decode(respuesta['pcm'], validate=True)
                if len(datos) > 128000 or len(datos) % 2:
                    raise ValueError('Tamano no valido')
                if datos and secuencia <= self.secuencia:
                    raise ValueError('Audio repetido')
                self.secuencia = secuencia
                self.buffer.extend(datos)
            except (ValueError, KeyError, TypeError) as error:
                raise ErrorSensores('Audio NAO incompleto, repetido o sin continuidad.') from error
        resultado = bytes(self.buffer[:longitud])
        del self.buffer[:longitud]
        return resultado

    def close(self):
        self.cerrado = True
        self.buffer.clear()


def fuente_audio_nao(sr, cliente):
    class FuenteNAO(sr.AudioSource):
        def __init__(self):
            self.CHUNK = 1024
            self.SAMPLE_RATE = 16000
            self.SAMPLE_WIDTH = 2
            self.stream = None

        def __enter__(self):
            self.stream = FlujoPCM(cliente)
            return self

        def __exit__(self, *args):
            if self.stream:
                self.stream.close()
                self.stream = None

    return FuenteNAO()
