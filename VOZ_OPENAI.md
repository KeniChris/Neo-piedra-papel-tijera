# Voz OpenAI para Neo

Luna sigue generando las respuestas mediante Codex. Esta opcion convierte ese
texto y los avisos del juego en audio con OpenAI Realtime y la voz `marin`.
No sustituye las reglas, la camara ni la transcripcion del microfono.

**Implementacion comprobada con respuestas OpenAI y SDK simulados, HTTP/TCP
locales reales y PCM sintetico. Falta probar una solicitud real a OpenAI,
escuchar la laptop y escuchar el NAO fisico con este programa.** No hay una
clave de API en el proyecto y las pruebas automatizadas no consumen saldo.

## Saldo y clave

La voz usa facturacion API, separada del uso de Codex con ChatGPT Plus:

1. Abre [Billing](https://platform.openai.com/settings/organization/billing/overview)
   de tu organizacion de API e introduce el metodo de pago.
2. Compra inicialmente US$5 si solo quieres evaluar el prototipo. Es el minimo
   indicado por OpenAI. Revisa **Use auto-reload**: viene activado durante la
   configuracion; desactivalo si quieres recargar manualmente.
3. Crea una clave del proyecto en [API keys](https://platform.openai.com/api-keys).
   Guardala en tu gestor de contrasenas. No la pegues en el chat ni en GitHub.

Al ejecutar con voz OpenAI se pide la clave con entrada oculta, sin guardarla.
Si ya existe `OPENAI_API_KEY` en el entorno, se usa esa variable. No se leen
credenciales de Codex ni se copian a otra laptop. Los procesos de vision,
Codex y SDK no reciben la clave de voz; el puente SDK recibe un token local
efimero distinto. La clave de voz pertenece al proceso Python 3 que la necesita.

## Probar primero en la laptop

En PowerShell, dentro del proyecto:

```powershell
python preparar_vision.py --examen
.\.venv_neo\Scripts\python.exe probar_voz.py --solo-config
```

Esos pasos instalan/comprueban bibliotecas; no hacen consultas de pago. Cuando
tengas saldo y clave, escucha una frase:

```powershell
.\.venv_neo\Scripts\python.exe probar_voz.py
```

Pega la clave en la entrada oculta de la terminal y pulsa Enter. Esta prueba
hace una consulta de voz, reproduce por el dispositivo de salida predeterminado
de la laptop y guarda `grabaciones/neo_voz_openai.wav`. Esa carpeta esta excluida
de Git. No requiere Choregraphe, robot, camara ni una consulta a Luna.
`VOZ_OPENAI_REPRODUCIDA_PC` significa que la reproduccion termino sin error;
comprueba personalmente que la escuchaste. Puedes comparar otra voz:

```powershell
.\.venv_neo\Scripts\python.exe probar_voz.py --voz coral
```

## Usar la misma voz en la partida

Para ensayar con Choregraphe virtual:

```powershell
.\.venv_neo\Scripts\python.exe iniciar_examen.py --virtual --voz openai
```

Pide el puerto **actual** del virtual. Usa sus fuentes PC y reproduce OpenAI
por los parlantes de la laptop; la consola muestra el texto. Este modo no prueba
los altavoces del NAO. El HUD indica `openai` y la salida `pc`.

En el NAO fisico, primero diagnostica:

```powershell
.\.venv_neo\Scripts\python.exe iniciar_examen.py --voz openai --diagnostico
```

Introduce la IP actual. Se comprueba la conexion de salida antes de generar
la frase de pago. Debe aparecer `VOZ_OPENAI_ENVIADA`; alguien debe escucharla
en el robot. Si pasa, inicia la partida:

```powershell
.\.venv_neo\Scripts\python.exe iniciar_examen.py --voz openai
```

El arranque genera la frase de prueba y prepara dos frases de cuenta atras:
son consultas de pago. Las frases repetidas se reutilizan en memoria durante
esa ejecucion; no se vuelven a cobrar si salen de esa cache local. Al reiniciar
el programa se pierde la cache. Las respuestas nuevas de Luna necesitan audio
nuevo. No se promete respuesta instantanea ni una latencia ya medida.

`--voz-openai coral` cambia la voz en el lanzador. Tambien puedes seleccionar
`"voz": "openai"` y `"voz_openai": "marin"` en `config/neo_examen.json` para
no repetir la opcion. El perfil recibido conserva `nao_tts` por defecto para
que un arranque habitual no active consultas de pago. `--voz nao_tts` conserva
la voz nativa y no usa la API de audio.

Un fallo de clave, saldo o servicio de voz no cambia al virtual ni reintenta
automaticamente la consulta. Tras iniciar una prueba de audio de pago, tampoco
se repite automaticamente en otro puerto si el robot rechaza el PCM. Las
pruebas de conexion previas, sin consultas de voz, conservan el orden
9559 -> 9561 -> virtual del perfil. Puedes cerrar y elegir expresamente otra
salida para una prueba nueva.

## Consumo aproximado

Tarifas consultadas el **2 de noviembre de 2026**, en USD, para
`gpt-realtime-2.1-mini`: audio generado US$20 por millon de tokens;
texto de entrada US$0.60 y texto de salida US$2.40 por millon. OpenAI documenta
aproximadamente 20 tokens por segundo de audio de salida. El componente de
audio resulta asi en **US$0.024 por minuto generado**, mas el texto y cualquier
otro uso facturado. No son minutos de tener abierta la aplicacion.

| Audio nuevo generado | Componente estimado de audio |
| --- | --- |
| 10 minutos | US$0.24 |
| 30 minutos | US$0.72 |
| 60 minutos | US$1.44 |

No es una tarifa fija por partida: cambia cuanto habla Neo, cuantas frases
se generan, los reintentos manuales y los precios vigentes. Las respuestas
que lleguen a generarse pueden consumir aunque despues falle la reproduccion
o la comprobacion de transcripcion. Consulta el consumo real en
[Usage](https://platform.openai.com/usage). El programa guarda solo contadores
y una estimacion en `diagnosticos_locales/voz_openai_uso.jsonl`, sin clave ni
texto. Ese archivo no sustituye la facturacion del proveedor. Los creditos
comprados vencen al ano y el saldo prepago no garantiza un corte instantaneo.

## Transporte y limites

Python 3 solicita audio PCM mono de 24 kHz y 16 bits mediante WebSocket Realtime.
La respuesta se recibe completa y se compara su transcripcion con el texto
antes de reproducirla. Si cambia palabras o resultados, se rechaza; no se
reintenta automaticamente. Esta comprobacion puede rechazar una lectura
equivalente que use otra forma de escribir numeros. No garantiza por si sola
la pronunciacion ni la audibilidad; ambas requieren escuchar el resultado.

El servicio local escucha solo en `127.0.0.1:5008`, protegido con un token
efimero. No lo publiques en la red. El SDK Python 2.7 toma el PCM y lo convierte
a 48 kHz estereo para `qi.Session` / `ALAudioDevice.sendRemoteBufferToOutput`,
con bloques acotados y ritmo de reproduccion. Ajusta temporalmente
`outputSampleRate` y restaura su valor; no sube el volumen ni desactiva silencio.
El SDK confirma aceptacion de los bloques; la espera sigue su duracion nominal
mas un margen de vaciado. No ofrece una confirmacion de audibilidad fisica.
No usa `ALPythonBridge.eval` ni copia el codigo/credenciales del proyecto del
companero. Con esta voz, el fisico no necesita `ALTextToSpeech` para hablar.

El microfono permanece bloqueado mientras Neo genera y reproduce la frase.
La ventana de jugada abre despues de terminar `Ya`. Si la cuenta atras falla,
la ronda se pausa sin abrir captura ni sumar puntos. El controlador sigue
siendo la unica autoridad sobre acciones, marcador y movimientos.

Para voz se usa el flujo Realtime recomendado actualmente por OpenAI. No se
envia este modelo a `/v1/audio/speech`; los modelos antiguos de ese endpoint
estan anunciados para retirada el 6 de enero de 2027.

Fuentes oficiales: [facturacion prepago](https://help.openai.com/en/articles/8264644-setting-up-and-managing-prepaid-api-billing),
[modelo y tarifas](https://developers.openai.com/api/docs/models/gpt-realtime-2.1-mini),
[costos de Realtime](https://developers.openai.com/api/docs/guides/voice-latency-cost),
[texto a voz](https://developers.openai.com/api/docs/guides/text-to-speech),
[protocolo Realtime](https://developers.openai.com/api/docs/guides/realtime-conversations).
