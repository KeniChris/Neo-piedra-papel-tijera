# Neo conversacional — NAO V6

Prototipo académico de piedra, papel o tijera con conversación contextual.
Python controla las rondas y el marcador; Codex genera respuestas cortas con
la personalidad de `POLITICAS_NEO.md`. Un puente NAOqi envía los textos al
robot virtual de Choregraphe o al NAO físico configurado por el equipo.

La visión conserva el clasificador recibido: MediaPipe Hands localiza la mano
y reglas geométricas clasifican el gesto visible como piedra, papel o tijera.
**El modelo de anticipación propuesto todavía no está implementado ni entrenado.**
Neo elige al azar antes de observar la jugada del participante.

## Modo de examen con el robot físico

Sigue **[EXAMEN_NAO_V6.md](EXAMEN_NAO_V6.md)**. El perfil usa NAO V6,
Choregraphe 2.8.7.4, puerto 9559, cámara y micrófono del robot y voz nativa
`ALTextToSpeech`. La IP se pide al ejecutar. Prepara la laptop sin robot con
`python preparar_vision.py --examen` y comprueba después
`.\.venv_neo\Scripts\python.exe iniciar_examen.py --verificar-config`.

El día del examen, ejecuta primero `iniciar_examen.py --diagnostico` con ese
Python; si pasa, ejecuta `iniciar_examen.py`. La integración de sensores está
probada con SDK simulado; **la validación física sigue pendiente**.

El respaldo está activado: intenta sensores PC cuando falle un sensor NAO y,
si falla el destino físico al arrancar, prueba también 9561 y luego intenta
una vez el virtual de Choregraphe. El 9561 procede de la configuración del
proyecto compartido por el compañero; se mantiene 9559 como primer intento.
Pide el puerto virtual actual si falta. Puedes ensayarlo con
`.\.venv_neo\Scripts\python.exe iniciar_examen.py --virtual`. La ventana
indica destino y fuentes; la voz virtual se muestra en Robot View/Dialog.

## Puesta en marcha en Windows

Se usan dos intérpretes: Python 3.11 de 64 bits para cámara y conversación,
y el Python del SDK NAOqi para el puente. La instalación del equipo utiliza
`C:\Python27\python.exe`; puedes cambiarla con `--python-naoqi`.
Codex CLI debe estar instalado y autenticado con una sesión propia de ChatGPT.
Consulta [LEEME.md](LEEME.md) para esos requisitos.

Prepara la visión desde la carpeta del proyecto:

```powershell
python preparar_vision.py
```

Cuando termine con `VISION_OK`, abre Choregraphe y su robot virtual. Copia el
puerto que muestra **Edit > Preferences > Virtual Robot > NAOqi state**.
El siguiente ejemplo usa el puerto 61778 observado durante las pruebas;
sustitúyelo por el puerto actual de tu instalación:

```powershell
.\.venv_neo\Scripts\python.exe probar_choregraphe.py --robot-ip 127.0.0.1 --robot-port 61778 --vision
```

Con la ventana de cámara seleccionada, pulsa **S** para iniciar, muestra y
mantén tu gesto después de «Ya», y pulsa **N** para otra ronda. **T** permite
escribir una pregunta para la IA; **Esc** termina. `--movimientos` activa
las poses del programa recibido. El modo por defecto mantiene quieto el robot.

Para probar solo la conversación por texto y la salida NAOqi:

```powershell
python probar_choregraphe.py --robot-ip 127.0.0.1 --robot-port 61778
```

Escribe `Hola Neo, preséntate sin comenzar la partida` y espera su respuesta.
En el virtual, el texto puede aparecer en Robot View o Dialog sin audio.

## Organización

| Archivo | Propósito |
| --- | --- |
| [EXAMEN_NAO_V6.md](EXAMEN_NAO_V6.md) | Preparación sin robot y diagnóstico el día del examen |
| [config/neo_examen.json](config/neo_examen.json) | Perfil de robot, fuentes de sensores y modelo |
| [POLITICAS_NEO.md](POLITICAS_NEO.md) | Personalidad y reglas de conversación; se recarga por consulta |
| [PRUEBAS_CHOREGRAPHE.md](PRUEBAS_CHOREGRAPHE.md) | Pruebas del virtual y entrega al compañero para el robot físico |
| [LEEME.md](LEEME.md) | Arquitectura, instalación y detalles de funcionamiento |
| [SUBIR_A_GITHUB.md](SUBIR_A_GITHUB.md) | Primer envío y actualizaciones del repositorio |
| [AGENTS.md](AGENTS.md) | Contexto para continuar el proyecto con Codex |
| `tests/` | Pruebas del protocolo, reglas, adaptadores y diagnósticos |
| `originales/` | Copias sin modificar de los cinco archivos recibidos |

## Estado comprobado

- El usuario obtuvo una respuesta real de Codex con `gpt-6-luna` en su laptop.
- El usuario confirmó `PROXY_OK` y `NAOQI_OK` en su Choregraphe y ejecutó
  cuenta atrás y pausa automática.
- Pasaron 68 pruebas automatizadas, con CLI/API/SDK simulados y transporte
  local real; SpeechRecognition se comprobó con PCM sintético, sin hardware.
- MediaPipe Hands se instaló y procesó un fotograma vacío en Linux/Python 3.12;
  se comprobó la resolución de dependencias para Windows x64/Python 3.11.
- Falta comprobar con este entorno la webcam y el micrófono de la laptop,
  una respuesta de Luna enviada por el puente y la ejecución en el robot físico.

El lanzador anterior conserva webcam y micrófono PC como fuentes por defecto.
El modo de examen intenta primero cámara y micrófono NAO mediante un puente
del SDK, y permite respaldo PC según el perfil. No hay transmisión desde el reloj.

## Desarrollo

```powershell
python -m unittest discover -s tests -v
```

El repositorio incluye código, documentación y requisitos. `.gitignore`
excluye `.venv_neo`, cachés, sesiones y resultados locales; cada computadora
reconstruye su entorno con `preparar_vision.py` y configura su SDK NAOqi.
