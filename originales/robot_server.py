# -*- coding: utf-8 -*-
import socket, random, time, threading
from naoqi import ALProxy

IP, PROXY = "127.0.0.1", 54743
tts = ALProxy("ALTextToSpeech", IP, PROXY)
postura = ALProxy("ALRobotPosture", IP, PROXY)
motion = ALProxy("ALMotion", IP, PROXY)
leds = ALProxy("ALLeds", IP, PROXY)

try:
    tts.setLanguage("Spanish")
except Exception:
    pass  # en el simulador puede no estar instalado

JUGADAS = ("piedra", "papel", "tijera")
GANA = set([("piedra", "tijera"), ("papel", "piedra"), ("tijera", "papel")])
META = 3

BLANCO, AZUL, VERDE, ROJO, AMARILLO = 0xFFFFFF, 0x0000FF, 0x00FF00, 0xFF0000, 0xFFFF00

INICIO = threading.Event()
ultima = [None, 0]          # [seña, momento en que se vio]
marcador = {"yo": 0, "humano": 0}


def ojos(color):
    leds.fadeRGB("FaceLeds", color, 0.3)


# ---------- Movimiento ----------
def brazo(pitch, codo, t):
    motion.angleInterpolation(["RShoulderPitch", "RElbowRoll"],
                              [[pitch], [codo]], [[t], [t]], True)

def mano(abierta):
    motion.setAngles("RHand", 1.0 if abierta else 0.0, 0.6)
    time.sleep(0.5)

def sacudir():
    """Anima 'piedra, papel o tijera, ya' con 3 golpes de brazo."""
    mano(False)
    brazo(-0.5, 1.0, 0.8)                      # sube el brazo
    tts.post.say("Piedra, papel o tijera, ya")  # no bloquea
    for _ in range(3):
        brazo(0.3, 1.0, 0.35)                  # baja
        brazo(-0.5, 1.0, 0.35)                 # sube

def mostrar(jugada):
    if jugada == "piedra":
        mano(False)
        brazo(0.0, 0.5, 0.8)
    elif jugada == "papel":
        mano(True)
        brazo(0.0, 0.1, 0.8)      # brazo extendido hacia adelante
    else:  # tijera
        mano(True)
        brazo(-1.2, 0.3, 0.8)     # brazo apuntando hacia arriba


# ---------- Comunicación ----------
def lector(conn):
    for linea in conn.makefile():
        l = linea.strip()
        if l == "START":
            INICIO.set()
        elif l in JUGADAS:
            ultima[0], ultima[1] = l, time.time()

def leer_sena():
    if ultima[0] and time.time() - ultima[1] < 1.0:
        return ultima[0]
    return None


# ---------- Juego ----------
def ronda():
    """Devuelve False si no se vio ninguna seña (no cuenta)."""
    ojos(AZUL)
    ultima[0] = None
    sacudir()
    time.sleep(0.3)
    humano = leer_sena()
    if humano is None:
        ojos(BLANCO)
        tts.say("No vi tu jugada, intenta otra vez")
        return False

    robot = random.choice(JUGADAS)
    mostrar(robot)

    if humano == robot:
        ojos(AMARILLO)
        frase = "Empate"
    elif (humano, robot) in GANA:
        ojos(ROJO)
        marcador["humano"] += 1
        frase = "Ganaste esta ronda"
    else:
        ojos(VERDE)
        marcador["yo"] += 1
        frase = "Gané yo"

    tts.say("Yo saqué {}. {}".format(robot, frase))
    tts.say("Marcador: yo {}, tú {}".format(marcador["yo"], marcador["humano"]))
    return True

def partida():
    marcador["yo"] = marcador["humano"] = 0
    tts.say("Vamos a jugar. El primero en llegar a {} gana".format(META))
    while marcador["yo"] < META and marcador["humano"] < META:
        postura.goToPosture("StandInit", 0.7)
        time.sleep(1.0)
        ronda()
    if marcador["yo"] > marcador["humano"]:
        tts.say("Gané la partida. Mejor suerte la próxima")
    else:
        tts.say("Ganaste la partida. Felicidades")
    postura.goToPosture("StandInit", 0.7)
    ojos(BLANCO)
    tts.say("Di empezar para jugar de nuevo")


# ---------- Main ----------
postura.goToPosture("StandInit", 0.7)
ojos(BLANCO)

srv = socket.socket()
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", 5005))
srv.listen(1)
print("Esperando al lado de visión...")
conn, _ = srv.accept()
t = threading.Thread(target=lector, args=(conn,))
t.daemon = True
t.start()

tts.say("Di empezar para jugar")
while True:
    INICIO.wait()
    INICIO.clear()
    partida()
    INICIO.clear()   # ignora "empezar" acumulados durante la partida