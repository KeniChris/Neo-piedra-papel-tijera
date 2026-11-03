# Naoqi

La entrada del juego es `jugar.py`. `instalar.py` prepara `.venv_neo`.

## Conversación

- `POLITICAS_NEO.md` define las respuestas del personaje y se recarga por consulta.
- Conserva el nombre Naoqi, el humor competitivo y respetuoso y las respuestas breves en español.
- El micrófono acepta peticiones sin palabra de activación; V y el botón MIC lo silencian.
- Codex usa `gpt-6-luna`; la salida OpenAI usa Realtime y la voz Verse.
- El estado de Python es la autoridad del juego. El modelo solo propone acciones validadas.
- Mantén la elección del robot antes de la captura humana y los bloqueos por versión y token.

## Mantenimiento

- Conserva Python 2.7 en `conexion_naoqi.py`, `robot_server_ia.py`, `sensores_nao.py`, `audio_neo.py`, `naoqi_compat.py`, `estado_juego.py`, `agente_juego.py` y `personalidad_naoqi.py`.
- Los formatos `struct` del SDK son bytes; las cadenas pasan por `cadena_naoqi`.
- Conserva los ángulos y velocidades del robot, la pausa y el regreso a StandInit.
- La clave API se solicita oculta y solo permanece en el proceso de voz.
- Cancela y libera únicamente los procesos y recursos creados por esta aplicación.
