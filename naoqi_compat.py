# -*- coding: utf-8 -*-
"""Convierte textos en el limite con las extensiones nativas del SDK NAOqi.

El controlador conserva Unicode internamente. El SDK clasico de Python 2
recibe str UTF-8; los bindings de Python 3 reciben str de Python 3.
"""
from __future__ import unicode_literals

import sys

PYTHON_2 = sys.version_info[0] == 2
try:
    TIPO_TEXTO = unicode
except NameError:
    TIPO_TEXTO = str


def cadena_naoqi(texto):
    if PYTHON_2:
        return texto.encode('utf-8') if isinstance(texto, TIPO_TEXTO) else texto
    return texto.decode('utf-8') if isinstance(texto, bytes) else texto
