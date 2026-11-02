# -*- coding: utf-8 -*-
"""Salida PCM y cliente del puente de voz. Compatible con Python 2.7 y 3."""
from __future__ import print_function, unicode_literals

import json
import os
import time
try:
    from urllib.request import Request, build_opener, ProxyHandler
    from urllib.error import HTTPError
except ImportError:
    from urllib2 import Request, build_opener, ProxyHandler, HTTPError

from naoqi_compat import cadena_naoqi

MAX_PCM = 24000 * 2 * 45


class ErrorAudio(RuntimeError):
    pass


class ErrorPuenteVoz(ErrorAudio):
    """Error local/nube: no debe provocar una busqueda de otro puerto NAOqi."""
    pass


def convertir_24mono_a_48estereo(pcm):
    if not pcm or len(pcm) % 2:
        raise ErrorAudio('PCM de entrada incompleto.')
    # Cada muestra firmada LE se duplica en tiempo y en los dos canales.
    return b''.join(pcm[i:i + 2] * 4 for i in range(0, len(pcm), 2))


class SalidaAudioNAO(object):
    def __init__(self, ip, puerto, sesion=None):
        if sesion is None:
            import qi
            sesion = qi.Session()
            sesion.connect(cadena_naoqi('tcp://{}:{}'.format(ip, int(puerto))))
        self.sesion = sesion
        self.audio = sesion.service(cadena_naoqi('ALAudioDevice'))
        if int(self.audio.getOutputVolume()) <= 0:
            raise ErrorAudio('El volumen del NAO esta en cero. Ajustalo antes de probar la voz.')
        try:
            if self.audio.isAudioOutMuted():
                raise ErrorAudio('La salida del NAO esta silenciada. Revisala antes de probar.')
        except ErrorAudio:
            raise
        except Exception:
            pass  # No todos los firmware exponen una consulta de silencio.

    def reproducir(self, pcm):
        if not pcm or len(pcm) % 2 or len(pcm) > MAX_PCM:
            raise ErrorAudio('PCM no valido o demasiado largo.')
        parametro = cadena_naoqi('outputSampleRate')
        anterior = int(self.audio.getParameter(parametro))
        reloj = getattr(time, 'monotonic', time.time)
        try:
            if anterior != 48000:
                self.audio.setParameter(parametro, 48000)
            inicio = reloj()
            enviados = 0
            # 2000 muestras mono -> 4000 tramas estereo / 16000 bytes.
            for posicion in range(0, len(pcm), 4000):
                bloque = convertir_24mono_a_48estereo(pcm[posicion:posicion + 4000])
                tramas = len(bloque) // 4
                if not self.audio.sendRemoteBufferToOutput(tramas, bytearray(bloque)):
                    raise ErrorAudio('ALAudioDevice rechazo el PCM. No se puede confirmar la salida de voz.')
                enviados += tramas
                restante = inicio + enviados / 48000.0 - reloj()
                if restante > 0:
                    time.sleep(restante)
            # Margen de vaciado antes de restaurar la tasa; el SDK solo confirma aceptacion.
            time.sleep(.1)
        finally:
            if anterior != 48000:
                self.audio.setParameter(parametro, anterior)

    def cerrar(self):
        self.sesion.close()


class ClienteVoz(object):
    def __init__(self, puerto=5008, token=None, salida=None):
        self.puerto = int(puerto)
        self.token = token or os.environ.get('NEO_VOZ_TOKEN', '')
        if not self.token:
            raise ErrorAudio('Falta la sesion efimera del puente de voz.')
        self.salida = salida
        self.http = build_opener(ProxyHandler({}))  # El puente local no pasa por proxies.

    def decir(self, texto):
        cuerpo = json.dumps({'texto': texto}, ensure_ascii=True).encode('utf-8')
        solicitud = Request('http://127.0.0.1:{}/hablar'.format(self.puerto), data=cuerpo,
                            headers={'Content-Type': 'application/json', 'X-Neo-Voz': self.token})
        respuesta = None
        try:
            respuesta = self.http.open(solicitud, timeout=100)
            dato = respuesta.read(MAX_PCM + 1)
            if len(dato) > MAX_PCM:
                raise ErrorPuenteVoz('El puente devolvio demasiado audio.')
            if self.salida is not None:
                if respuesta.headers.get('Content-Type') != 'audio/pcm;rate=24000;channels=1':
                    raise ErrorPuenteVoz('El puente no devolvio el formato PCM esperado.')
                self.salida.reproducir(dato)
            elif json.loads(dato.decode('utf-8')).get('reproducido') != 'pc':
                raise ErrorPuenteVoz('El puente no confirmo la reproduccion en la laptop.')
        except HTTPError as error:
            try:
                mensaje = json.loads(error.read(4096).decode('utf-8')).get('error', '')
            except (ValueError, UnicodeError):
                mensaje = ''
            raise ErrorPuenteVoz(mensaje or 'El puente de voz rechazo la solicitud.')
        except ErrorAudio:
            raise
        except Exception:
            raise ErrorPuenteVoz('Fallo el puente local de voz. Revisa la consola Python 3.')
        finally:
            if respuesta is not None:
                respuesta.close()

    def cerrar(self):
        if self.salida is not None:
            self.salida.cerrar()
