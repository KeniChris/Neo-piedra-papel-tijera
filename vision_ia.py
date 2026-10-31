"""Webcam y microfono del PC; conserva la geometria de vision.py recibido."""
import argparse
import importlib
import sys
import threading
import time

from cliente_neo import ConexionNeo, Conversador, procesar_texto
from gestos import clasificar
from ia_neo import CerebroNeo, ErrorIA


class ErrorVision(RuntimeError):
    pass


def cargar_dependencias():
    modulos = {}
    for nombre in ('cv2', 'mediapipe'):
        try:
            modulos[nombre] = importlib.import_module(nombre)
        except Exception as error:
            raise ErrorVision('No se pudo cargar {}: {}: {}'.format(
                nombre, type(error).__name__, error)) from error
    cv2, mp = modulos['cv2'], modulos['mediapipe']
    try:
        manos_clase = mp.solutions.hands.Hands
        if not callable(manos_clase):
            raise AttributeError('Hands no es una clase utilizable')
    except AttributeError as error:
        raise ErrorVision('MediaPipe {} ({}) no ofrece mp.solutions.hands.Hands. '
                          'Este codigo utiliza esa API; prepara el entorno compatible.'.format(
                              getattr(mp, '__version__', '?'), getattr(mp, '__file__', '?'))) from error
    return cv2, mp, manos_clase


def diagnosticar(cv2, mp, manos_clase):
    print('OpenCV:', getattr(cv2, '__version__', '?'), '|', getattr(cv2, '__file__', '?'))
    print('MediaPipe:', getattr(mp, '__version__', '?'), '|', getattr(mp, '__file__', '?'))
    try:
        import numpy as np
        with manos_clase(static_image_mode=True, max_num_hands=1) as detector:
            detector.process(np.zeros((128, 128, 3), dtype=np.uint8))
    except Exception as error:
        print('FALLO al inicializar o ejecutar Hands:', type(error).__name__, str(error))
        return 1
    print('VISION_OK: Hands inicializado y fotograma vacio procesado. No se abrio la camara ni se consulto la IA.')
    return 0


