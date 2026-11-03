# Naoqi: piedra, papel o tijera

Juego para NAO V6 con reconocimiento de manos, conversación con Codex y voz.
Naoqi elige antes de recibir el gesto del jugador, anuncia su jugada y calcula
el resultado en Python. La personalidad es competitiva, graciosa y respetuosa.

## Requisitos

- Laptop Windows con Python 3.11 de 64 bits.
- SDK NAOqi 2.8 para Python 2.7, configurado en `C:\Python27\python.exe`.
  El SDK se instala por separado; usa el entorno compatible con Choregraphe 2.8.7.4.
- NAO V6 y laptop conectados a una red que permita la comunicación entre ambos.
- Codex CLI instalado y autenticado con tu cuenta: `codex login`.
- Internet para conversación, transcripción y voz OpenAI.
- Para voz OpenAI: clave de API con saldo. Se solicita oculta y no se guarda.

## Instalar

Desde la carpeta del repositorio:

```powershell
python instalar.py
```

El instalador crea o actualiza `.venv_neo`. El Python 2.7 del SDK se conserva
separado del Python 3 de visión y conversación.

## Jugar

Para utilizar la voz Verse y los movimientos:

```powershell
.\.venv_neo\Scripts\python.exe jugar.py --voz openai --movimientos
```

Introduce la IP que indique el NAO y la clave API cuando se soliciten.
También puedes pasar la IP con `--ip`.

El puerto NAOqi configurado es **9561**, con **9559** como alternativa.
Para seleccionar otro puerto:

```powershell
.\.venv_neo\Scripts\python.exe jugar.py --ip IP_DEL_NAO --robot-port 9561 --voz openai --movimientos
```

OpenAI usa saldo de API para generar la voz. Las frases fijas se preparan
en caché para la sesión. Codex genera las respuestas de conversación con
`gpt-6-luna`; la voz usa `gpt-realtime-2.1-mini` y `verse`.

La voz nativa está disponible mediante `--voz nao_tts`. Los movimientos se
activan con `--movimientos`; al omitirlo, el juego conserva voz y visión.
`--rondas 5` permite jugar cinco rondas en lugar de tres.

## Durante la partida

Di **empezar** para iniciar. Después de «Ya», muestra la mano completa y
mantén piedra, papel o tijera frente a la cámara. Di **siguiente** para
avanzar, **pausa** para detenerte o **continuar** para reanudar.

Las preguntas se procesan directamente, sin palabra de activación. El
micrófono se bloquea mientras habla Naoqi para evitar que responda a su propia voz.

| Tecla | Acción |
| --- | --- |
| S | Empezar |
| N | Siguiente ronda |
| C | Continuar |
| P | Pausa |
| M | Marcador |
| R | Reglas |
| V o botón MIC | Silenciar o reactivar el micrófono |
| T | Escribir un mensaje |
| Esc | Cerrar el juego |

## Configuración

`config/naoqi.json` contiene el perfil de ejecución. Para guardar ajustes
propios sin alterar el archivo compartido:

```powershell
Copy-Item .\config\naoqi.json .\config\naoqi.local.json
```

`naoqi.local.json` se utiliza automáticamente y queda fuera de Git.

| Campo | Uso |
| --- | --- |
| `robot_ip`, `robot_port` | Dirección y puerto NAOqi |
| `python_naoqi` | Python 2.7 del SDK |
| `camara`, `microfono` | `nao` o `pc`; el micrófono admite `no` |
| `respaldo_pc` | Usar sensores de la laptop si los del NAO fallan |
| `callback_ip` | IP de la laptop accesible desde el NAO; se calcula si es `null` |
| `puerto_control` | Conexión local del juego, 5005 |
| `puerto_sensores`, `callback_port` | Sensores y retorno de audio, 5006 y 5007 |
| `puerto_voz` | Servicio local de voz OpenAI, 5008 |
| `voz`, `voz_openai` | `nao_tts` u `openai`, y voz `verse` |


## Personalidad y respuestas

- `POLITICAS_NEO.md`: personalidad y reglas de conversación; se recarga en cada consulta.
- `personalidad_naoqi.py`: saludo, anuncios y frases fijas del juego.
- `AGENTS.md`: reglas breves para mantener el proyecto con Codex.

Las reglas, los puntos y las jugadas pertenecen al controlador. El modelo
propone respuestas y acciones permitidas; no envía órdenes de articulaciones.

## Archivos principales

| Archivo | Función |
| --- | --- |
| `jugar.py` | Entrada única del programa |
| `instalar.py`, `requirements.txt` | Preparación del entorno |
| `ejecucion_nao.py`, `conexion_naoqi.py` | Arranque y conexión del SDK |
| `vision_ia.py`, `gestos.py` | Landmarks, clasificación y estabilidad del gesto |
| `robot_server_ia.py`, `estado_juego.py` | Sesión, arbitraje y movimientos |
| `agente_juego.py` | Estrategia estadística de la jugada |
| `cliente_neo.py`, `ia_neo.py`, `codex_neo.py` | Conversación y protocolo |
| `sensores_nao.py`, `sensores_cliente.py` | Cámara y micrófono |
| `voz_openai.py`, `audio_neo.py` | Generación y reproducción de voz |
| `naoqi_compat.py` | Compatibilidad de cadenas con Python 2.7 |

El agente combina exploración con frecuencias y transiciones del historial
confirmado. La cámara reconoce el gesto mostrado y permite arbitrar la ronda.
Los modelos de MediaPipe se utilizan preentrenados.
