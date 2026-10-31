# Contexto para continuar las pruebas de Neo

Lee `PRUEBAS_CHOREGRAPHE.md` y `POLITICAS_NEO.md` antes de cambiar el flujo.
El usuario ya obtuvo una respuesta real con Codex y `gpt-6-luna` (5282 ms).
Se trabaja primero con su Choregraphe y después con un NAO físico.

`probar_choregraphe.py` es Python 3 y lanza el intérprete NAOqi configurado.
`comprobar_naoqi.py`, `robot_server_ia.py`, `naoqi_compat.py` y `estado_juego.py` deben conservar
compatibilidad con Python 2.7. El intérprete del SDK original era
`C:\Python27\python.exe`. Copia IP y puerto del destino real; no los adivines.
El puerto virtual cambio de 62213 a 61778. El usuario ya obtuvo PROXY_OK y
NAOQI_OK en 127.0.0.1:61778 con el SDK real de Python 2.7. Se corrigio el paso
de Unicode al SDK clasico con cadena_naoqi. No pases Unicode directamente
a ALProxy bajo Python 2. El intento --vision fallo al cargar OpenCV/MediaPipe
en su Python 3.11; preparar_vision.py crea .venv_neo con versiones fijadas.

Las políticas se recargan por consulta. Las reglas y el marcador pertenecen
a Python. No introduzcas puntos, articulaciones o comandos de sistema en la
interfaz del modelo. Los clientes ejecutan solo acciones validadas para la
fase y versión actuales. Neo elige antes de la captura; no predice la jugada.

La visión recibida utiliza la webcam de la laptop y MediaPipe solutions.hands.
El modelo de anticipacion propuesto previamente no esta implementado ni
entrenado: la clasificacion actual usa reglas sobre los puntos de la mano.
No afirmes haber conectado la cámara interna del NAO o el reloj sin comprobarlo.
El modo `--simular` solo imprime mensajes: no equivale a probar Choregraphe.
Los tests del SDK y CLI usan dobles de prueba claramente identificados.

Ejecuta `python -m unittest discover -s tests -v` tras cambios en el protocolo,
el cargador o el lanzador. Registra por separado lo comprobado con dobles,
con Choregraphe y con hardware. No leas ni copies credenciales de Codex.
Mantén los originales recibidos sin modificar en `originales/`.
