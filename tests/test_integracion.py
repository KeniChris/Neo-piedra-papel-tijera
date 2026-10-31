"""Pruebas sin API real, webcam, microfono ni robot fisico."""
import copy
import io
import json
import os
import socket
import sys
import threading
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cliente_neo import ConexionNeo, Conversador, procesar_texto
from estado_juego import EstadoJuego, JUGADAS, texto_hablable
from ia_neo import CerebroNeo, ErrorIA, FUNCION, interpretar_respuesta
from robot_server_ia import Robot, Sesion


def respuesta_falsa(accion='hablar', texto='Hola, juguemos cuando quieras.'):
    return {'status': 'completed', 'output': [
        {'type': 'function_call', 'name': FUNCION,
         'arguments': json.dumps({'accion': accion, 'texto': texto})}]}


def esperar(condicion, timeout=3):
    fin = time.monotonic() + timeout
    while time.monotonic() < fin:
        if condicion():
            return
        time.sleep(0.01)
    raise AssertionError('No se cumplio la condicion esperada.')


class PruebasReglas(unittest.TestCase):
    def test_nueve_combinaciones_y_preseleccion(self):
        gana = {('piedra', 'tijera'), ('tijera', 'papel'), ('papel', 'piedra')}
        for humano in JUGADAS:
            for robot in JUGADAS:
                with self.subTest(humano=humano, robot=robot):
                    g = EstadoJuego(elegir=lambda _: robot)
                    g.iniciar()
                    g.preparar_ronda()
                    self.assertEqual(g._jugada_neo, robot)
                    self.assertNotIn('_jugada_neo', g.snapshot())
                    token = g.abrir_captura()
                    resultado = g.registrar(humano, token)
                    esperado = 'empate' if humano == robot else ('jugador' if (humano, robot) in gana else 'neo')
                    self.assertEqual(resultado['ganador'], esperado)
                    self.assertEqual(sum(g.marcador.values()), 0 if esperado == 'empate' else 1)

    def test_cinco_rondas_incluyen_empates(self):
        g = EstadoJuego(5, elegir=lambda _: 'piedra')
        g.iniciar()
        for _ in range(5):
            self.assertTrue(g.preparar_ronda())
            token = g.abrir_captura()
            self.assertIsNotNone(g.registrar('piedra', token))
        self.assertEqual(g.fase, 'terminada')
        self.assertEqual(g.completadas, 5)
        self.assertFalse(g.preparar_ronda())
        self.assertIn('empatados', g.frase_final())

    def test_reintento_no_cambia_eleccion(self):
        elecciones = iter(('papel', 'tijera'))
        g = EstadoJuego(elegir=lambda _: next(elecciones))
        g.iniciar(); g.preparar_ronda()
        viejo = g.abrir_captura()
        g.pausar('sin_jugada_valida')
        g.preparar_ronda()
        nuevo = g.abrir_captura()
        self.assertNotEqual(viejo, nuevo)
        self.assertIsNone(g.registrar('piedra', viejo))
        self.assertEqual(g._jugada_neo, 'papel')
        self.assertIsNone(g.registrar('invalido', nuevo))
        self.assertEqual(g.completadas, 0)

    def test_version_antigua_y_accion_fuera_de_lista(self):
        g = EstadoJuego()
        self.assertFalse(g.permite_agente(g.version, 'dar_puntos'))
        viejo = g.version
        g.iniciar()
        self.assertFalse(g.permite_agente(viejo, 'hablar'))
        g.preparar_ronda()
        self.assertFalse(g.permite_agente(g.version, 'hablar'))

    def test_texto_plano_sin_marcas_naoqi(self):
        self.assertEqual(texto_hablable('Hola \\vol=100\\ jugador\n'), 'Hola jugador')
        self.assertLessEqual(len(texto_hablable('a' * 900)), 280)


