# Examen con Neo / NAO V6

Perfil preparado para la instalación indicada por el equipo: **NAO V6,
Choregraphe 2.8.7.4-win64-vs2015 y puerto NAOqi 9559**. No instala ni cambia
el firmware. La versión que tenga realmente el robot se consultará al conectar.
La IP se introduce ese día; no se reutiliza `127.0.0.1` del robot virtual.

La integración está implementada y comprobada con un SDK simulado. **La voz,
la cámara, los micrófonos y la partida completa en el NAO físico siguen
pendientes de validación.** Las pruebas de audio de otros compañeros son
un antecedente útil, pero usaban otro programa.

## Qué está seleccionado

| Parte | Configuración de examen |
| --- | --- |
| Cámara | NAO, índice 0, captura BGR 320 × 240 a 15 fps solicitados |
| Micrófono | NAO, audio mono de 16 bits a 16 kHz por el SDK |
| Transcripción | SpeechRecognition con Google, español de Perú; requiere internet |
| Conversación | Codex CLI con `gpt-6-luna` y `POLITICAS_NEO.md` |
| Voz del robot | `ALTextToSpeech`, solicita idioma Spanish |
| Partida | 3 rondas válidas; ventana de jugada de 3 segundos |
| Movimientos | Desactivados; se activan expresamente con `--movimientos` |
| Respaldo | Activado: sensores PC y un intento con Choregraphe virtual si falla el destino físico al arrancar |

La captura del chat describe **Gemini generando un audio que el robot reproduce**.
Este proyecto usa la voz nativa del NAO para leer el texto generado por Luna;
no incluye ese agente de Gemini. Para el micrófono NAO no hace falta PyAudio.
La selección está en [config/neo_examen.json](config/neo_examen.json).

## Preparar la laptop ahora, sin robot

Abre PowerShell en la carpeta del proyecto. Copia solo los comandos de los
bloques, sin `PS ... >` ni los mensajes de resultado.

Instala el entorno de cámara y transcripción:

```powershell
python preparar_vision.py --examen
```

Espera a que aparezcan `VISION_OK` y `TRANSCRIPCION_OK`. Después:

```powershell
.\.venv_neo\Scripts\python.exe iniciar_examen.py --verificar-config
```

Debe mostrar `SDK_OK` y `CONFIGURACION_OK`. Comprueba bibliotecas, importación
del SDK desde `C:\Python27\python.exe` y sesión de Codex. No contacta al robot,
no abre cámara ni micrófono y no hace una consulta al modelo. Si aún falta
configurar Codex, sigue [LEEME.md](LEEME.md); no copies credenciales entre laptops.
Si tu SDK está en otra ruta, cambia `python_naoqi` en el JSON.

Puedes ensayar ahora todo el respaldo con Choregraphe virtual, webcam y
micrófono de la laptop:

```powershell
.\.venv_neo\Scripts\python.exe iniciar_examen.py --virtual
```

Abre el robot virtual de Choregraphe. El programa pide su puerto **actual**,
visible en Edit > Preferences > Virtual Robot > NAOqi state. 61778 fue el que
funcionó antes; no se supone que siga siendo ese. Este modo no pide la IP del
NAO físico. La voz del virtual aparece como texto en Robot View/Dialog y puede
no reproducirse como audio. Ese ensayo no valida sensores ni audio del físico.

Puedes guardar el puerto actual en `puerto_virtual` del JSON o pasarlo con
`--puerto-virtual`. Si se queda en `null`, se pide al necesitar el virtual.
La preparación de examen instala PyAudio en Windows para el micrófono PC.
Si ese micrófono falla, permanecen disponibles las teclas y T.

## Al llegar al robot

Conecta la laptop y el robot a una red donde puedan comunicarse. Averigua la IP
actual del NAO. Mantén los archivos y el entorno preparados en esa misma laptop.
Evita ejecutar otro programa que controle simultáneamente la partida o la voz.

