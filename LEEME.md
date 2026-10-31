# Neo conversacional

Integra conversacion con una IA real en la partida de piedra, papel o tijera.
La laptop ejecuta la vision, transcripcion y cliente de IA. El puente NAOqi
reproduce la voz y, si lo activas, los movimientos de tu script original.

## Perfil para el examen con NAO V6

Usa **[EXAMEN_NAO_V6.md](EXAMEN_NAO_V6.md)** para el robot fisico. Configura
Choregraphe 2.8.7.4, puerto 9559, camara y microfono NAO, voz ALTextToSpeech y
Luna. La IP se introduce ese dia. `python preparar_vision.py --examen` prepara
las dependencias; `iniciar_examen.py --verificar-config` comprueba software sin
robot; `iniciar_examen.py --diagnostico` comprueba la conexion y recepcion de
sensores antes de abrir la partida. Usa el Python de `.venv_neo` para esos
comandos. La integracion de software esta probada con dobles del SDK;
el ensayo en el robot fisico sigue pendiente.

Los ejemplos anteriores de `probar_choregraphe.py --vision` que aparecen abajo
conservan webcam y microfono PC. El perfil nuevo selecciona fuentes NAO de
forma expresa y no las sustituye por fuentes PC si fallan.

## Actualizacion: Choregraphe y politicas editables

Empieza por **[PRUEBAS_CHOREGRAPHE.md](PRUEBAS_CHOREGRAPHE.md)**. Usa tu
conexion Python 3 -> Python 2.7 -> ALProxy y permite probar desde una sola
terminal. `probar_choregraphe.py` comprueba NAOqi e inicia el puente y el
cliente; no requiere crear un bloque en Choregraphe. El puerto del virtual
se copia de **Edit > Preferences > Virtual Robot > NAOqi state**.

La personalidad esta en **[POLITICAS_NEO.md](POLITICAS_NEO.md)** y se recarga
en cada consulta, tanto para Codex como para la API opcional. El lanzador
selecciona Codex y `gpt-6-luna`, salvo que ya hayas elegido explicitamente
otro modelo en `NEO_CODEX_MODEL`. Los calculos del juego permanecen en Python.

El virtual puede mostrar lo dicho en Robot View o Dialog sin audio. El modo
`--simular` descrito mas abajo solo imprime texto y no conecta con Choregraphe.

Si falla al cargar OpenCV o `mp.solutions.hands`, prepara el entorno de vision:

```powershell
python preparar_vision.py
.\.venv_neo\Scripts\python.exe probar_choregraphe.py --robot-ip 127.0.0.1 --robot-port 61778 --vision
```

Ejecuta el segundo comando cuando el primero termine con **VISION_OK**.
La instalacion usa `requirements_vision.txt` y un entorno separado `.venv_neo`.
La conexion real de tu Choregraphe ya se confirmo en el puerto 61778; comprueba
el puerto actual si reinicias el virtual. Tu primer intento de vision fallo
en las dependencias; ahora el mensaje identifica la biblioteca y el detalle.

## Lo primero: Codex con tu cuenta ChatGPT

**Esta version usa Codex CLI por defecto. No necesita una clave ni comprar
creditos de OpenAI API.** Inicias sesion con tu cuenta de ChatGPT y consumes
tu uso disponible de Codex. No es ilimitado: si lo agotas, puedes esperar al
restablecimiento o decidir si quieres ampliar el uso. La aplicacion corre en
tu laptop, pero el modelo sigue en la nube y necesita internet.

