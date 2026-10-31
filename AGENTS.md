# Contexto para continuar las pruebas de Neo

Lee `EXAMEN_NAO_V6.md`, `PRUEBAS_CHOREGRAPHE.md` y `POLITICAS_NEO.md` antes de cambiar el flujo.
El usuario ya obtuvo una respuesta real con Codex y `gpt-6-luna` (5282 ms).
El usuario no tendra acceso al robot fisico hasta el examen. Choregraphe es
2.8.7.4-win64-vs2015, robot NAO V6 y puerto fisico confirmado por el usuario
9559. La IP fisica es desconocida: se pide al ejecutar, no se inventa.

`probar_choregraphe.py` es Python 3 y lanza el intérprete NAOqi configurado.
`comprobar_naoqi.py`, `robot_server_ia.py`, `sensores_nao.py`, `naoqi_compat.py` y `estado_juego.py` deben conservar
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
El lanzador anterior mantiene fuentes PC por defecto. iniciar_examen.py usa
config/neo_examen.json: camara y microfono NAO, TTS nativo, Luna, tres rondas
y movimientos desactivados. sensores_nao.py usa ALVideoDevice y ALAudioDevice;
sensores_cliente.py entrega imagenes y PCM al cliente Python 3. El retorno
de audio requiere acceso del robot al broker de la laptop (callback 5007).
Los puentes HTTP/control son locales; no publiques sus puertos en la red.
El token de sensores es efimero y no se guarda. No hay fallback automatico
a sensores PC. No se ha integrado el agente Gemini mostrado en el chat.
El modelo de anticipacion propuesto previamente no esta implementado ni
entrenado: la clasificacion actual usa reglas sobre los puntos de la mano.
No afirmes haber validado la camara, microfonos ni voz del NAO fisico sin
comprobarlos. La integracion de software tiene pruebas con SDK simulado y PCM
sintetico; la observacion de los companeros corresponde a otro programa.
Un say sin error no acredita audibilidad ni paquetes PCM acreditan transcripcion.
No hay conexion al reloj.
El modo `--simular` solo imprime mensajes: no equivale a probar Choregraphe.
Los tests del SDK y CLI usan dobles de prueba claramente identificados.

Ejecuta `python -m unittest discover -s tests -v` tras cambios en el protocolo,
el cargador o el lanzador. Registra por separado lo comprobado con dobles,
con Choregraphe y con hardware. No leas ni copies credenciales de Codex.
Mantén los originales recibidos sin modificar en `originales/`.