Primero ejecuta:

```powershell
.\.venv_neo\Scripts\python.exe iniciar_examen.py --diagnostico
```

Cuando diga `IP actual del NAO fisico >`, introduce solo la IP. Ya usa el
puerto **9559**. El diagnóstico solicita una frase de voz, obtiene una imagen
y espera paquetes reales de micrófono. Consulta versión, volumen y silencio
si el robot ofrece esos métodos. Termina sin iniciar el juego ni moverlo.

Comprueba `NAOQI_OK`, `SENSORES_NAO_OK` y `DIAGNOSTICO_COMPLETADO`. Además,
**alguien debe oír la frase**. Que `say` termine correctamente no demuestra
por sí solo que se haya escuchado. Recibir paquetes de audio tampoco demuestra
que se entiendan bien las palabras. El resumen queda en
`diagnosticos_locales/ultimo_examen.json`, sin grabaciones ni imágenes.

Si aparece `SENSORES_NAO_PARCIAL`, revisa `FUENTES SELECCIONADAS`: se ha activado
el respaldo de algún sensor. En ese caso el diagnóstico también intenta recibir
una imagen o muestras del PC para las fuentes que haya sustituido. Una webcam
PC que no entrega imágenes impide completar el diagnóstico; un micrófono PC
que falle deja el control por teclado. El archivo de resultados distingue el
destino NAOqi, las fuentes elegidas y qué pruebas PC pasaron.

Si ese paso termina bien, abre la demostración:

```powershell
.\.venv_neo\Scripts\python.exe iniciar_examen.py
```

Introduce de nuevo la IP. Verás la imagen recibida del NAO y el estado de las
fuentes. Luna genera una presentación breve al arrancar; espera a que Neo
termine de hablar. Di **«Neo, ¿estás listo para jugar?»** y comprueba en la
consola `Oi:` y la respuesta del modelo. Así se evalúa la conversación completa.
`gpt-6-luna` tardó unos 5,3 segundos en la consulta real anterior del usuario;
la demora de esta ejecución puede ser distinta.

Para jugar, di **«empezar»**. Muestra y mantén el gesto dentro de la imagen
después de «Ya». El detector exige seis fotogramas consecutivos iguales.
Di **«siguiente»** entre rondas o **«continuar»** si se pausó por falta de gesto.
Para preguntas libres, empieza con **«Neo»**. Habla cuando haya terminado su voz.

Con la ventana de cámara activa también puedes usar:

| Tecla | Acción |
| --- | --- |
| S | Empezar |
| N / C | Siguiente / continuar |
| P | Pausar el juego |
| M / R | Marcador / reglas |
| T | Escribir en la terminal para conversar |
| Esc | Cerrar el cliente y sus puentes |

El perfil inicial anuncia la jugada de Neo con voz. Para incluir las poses
del programa original, cierra la ejecución anterior y usa:

```powershell
.\.venv_neo\Scripts\python.exe iniciar_examen.py --movimientos
```

Las poses también requieren validación física. La tecla P pausa la partida;
no es una parada de emergencia del robot.

## Si falla algo ese día

Con `respaldo_choregraphe: true`, el perfil aplica este orden:

| Fallo | Respaldo |
| --- | --- |
| Conexión, voz o puente del destino físico durante el arranque | Cierra ese intento e intenta una vez el NAOqi virtual de Choregraphe; usa sensores PC y pide el puerto virtual si falta. |
| Cámara NAO | Intenta webcam PC y conserva voz/control y micrófono NAO si funcionan. |
| Micrófono NAO | Intenta micrófono PC y conserva cámara y voz/control que funcionen. |
| Micrófono PC | Muestra el fallo y deja teclas/T disponibles. |
| Cámara PC | Informa el fallo; no genera una imagen de prueba para simular reconocimiento. |