class PruebasAPI(unittest.TestCase):
    def test_parseo_estricto_y_campos_extra(self):
        self.assertEqual(interpretar_respuesta(respuesta_falsa())['accion'], 'hablar')
        malos = [
            {'status': 'incomplete', 'output': []},
            {'status': 'completed', 'output': 'incorrecto'},
            {'status': 'completed', 'output': []},
            respuesta_falsa('dar_puntos'),
        ]
        extra = respuesta_falsa()
        extra['output'][0]['arguments'] = '{"accion":"hablar","texto":"hola","puntos":99}'
        malos.append(extra)
        for malo in malos:
            with self.assertRaises(ErrorIA):
                interpretar_respuesta(malo)

    def test_payload_y_historia_por_partida(self):
        brain = CerebroNeo(transporte=lambda _: respuesta_falsa())
        g = EstadoJuego(); g.iniciar()
        p = brain.payload(g.snapshot(), 'Me llamo Ana')
        self.assertFalse(p['store'])
        self.assertFalse(p['parallel_tool_calls'])
        self.assertEqual(p['tool_choice']['name'], FUNCION)
        self.assertNotIn('OPENAI_API_KEY', json.dumps(p))
        brain.confirmar_hablado('Me llamo Ana', 'Hola Ana')
        estado2 = g.snapshot(); estado2['partida'] = 2
        p2 = brain.payload(estado2, 'Hola')
        self.assertNotIn('Ana', json.dumps(p2))

    def test_falta_clave_no_hace_solicitudes(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': ''}):
            with patch('urllib.request.urlopen') as http:
                with self.assertRaises(ErrorIA):
                    CerebroNeo(provider='openai')
                http.assert_not_called()

    def test_timeout_y_401_sin_filtrar_credenciales(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'SECRETO_DE_PRUEBA_NO_REAL'}):
            b = CerebroNeo(provider='openai')
            with patch('urllib.request.urlopen', side_effect=socket.timeout()):
                with self.assertRaises(ErrorIA):
                    b.responder(EstadoJuego().snapshot(), 'hola')
            err = urllib.error.HTTPError('https://api.openai.com', 401, 'error', {}, io.BytesIO(b'privado'))
            with patch('urllib.request.urlopen', side_effect=err):
                with self.assertRaises(ErrorIA) as resultado:
                    b.responder(EstadoJuego().snapshot(), 'hola')
                self.assertNotIn('SECRETO', str(resultado.exception))
                self.assertNotIn('privado', str(resultado.exception))


class ConexionFalsa:
    def __init__(self):
        self.state = EstadoJuego().snapshot()
        self.closed = threading.Event()
        self.sent = []
        self.commands = []
    def snapshot(self):
        return copy.deepcopy(self.state)
    def enviar(self, dato):
        self.sent.append(dato)
        return True
    def comando(self, dato):
        self.commands.append(dato)


class PruebasConversacion(unittest.TestCase):
    def test_negacion_no_arranca_y_nombre_activa_conversacion(self):
        c = ConexionFalsa()
        class ConversadorFalso:
            def __init__(self): self.textos = []
            def pedir(self, texto): self.textos.append(texto); return True
        b = ConversadorFalso()
        procesar_texto('no quiero jugar', c, b)
        self.assertEqual(c.commands, [])
        self.assertEqual(b.textos, ['no quiero jugar'])
        self.assertFalse(procesar_texto('hola todos', c, b, requiere_nombre=True))
        self.assertTrue(procesar_texto('Neo, por que perdi?', c, b, requiere_nombre=True))
        procesar_texto('Neo, pausa', c, b, requiere_nombre=True)
        self.assertEqual(c.commands, ['pausar'])

    def trabajador(self):
        c = ConexionFalsa()
        entro, liberar = threading.Event(), threading.Event()
        def transporte(_):
            entro.set()
            liberar.wait(2)
            return respuesta_falsa()
        b = Conversador(c, CerebroNeo(transporte=transporte))
        self.addCleanup(b.cerrar)
        self.addCleanup(liberar.set)
        return c, b, entro, liberar

    def test_descarta_respuesta_si_cambio_ronda(self):
        c, b, entro, liberar = self.trabajador()
        b.pedir('Hola')
        self.assertTrue(entro.wait(1))
        c.state['version'] += 1
        c.state['fase'] = 'cuenta_atras'
        liberar.set()
        esperar(lambda: not b.en_curso)
        self.assertEqual(c.sent, [])

    def test_comentario_no_reemplaza_pregunta_del_jugador(self):
        c, b, entro, liberar = self.trabajador()
        b.pedir('Como te llamas?')
        self.assertTrue(entro.wait(1))
        self.assertFalse(b.pedir('comenta', 'comentario_ronda'))
        liberar.set()
        esperar(lambda: len(c.sent) == 1)
        self.assertEqual(c.sent[0]['reply']['accion'], 'hablar')

    def test_cierre_no_envia_respuesta_tardia(self):
        c, b, entro, liberar = self.trabajador()
        b.pedir('Hola')
        self.assertTrue(entro.wait(1))
        b.cerrar()
        liberar.set()
        esperar(lambda: not b.en_curso)
        self.assertEqual(c.sent, [])

    def test_comando_directo_cancela_decision_ia_pendiente(self):
        c, b, entro, liberar = self.trabajador()
        b.pedir('Quiero jugar')
        self.assertTrue(entro.wait(1))
        b.cancelar()
        liberar.set()
        esperar(lambda: not b.en_curso)
        self.assertEqual(c.sent, [])