1. Extrae de nuevo el ZIP actualizado en una carpeta nueva. Abre PowerShell alli.
2. Comprueba la CLI local:

   ```powershell
   codex --version
   ```

   Si no existe, instala la CLI oficial. Con Node.js y npm ya disponibles:

   ```powershell
   npm install -g @openai/codex
   ```

   Si tampoco existe npm, usa las instrucciones de instalacion de Windows
   de la [CLI oficial](https://learn.chatgpt.com/docs/codex/cli).
   Estar usando Codex en esta conversacion no implica tener la CLI instalada
   en tu computadora. Usa una version reciente que admita las opciones del paquete.

3. Inicia sesion y elige **Sign in with ChatGPT**:

   ```powershell
   codex login
   codex login status
   ```

   El navegador completa el acceso; el paquete no pide ni copia tus contrasenas
   o archivos de autenticacion. En esta modalidad se comprueba que el estado
   de la CLI indique ChatGPT, en lugar de una sesion con clave de API.

4. Usa Python 3 (el mismo entorno donde funciona vision.py) y selecciona Codex:

   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   . .\USAR_CODEX.ps1
   python probar_ia.py
   ```

   La politica de ejecucion solo cambia para esta terminal. No se necesitan
   paquetes de pip para esta primera prueba. Si Python no aparece, abre el
   entorno Python 3 de tu companero; no necesitas el lanzador `py`.

5. Una consulta real correcta muestra **CODEX REAL: respuesta recibida**, la
   respuesta, su accion propuesta y el tiempo total, incluido el arranque de la CLI.
   No contacta con el robot ni abre la camara.

El adaptador usa `codex exec` y salida JSON con esquema. No hace consultas por
cada imagen de video. Limita la conversacion a peticiones y comentarios entre
rondas; debemos medir si su demora resulta adecuada. Si falla o agota el uso,
**no cambia automaticamente a la API de pago** ni inventa una respuesta de IA.

Al ejecutar directamente `probar_ia.py`, el modelo es el predeterminado de
Codex si no configuras `NEO_CODEX_MODEL` ni `--modelo`. Para repetir tu prueba
correcta con Luna usa `python probar_ia.py --modelo gpt-6-luna`.

## Que usan realmente los archivos que enviaste

- `robot_server.py`: apunta a NAOqi en **127.0.0.1:54743**, tipico del simulador
  local. Los archivos por si solos no demuestran conexion al robot fisico.
- `vision.py`: usa **cv2.VideoCapture(0)**, la webcam de la laptop. No contiene
  una suscripcion a la camara del NAO.
- La voz ya se transcribe con `SpeechRecognition.recognize_google`; el original
  solo aprovecha palabras de inicio. Ahora pueden enviarse preguntas a la IA.

Las copias exactas de los cinco archivos recibidos estan en `originales/`;
incluyen tambien `prueba.py` y `prueba_naoqui.py`. Esta ultima copia conserva
los comentarios y comillas recibidos; para probar usa los scripts nuevos.
El paquete es una version separada; no reemplaza tus archivos al extraerlo.
La integracion nueva de camara interna esta en `sensores_nao.py` y
`sensores_cliente.py`. Se usa mediante el perfil de examen o las opciones
`--camara-nao` y `--microfono-nao` del lanzador. La webcam sigue disponible.

## Segunda comprobacion: que Neo diga una respuesta de IA

Primero comprueba que NAOqi ya funciona con tu instalacion actual.
La guia PRUEBAS_CHOREGRAPHE.md automatiza los dos procesos descritos aqui.

**Terminal del puente:** usa el mismo interprete y configuracion NAOqi con el
que ejecutabas el `robot_server.py` original. El puente nuevo admite Python 2.7
y Python 3; el interprete real debe poder importar `naoqi`.

Para el simulador local (puerto del archivo recibido):

```text
python robot_server_ia.py --robot-ip 127.0.0.1 --robot-port 54743
```

Para el robot fisico, sustituye por su IP y su puerto NAOqi reales. El puerto
habitual es 9559, pero confirma el que ya use tu companero:

```text
python robot_server_ia.py --robot-ip IP_REAL_DE_NEO --robot-port 9559
```

Por defecto se utiliza solamente la voz: no se ejecutan posturas ni movimientos.
No ejecutes a la vez el servidor viejo y el nuevo: ambos usan el puerto 5005.

**Terminal Python 3 con Codex seleccionado e inicio de sesion completado:**

```powershell
python conversar.py --robot
```

Escribe `Hola Neo, presentate en una frase sin iniciar la partida`.
Cuando Codex conteste, Neo debe decir esa respuesta. Esta prueba no abre
la camara. Cierra `conversar.py` escribiendo `salir` antes de abrir vision.
Cada conexion nueva al puente inicia una sesion de juego nueva.

Para probar solo conversacion en la laptop, sin conectar NAOqi:

```powershell
python conversar.py
```

En esa modalidad las acciones se muestran pero no se ejecutan; no hay
partidas observadas ni marcador de una camara.

## Tercera comprobacion: partida completa con vision y conversacion

En el puente elige 3 o 5 rondas. Los empates cuentan como una ronda valida;
los gestos invalidos y la ausencia de gesto no suman ronda ni puntos.
El numero de rondas es fijo, a diferencia del original que esperaba llegar
a 3 puntos y podia alargarse mucho mas.

```text
python robot_server_ia.py --robot-ip IP_REAL_DE_NEO --robot-port 9559 --rondas 3 --movimientos
```

`--movimientos` activa los movimientos del archivo original, con los mismos
angulos, articulaciones y velocidades. La IA no genera trayectorias ni angulos.
Para cambiar a 5 usa `--rondas 5`. Puedes probar primero omitiendo movimientos.

En el **entorno Python 3 donde ya funciona vision.py**, con Codex preparado:

```powershell
python vision_ia.py --microfono
```

Puedes reutilizar el entorno donde ya funcionen OpenCV y MediaPipe de tu
companero o crear uno con `python preparar_vision.py`. El entorno nuevo prepara
camara y control por teclado/texto. Para usar `--microfono` necesita ademas
SpeechRecognition y PyAudio, como el original. La IA usa la biblioteca estandar.
La vision conserva la API **mp.solutions.hands** del original; no actualices
MediaPipe sin comprobar compatibilidad. Si esa API no existe, se explica el
fallo al iniciar. Se necesita una webcam libre; `--camara 1` permite probar
otro indice. No hay un modelo nuevo de reconocimiento de manos en este paquete.

### Uso en la partida

- Espera a que Neo termine de hablar antes de hablarle.
- Di **empezar** para la primera ronda.
- Al oir **ya**, muestra y manten tu jugada ante la camara. Conservamos el
  clasificador geometrico del original. Un puno visible despues de la senal
  puede contarse como piedra; no se esta detectando si tu brazo sigue arriba.
- La captura utiliza solo imagenes posteriores a la apertura de esa ventana
  y exige seis clasificaciones consecutivas iguales. La ventana dura 3 segundos.
- Si no se ve una jugada valida en ese plazo, pasa a **pausa** y permite reintentar.
- Entre rondas puedes conversar: **Neo, por que perdi?**, **Neo, no estoy de
  acuerdo con ese punto**, **Neo, vas a perder**, **Neo, explicame las reglas**.
- Di **siguiente** cuando quieras la proxima ronda. No avanza mientras quieras hablar.
- La IA tambien intenta hacer un comentario breve despues de cada ronda.
  Usa `--sin-comentarios` si prefieres que responda solo cuando le hablen.
- Di **pausa** o **espera** para solicitar una pausa; **continuar** para reanudar.
  Si hay una interpolacion del brazo en curso, primero termina esa operacion.
  No es un mecanismo de parada de emergencia.
- Las conversaciones por voz requieren **Neo** al inicio, salvo los comandos
  cortos exactos. Asi las conversaciones de otras personas no activan el robot
  tan facilmente. No se interpreta "no quiero jugar" como la orden empezar.
- Tras 3 o 5 rondas validas anuncia el resultado. Una revancha abre otra partida.

### Teclado de respaldo

Con la ventana de video seleccionada:

| Tecla | Accion |
| --- | --- |
| S | Empezar |
| N / C | Siguiente / continuar |
| P | Pausa |
| R | Reglas |
| M | Marcador |
| T | Abre una entrada de texto en la terminal para conversar con la IA |
| Esc | Cierra la vision |

Sin `--microfono`, se conserva el control por teclado y texto. Esto permite
comprobar la IA aunque falte PyAudio o falle la transcripcion de Google.

## Como funciona la IA

Codex recibe el contexto por entrada estandar y devuelve un JSON con `accion`
y `texto`. Corre desde una carpeta temporal y en sandbox de solo lectura,
sin cargar la configuracion personal de herramientas del usuario. La CLI se
encarga del inicio de sesion; nuestro codigo no lee su archivo de credenciales.
Los procesos hijos no reciben OPENAI_API_KEY ni CODEX_API_KEY.

Las acciones permitidas son hablar, iniciar, pausar, continuar, reglas y marcador.
El puente valida la fase y version del estado antes de aceptarlas. Una respuesta
de otra ronda se descarta. La API opcional usa el mismo contrato mediante
una funcion con parametros estrictos.

El modelo recibe el estado real calculado por Python y el texto del jugador.
No recibe imagenes, coordenadas de articulaciones ni acceso para editar puntos.
Las reglas, el marcador y las jugadas quedan en el codigo determinista.
Las frases de reglas y marcador se generan directamente desde ese codigo.
La IA puede equivocarse en una frase libre: prueba sus comentarios con
resultados reales antes de la presentacion. No se garantiza que nunca cometa errores.

Neo elige su jugada al azar **antes** de abrir la captura humana y la conserva
si hay que reintentar la ronda. Esta version no predice la intencion del jugador.
El aporte nuevo es conversacion contextual y coordinacion de acciones.

La transcripcion del microfono conserva Google, como en el codigo original.
El audio va a ese servicio; a OpenAI se envia texto transcrito y el estado.
El programa no guarda audio ni video en archivos. En modo Codex se utiliza la
CLI oficial con tu sesion ChatGPT. En el modo API opcional, la clave se envia
solo a `https://api.openai.com/v1/responses`; nunca forma parte del estado del juego.
Los errores no imprimen cuerpos remotos ni cabeceras con credenciales.

Solo se mantiene un historial breve en memoria; se reinicia al cambiar de partida.
Cada consulta tiene un limite de espera y no se reintenta automaticamente. Si falla,
las reglas y el control por teclado siguen disponibles y se informa el fallo.

## Alternativa opcional: OpenAI API

Usa esta opcion solo si eliges una cuenta de API con clave y creditos. Ser una
prueba local no hace que las llamadas de API sean gratuitas. Es una modalidad
distinta del inicio de sesion con ChatGPT en Codex.

```powershell
Set-ExecutionPolicy -Scope Process Bypass
. .\CONFIGURAR_IA.ps1
python probar_ia.py
```

Ese script selecciona explicitamente `NEO_IA_PROVIDER=openai` y solicita una
clave con entrada oculta. El modelo API configurable por defecto es
`gpt-5.6-luna`; tu cuenta debe tener acceso. En este modo la prueba imprime
**API REAL**. Para volver al uso de Codex ejecuta `. .\USAR_CODEX.ps1`.

## Comprobar los procesos sin robot ni API

Terminal 1, cualquier Python 3:

```powershell
python robot_server_ia.py --simular
```

Terminal 2, entorno de vision:

```powershell
python vision_ia.py --sin-ia
```

Esta modalidad muestra explicitamente **ROBOT SIMULADO** y **SIN IA**.
No constituye una prueba de voz, movimientos fisicos ni respuestas de un LLM.

## Validacion realizada

Se ejecutaron 53 pruebas automatizadas en Python 3, con CLI/API y SDK/robot simulados:
las nueve combinaciones de jugadas, limite de rondas, empates, reintentos,
marcador, captura identificada por ventana, conexion TCP local entre procesos,
contexto antiguo, cancelacion de decisiones pendientes, comandos con negacion,
lista de acciones, campos extra rechazados, fallos de API y manejo de la clave.
Tambien se comprobo el recorrido respuesta de modelo simulado -> TCP real local
-> voz simulada -> confirmacion e historial, sin alterar el marcador.
El adaptador Codex se comprueba con una CLI FALSA de pruebas: JSON, entrada
estandar, rechazo de login API, retirada de claves del entorno hijo, timeout
y ausencia de fallback a pagos. Esa CLI falsa no se usa en la aplicacion normal.
Se comprobo tambien la recarga del Markdown en ambos transportes, UTF-8 con
BOM, errores de archivo antes de consultar, independencia del directorio de
trabajo, el lanzador con un SDK falso en un proceso aparte, mensajes con
acentos, confirmacion de voz por TCP y cierre del puente sin movimientos.
Se agregaron cuatro regresiones para el limite del SDK clasico: cadenas
UTF-8, constructor y voz, nombres de postura/articulaciones/luces, y errores
con etapa y detalle. Estas pruebas simulan los requisitos de tipos de Python
2 desde Python 3; no sustituyen una ejecucion con el SDK real del usuario.
Los diagnosticos de vision distinguen falta de cv2, fallo de MediaPipe y falta
de la API legacy; el modo --diagnostico no crea una IA ni conecta con NAOqi.
Las pruebas de examen agregan transporte HTTP local de imagenes BGR y PCM,
validacion de formatos y continuidad, descarte de audio anterior al turno,
registro de callbacks y cierre de suscripciones. El diagnostico completo se
ejecuta en procesos con un SDK falso, sin iniciar el juego ni mover articulaciones.
SpeechRecognition real se comprobo con una fuente de PCM sintetico; esta prueba
se omite si no esta instalada la dependencia de examen. No usa Google ni un microfono real.

Tambien se instalo realmente el entorno de requirements_vision.txt en Linux
con Python 3.12: pip check paso y Hands proceso un fotograma vacio. Se comprobo
la resolucion de paquetes binarios para Windows x64 / Python 3.11 sin instalarlos
en Windows. La webcam y el funcionamiento en Windows siguen pendientes.

```powershell
python -m unittest discover -s tests -v
```

La CLI y API fueron simuladas en estas pruebas. En tu laptop ya confirmaste
una consulta real con Codex y `gpt-6-luna`, de 5282 ms, con la version anterior.
La latencia con estas politicas y el recorrido completo deben medirse alli.
Codex CLI no esta instalado ni autenticado en este entorno de trabajo.
No se han probado aqui webcam, microfono, PowerShell, NAOqi ni el robot fisico.
Tras corregir la conversion de Unicode y comprobar el puerto, el usuario
obtuvo PROXY_OK y NAOQI_OK en 127.0.0.1:61778 con su SDK real Python 2.7.
Tambien ejecuto empezar, cuenta atras y pausa automatica en Choregraphe.
Esa orden directa no demuestra todavia una respuesta de Luna dentro del puente.
El puente de sensores nuevo evita sintaxis exclusiva de Python 3, pero su
ejecucion con Python 2.7/NAOqi y los sensores fisicos sigue pendiente.

## Archivos

| Archivo | Funcion |
| --- | --- |
| EXAMEN_NAO_V6.md | Preparacion y arranque el dia del examen |
| config/neo_examen.json | Perfil con fuentes NAO, puerto y modelo |
| iniciar_examen.py | Verificacion sin robot y arranque con perfil |
| sensores_nao.py | Captura de imagen y PCM con el SDK Python 2.7 |
| sensores_cliente.py | Fuentes remotas para OpenCV y SpeechRecognition |
| requirements_examen.txt | Vision y transcripcion del microfono NAO |
| POLITICAS_NEO.md | Personalidad y reglas de conversacion editables |
| PRUEBAS_CHOREGRAPHE.md | Pasos en tu laptop y entrega al companero |
| AGENTS.md | Contexto para continuar el trabajo con Codex |
| probar_choregraphe.py | Lanza el puente NAOqi y el cliente desde Python 3 |
| comprobar_naoqi.py | Comprueba ALTextToSpeech sin IA ni movimientos |
| naoqi_compat.py | Adapta cadenas al SDK clasico Python 2 y a Python 3 |
| preparar_vision.py | Crea .venv_neo, instala y comprueba el detector |
| requirements_vision.txt | Versiones compatibles con el clasificador recibido |
| probar_ia.py | Primera consulta real a Codex o API; sin paquetes Python adicionales |
| conversar.py | Conversacion por texto y opcion de salida por Neo |
| ia_neo.py | Cliente de IA, prompt y funcion disponible |
| codex_neo.py | Adaptador Codex CLI con inicio de sesion ChatGPT |
| USAR_CODEX.ps1 | Selecciona Codex; no pide clave API |
| robot_server_ia.py | Puente NAOqi y control de la partida |
| estado_juego.py | Reglas y marcador, compatible con Python 2.7 y 3 |
| vision_ia.py | Vision, microfono opcional PC/NAO e integracion de IA |
| cliente_neo.py | Protocolo y control de respuestas tardias |
| gestos.py | Geometria del clasificador recibido |
| originales/ | Copias sin modificar de tus archivos |

## Documentacion consultada

- [OpenAI: funciones](https://developers.openai.com/api/docs/guides/function-calling).
- [Codex: autenticacion con ChatGPT](https://learn.chatgpt.com/docs/auth).
- [Codex: uso desde scripts y salidas estructuradas](https://learn.chatgpt.com/docs/non-interactive-mode).
- [Codex: planes y limites](https://learn.chatgpt.com/docs/pricing).
- [OpenAI: agentes de voz](https://developers.openai.com/api/docs/guides/voice-agents).
- [OpenAI: primera llamada y claves](https://developers.openai.com/api/docs/quickstart).
- [OpenAI: modelo configurable por defecto](https://developers.openai.com/api/docs/models/gpt-5.6-luna).
- [Choregraphe: preferencias y puerto del virtual](https://doc.aldebaran.com/2-5/software/choregraphe/choregraphe_preference.html).
- [ALTextToSpeech: diferencias entre robot virtual y fisico](https://doc.aldebaran.com/2-5/naoqi/audio/altexttospeech.html).
- [MediaPipe 0.10.21: binarios Python 3.11 para Windows x64](https://pypi.org/project/mediapipe/0.10.21/).
- [OpenCV contrib 4.11.0.86: instalacion y variante unica de cv2](https://pypi.org/project/opencv-contrib-python/4.11.0.86/).
- Para NAOqi, se parte de tus scripts y de los enlaces que adjuntaste en
  `originales/Scriptsindicacines (1).txt`.

31 de octubre de 2026.