Si la cámara NAO deja de enviar imágenes durante la partida, cambia una vez a
PC, borra la cuenta de detecciones y solicita pausa. Pulsa C para reintentar
después de la pausa. El cambio de sensor conserva la sesión y el marcador.
Si falla el control/voz física durante una partida ya iniciada, conserva la
pausa/error del puente; puedes cerrar y lanzar `--virtual` para una demostración
nueva. El cambio completo al virtual al arrancar inicia una sesión nueva.
Cerrar normalmente, cancelar o un fallo local de dependencias no dispara el
cambio de destino. Si el virtual tampoco conecta, muestra el error y termina.

El modo y las fuentes reales aparecen en la ventana y la consola. El respaldo
virtual permite ensayar el software; no repara la cámara, el audio o la conexión
del robot físico. Si `say` termina sin error pero no se oye, compruébalo en el
robot: esa falta de audibilidad no puede detectarse solo con la respuesta del SDK.

| Síntoma | Qué revisar |
| --- | --- |
| No conecta con NAOqi | IP física, puerto 9559 y acceso entre laptop y robot. Un puerto del virtual no sirve para el físico. |
| No se oye la frase | Volumen y silencio en el NAO; conserva el aviso si no acepta Spanish. |
| No llegan muestras de micrófono | Mira `callback_ip` y `callback_port` impresos. El robot necesita volver a conectar a la laptop. Permite el Python del SDK en la red privada de Windows, sin desactivar el firewall. |
| Seleccionó otra tarjeta de red | Configura `callback_ip` con la IP de la laptop en la red del NAO; por defecto se deduce de la ruta al robot. |
| Cámara NAO sin imágenes | Conserva el error de ALVideoDevice y revisa otras suscripciones. `indice_camara_nao` permite elegir 0 o 1; confirma la vista antes de jugar. |
| Hay audio pero no transcribe | Internet y ruido del salón. Mira `Oi:`; usa T y las teclas si es necesario. |
| Falla Codex | Revisa sesión y uso disponible. Para demostrar solo visión y reglas, usa `iniciar_examen.py --sin-ia`; se identifica claramente como modo sin IA. |
| Puerto local ocupado | Cierra la ejecución anterior. Control 5005, sensores 5006 y callback 5007 tienen que ser distintos y estar disponibles. |

Puedes elegir webcam cambiando `camara` a `pc` en el JSON, o teclado cambiando
`microfono` a `no`. El micrófono `pc` necesita PyAudio. Para desactivar todos
los cambios automáticos, configura `respaldo_choregraphe` como `false`.
El lanzador manual mantiene el comportamiento estricto salvo que se le añada
`--respaldo-pc`.

## Alcance de la demostración

Esta versión clasifica la mano visible, calcula el ganador y conversa según
el estado del juego. No predice una jugada futura, no detecta presión ni usa
el reloj. Codex recibe texto y estado; la transcripción de voz se envía a
Google. No se envían las imágenes de la cámara al modelo conversacional.

Pasaron **65 pruebas automatizadas** sin NAO físico: protocolo, reglas, CLI
simulada, transporte local de imágenes y PCM, descarte de audio antiguo,
suscripciones y cierre de procesos. Una prueba usa SpeechRecognition real
con PCM sintético; se omite si no está instalado. También se ejecutó MediaPipe
Hands con una imagen vacía en Linux. Las pruebas de respaldo incluyen un fallo
del destino físico simulado seguido de conexión TCP real al puente de un SDK
falso, sin dispositivos ni consultas a un modelo real. Ninguna sustituye el
ensayo en el salón.

Referencias: [ALVideoDevice 2.8](https://doc.aldebaran.com/2-8/naoqi/vision/alvideodevice-api.html),
[ALAudioDevice](https://doc.aldebaran.com/2-5/naoqi/audio/alaudiodevice-api.html)
y [ALTextToSpeech](https://doc.aldebaran.com/2-5/naoqi/audio/altexttospeech.html).