class PruebasSocket(unittest.TestCase):
    def setUp(self):
        self.server = socket.socket()
        self.server.bind(('127.0.0.1', 0))
        self.server.listen(1)
        self.sesion = None
        def atender():
            conn, _ = self.server.accept()
            self.sesion = Sesion(conn, Robot('', 0, simular=True), espera=0.25)
            self.sesion.estado.elegir = lambda _: 'piedra'
            try:
                self.sesion.run()
            finally:
                conn.close()
        self.thread = threading.Thread(target=atender, daemon=True)
        self.thread.start()
        self.c = ConexionNeo(port=self.server.getsockname()[1])
        self.c.esperar()

    def tearDown(self):
        self.c.cerrar()
        self.thread.join(2)
        self.server.close()
        self.assertFalse(self.thread.is_alive())

    def fase(self, fase):
        esperar(lambda: self.c.snapshot()['fase'] == fase)
        return self.c.snapshot()

    def test_partida_tres_rondas_por_tcp(self):
        self.c.comando('iniciar')
        for ronda in range(1, 4):
            estado = self.fase('capturando')
            token = estado['capture_id']
            self.c.enviar({'type': 'vision', 'capture_id': 'viejo', 'gesture': 'tijera'})
            self.c.enviar({'type': 'vision', 'capture_id': token, 'gesture': 'papel', 'hand_present': True})
            estado = self.fase('terminada' if ronda == 3 else 'entre_rondas')
            self.assertEqual(estado['rondas_completadas'], ronda)
            self.assertEqual(estado['marcador'], {'neo': 0, 'jugador': ronda})
            if ronda < 3:
                self.c.comando('continuar')
        self.c.comando('continuar')
        self.assertEqual(self.c.snapshot()['rondas_completadas'], 3)

    def test_timeout_pausa_sin_puntos_y_reintento(self):
        self.c.comando('iniciar')
        estado = self.fase('capturando')
        viejo = estado['capture_id']
        self.fase('pausa')
        self.assertEqual(self.c.snapshot()['rondas_completadas'], 0)
        self.c.comando('continuar')
        estado = self.fase('capturando')
        self.assertNotEqual(viejo, estado['capture_id'])
        self.c.enviar({'type': 'vision', 'capture_id': viejo, 'gesture': 'tijera'})
        self.c.enviar({'type': 'vision', 'capture_id': estado['capture_id'], 'gesture': 'piedra'})
        estado = self.fase('entre_rondas')
        self.assertEqual(estado['ultima_ronda']['ganador'], 'empate')

    def test_agente_no_puede_agregar_campos_ni_puntos(self):
        respuestas = []
        self.c.on_agent_result = respuestas.append
        self.c.enviar({'type': 'agent', 'context_version': self.c.snapshot()['version'],
                       'request_id': 12, 'reply': {'accion': 'hablar', 'texto': 'hola', 'puntos': 99}})
        esperar(lambda: len(respuestas) == 1)
        self.assertFalse(respuestas[0]['accepted'])
        self.assertEqual(self.c.snapshot()['marcador'], {'neo': 0, 'jugador': 0})

    def test_respuesta_modelo_llega_a_voz_y_se_confirma_por_tcp(self):
        texto = 'Hola, soy Neo y estoy listo para conversar.'
        brain = CerebroNeo(transporte=lambda _: respuesta_falsa(texto=texto))
        conversador = Conversador(self.c, brain, comentarios=False)
        self.addCleanup(conversador.cerrar)
        self.assertTrue(conversador.pedir('Presentate'))
        esperar(lambda: len(brain.historia) == 2)
        self.assertEqual(brain.historia[-1]['content'], texto)
        self.assertEqual(self.c.snapshot()['marcador'], {'neo': 0, 'jugador': 0})


if __name__ == '__main__':
    unittest.main()