def escuchar(conexion, conversador):
    try:
        import speech_recognition as sr
        reconocedor = sr.Recognizer()
        reconocedor.operation_timeout = 5
        with sr.Microphone() as microfono:
            while not conexion.closed.is_set() and not conexion.voz_token()[1]:
                conexion.closed.wait(0.1)
            reconocedor.adjust_for_ambient_noise(microfono, duration=0.6)
            print('Microfono activo. Para conversar di Neo seguido de tu pregunta.')
            while not conexion.closed.is_set():
                token, libre = conexion.voz_token()
                if not libre:
                    conexion.closed.wait(0.1)
                    continue
                try:
                    audio = reconocedor.listen(microfono, timeout=1, phrase_time_limit=4)
                    if not conexion.voz_valida(token):
                        continue
                    texto = reconocedor.recognize_google(audio, language='es-PE')
                    if conexion.voz_valida(token):
                        print('Oi:', texto)
                        procesar_texto(texto, conexion, conversador, requiere_nombre=True)
                except sr.WaitTimeoutError:
                    continue
                except sr.UnknownValueError:
                    continue
                except sr.RequestError:
                    print('No se pudo transcribir con Google. Usa T para escribir o las teclas.')
                    conexion.closed.wait(1)
    except (ImportError, OSError, AttributeError) as error:
        print('Microfono no disponible:', type(error).__name__, '| Usa T para escribir.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camara', default='0', help='Indice de webcam o fuente OpenCV que ya utilicen.')
    parser.add_argument('--puerto', type=int, default=5005)
    parser.add_argument('--microfono', action='store_true')
    parser.add_argument('--sin-ia', action='store_true', help='Solo prueba local de vision y reglas; NO usa un modelo.')
    parser.add_argument('--sin-comentarios', action='store_true', help='La IA responde solo cuando el jugador le habla.')
    parser.add_argument('--diagnostico', action='store_true', help='Comprueba librerias y detector sin camara, Codex ni NAOqi.')
    args = parser.parse_args()
    print('Python de vision:', sys.executable)
    try:
        cv2, mp, manos_clase = cargar_dependencias()
    except ErrorVision as error:
        print('FALLO DE VISION:', error)
        print('Prepara el entorno compatible con: python preparar_vision.py')
        return 1
    if args.diagnostico:
        return diagnosticar(cv2, mp, manos_clase)
    cerebro = None
    if not args.sin_ia:
        try:
            cerebro = CerebroNeo()
        except ErrorIA as error:
            print(error)
            return 1
        print('Modelo: {} | Politicas: {}'.format(cerebro.model, cerebro.politicas_path.name))
    conexion = None
    conversador = None
    cap = None
    hands = None
    entrada_activa = threading.Event()
    try:
        conexion = ConexionNeo(port=args.puerto)
        conexion.esperar()
        if cerebro:
            conversador = Conversador(conexion, cerebro, comentarios=not args.sin_comentarios)
            print('IA configurada con {}; conexion real pendiente de la primera respuesta.'.format(cerebro.provider))
        else:
            print('MODO SIN IA: respuestas fijas y reglas locales. No es una demostracion de LLM.')
        if args.microfono:
            threading.Thread(target=escuchar, args=(conexion, conversador), daemon=True).start()

        def escribir():
            try:
                texto = input('Mensaje para Neo > ')
                procesar_texto(texto, conexion, conversador)
            except EOFError:
                pass
            finally:
                entrada_activa.clear()

        hands = manos_clase(max_num_hands=1, min_detection_confidence=0.7,
                            min_tracking_confidence=0.7)
        fuente = int(args.camara) if args.camara.isdigit() else args.camara
        cap = cv2.VideoCapture(fuente)
        if not cap.isOpened():
            print('No se pudo abrir la camara del PC. Comprueba --camara.')
            return 1
        print('Teclas: S empezar | N siguiente | P pausa | C continuar | R reglas | M marcador | T texto | Esc salir')
        ultimo_token = None
        ultima_sena = None
        estables = 0
        ultimo_envio = 0.0
        while not conexion.closed.is_set():
            estado_previo = conexion.snapshot()
            token = estado_previo.get('capture_id') if estado_previo else None
            ok, frame = cap.read()
            if not ok:
                print('La camara dejo de entregar imagenes.')
                break
            resultado = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            hay_mano = bool(resultado.multi_hand_landmarks)
            sena = clasificar(resultado.multi_hand_landmarks[0].landmark) if hay_mano else None
            estado = conexion.snapshot()
            actual_token = estado.get('capture_id') if estado else None
            # Si cambio la ventana durante la lectura de la imagen, se descarta.
            if token != actual_token:
                token = None
            if token != ultimo_token:
                ultima_sena, estables = None, 0
                ultimo_token = token
                ultimo_envio = 0
            if token:
                estables = estables + 1 if sena == ultima_sena else 1
                ultima_sena = sena
                ahora = time.monotonic()
                estable = sena if sena and estables >= 6 else None
                if ahora - ultimo_envio >= (0.1 if estable else 0.3):
                    conexion.enviar({'type': 'vision', 'capture_id': token,
                                     'gesture': estable, 'hand_present': hay_mano})
                    ultimo_envio = ahora
            else:
                ultima_sena, estables = None, 0
            fase = estado['fase'] if estado else 'sin estado'
            puntos = estado['marcador'] if estado else {'neo': 0, 'jugador': 0}
            if conversador is None:
                estado_ia = 'SIN IA - prueba de reglas'
            elif conversador.error:
                estado_ia = 'IA: ERROR - revisa consola'
            elif conversador.ultimo_tiempo_ms is None:
                estado_ia = 'IA: aun sin verificar'
            else:
                estado_ia = 'IA: {} OK {} ms'.format(cerebro.provider, conversador.ultimo_tiempo_ms)
            lineas = [
                'Gesto: {} | {}'.format(sena or 'invalido / sin mano', fase),
                'Neo {} - Jugador {}'.format(puntos['neo'], puntos['jugador']),
                estado_ia,
                'S inicio | N siguiente | P pausa | T conversar | ESC salir'
            ]
            if conexion.hello.get('simulado'):
                lineas.append('ROBOT SIMULADO - sin voz ni movimiento fisicos')
            for i, linea in enumerate(lineas):
                cv2.putText(frame, linea, (10, 30 + i * 27), cv2.FONT_HERSHEY_SIMPLEX,
                            0.55, (0, 255, 0), 1)
            cv2.imshow('Neo - vision y conversacion', frame)
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                break
            atajos = {ord('s'): 'iniciar', ord('n'): 'continuar', ord('p'): 'pausar',
                      ord('c'): 'continuar', ord('r'): 'reglas', ord('m'): 'marcador'}
            if key in atajos:
                conexion.comando(atajos[key])
            elif key == ord('t') and not entrada_activa.is_set():
                entrada_activa.set()
                threading.Thread(target=escribir, daemon=True).start()
    except (OSError, RuntimeError) as error:
        print('No se pudo completar la conexion:', error)
        return 1
    except KeyboardInterrupt:
        pass
    finally:
        if conversador:
            conversador.cerrar()
        if conexion:
            conexion.comando('pausar')
            conexion.cerrar()
        if cap:
            cap.release()
        if hands:
            hands.close()
        cv2.destroyAllWindows()
    return 0


if __name__ == '__main__':
    sys.exit(main())
