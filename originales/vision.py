import cv2, socket, time, threading
import mediapipe as mp
import speech_recognition as sr

sock = socket.socket()
sock.connect(("127.0.0.1", 5005))
lock = threading.Lock()

def enviar(msg):
    with lock:
        sock.sendall((msg + "\n").encode())

# ---------- Voz ----------
PALABRAS = ("empezar", "empieza", "jugar", "vamos", "comenzar")

def escuchar():
    r = sr.Recognizer()
    with sr.Microphone() as mic:
        r.adjust_for_ambient_noise(mic)
        while True:
            try:
                audio = r.listen(mic, phrase_time_limit=3)
                texto = r.recognize_google(audio, language="es-PE").lower()
                print("Oí:", texto)
                if any(p in texto for p in PALABRAS):
                    enviar("START")
            except Exception:
                pass

threading.Thread(target=escuchar, daemon=True).start()

# ---------- Visión ----------
hands = mp.solutions.hands.Hands(max_num_hands=1,
                                 min_detection_confidence=0.7,
                                 min_tracking_confidence=0.7)
cap = cv2.VideoCapture(0)

def d(a, b):
    return ((a.x-b.x)**2 + (a.y-b.y)**2) ** 0.5

def dedos_extendidos(lm):
    muneca = lm[0]
    pares = [(8,6), (12,10), (16,14), (20,18)]
    return [d(lm[t], muneca) > d(lm[p], muneca) * 1.1 for t, p in pares]

def pulgar_extendido(lm):
    palma = d(lm[0], lm[9])
    # distancia de la punta del pulgar al nudillo del índice y al del medio
    sep = min(d(lm[4], lm[5]), d(lm[4], lm[9]))
    # y que la punta esté más lejos de la muñeca que su articulación media
    alejado = d(lm[4], lm[0]) > d(lm[3], lm[0]) * 1.05
    return sep > palma * 0.55 and alejado

def clasificar(lm):
    i, m, a, p = dedos_extendidos(lm)
    palma = d(lm[0], lm[9])
    print("sep pulgar:", round(min(d(lm[4], lm[5]), d(lm[4], lm[9])) / palma, 2))
    # OK / pellizco: punta del pulgar tocando la del índice
    if d(lm[4], lm[8]) < palma * 0.35:
        return None

    if not (i or m or a or p):
        # puño solo si el pulgar está recogido (descarta pulgar arriba)
        return None if pulgar_extendido(lm) else "piedra"
    if i and m and a and p:
        return "papel"
    if i and m and not a and not p:
        return "tijera"
    return None

ultima, estable = None, 0
while True:
    ok, frame = cap.read()
    if not ok: break
    res = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    sena = clasificar(res.multi_hand_landmarks[0].landmark) if res.multi_hand_landmarks else None

    estable = estable + 1 if sena == ultima else 0
    ultima = sena
    if sena and estable >= 5:
        enviar(sena)          # el robot se queda con la más reciente

    cv2.putText(frame, str(sena), (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
    cv2.imshow("vision", frame)
    k = cv2.waitKey(1) & 0xFF
    if k == 27: break
    if k == ord("s"): enviar("START")   # respaldo si falla el micrófono