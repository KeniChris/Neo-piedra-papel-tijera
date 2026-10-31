# Neo conversacional — NAO V6

Prototipo académico de piedra, papel o tijera con conversación contextual.
Python controla las rondas y el marcador; Codex genera respuestas cortas con
la personalidad de `POLITICAS_NEO.md`. Un puente NAOqi envía los textos al
robot virtual de Choregraphe o al NAO físico configurado por el equipo.

La visión conserva el clasificador recibido: MediaPipe Hands localiza la mano
y reglas geométricas clasifican el gesto visible como piedra, papel o tijera.
**El modelo de anticipación propuesto todavía no está implementado ni entrenado.**
Neo elige al azar antes de observar la jugada del participante.

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
- Pasaron 39 pruebas automatizadas con dobles de CLI/API/SDK, sin hardware.
- MediaPipe Hands se instaló y procesó un fotograma vacío en Linux/Python 3.12;
  se comprobó la resolución de dependencias para Windows x64/Python 3.11.
- Falta comprobar con este entorno la webcam y el micrófono de la laptop,
  una respuesta de Luna enviada por el puente y la ejecución en el robot físico.

La cámara utilizada actualmente es la webcam de la laptop. El micrófono
opcional también es el de la laptop. La cámara interna y los micrófonos del
NAO no se han integrado en este paquete. No hay transmisión desde el reloj.

## Desarrollo

```powershell
python -m unittest discover -s tests -v
```

El repositorio incluye código, documentación y requisitos. `.gitignore`
excluye `.venv_neo`, cachés, sesiones y resultados locales; cada computadora
reconstruye su entorno con `preparar_vision.py` y configura su SDK NAOqi.
