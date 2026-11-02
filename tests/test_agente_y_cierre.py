"""Estrategia, voz y gestos con dobles; sin API de pago ni motores reales."""
import json
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agente_juego import AgenteJugada, JUGADAS
from audio_neo import ClienteVoz, ErrorPuenteVoz
from cliente_neo import procesar_texto
from estado_juego import EstadoJuego
from personalidad_naoqi import INVITACION_APRETON, JINGLE_VICTORIA, SALUDO
from robot_server_ia import Robot, Sesion
from voz_openai import ErrorVoz, LectorOpenAI, ServicioVoz, normalizar_lectura
from test_voz_openai import WebSocketFalso, PCM


class PruebasAgente(unittest.TestCase):
    def test_azar_del_sistema_y_ningun_orden_fijo(self):
        self.assertIsInstance(AgenteJugada().azar, random.SystemRandom)
        azar = Mock(random=Mock(side_effect=[.9, .9, .1, .5]))
        agente = AgenteJugada(azar)
        self.assertEqual([agente.elegir() for _ in range(4)], ['tijera', 'tijera', 'piedra', 'papel'])
        self.assertTrue(all(abs(p - 1 / 3) < 1e-8 for p in agente.pesos().values()))

    def test_frecuencias_y_transiciones_sin_eliminar_la_exploracion(self):
        agente = AgenteJugada()
        for gesto in ['piedra'] * 5:
            agente.observar(gesto)
        self.assertEqual(max(agente.pesos(), key=agente.pesos().get), 'papel')
        self.assertTrue(all(p >= .5 / 3 for p in agente.pesos().values()))
        self.assertAlmostEqual(sum(agente.pesos().values()), 1)
        agente.reiniciar()
        for gesto in ['piedra', 'papel', 'piedra', 'papel', 'piedra']:
            agente.observar(gesto)
        self.assertEqual(max(agente.pesos(), key=agente.pesos().get), 'tijera')

    def test_solo_aprende_de_muestras_confirmadas_y_reinicia_por_partida(self):
        juego = EstadoJuego()
        juego.iniciar()
        for numero in range(3):
            juego.preparar_ronda()
            seleccion = juego._jugada_neo
            token = juego.abrir_captura()
            self.assertIsNone(juego.registrar('papel', 'TOKEN_VIEJO'))
            self.assertEqual(len(juego.agente.historial), numero)
            if numero == 0:
                juego.pausar()
                juego.preparar_ronda()
                self.assertEqual(juego._jugada_neo, seleccion)
                token = juego.abrir_captura()
            resultado = juego.registrar('papel', token)
            self.assertEqual(resultado['neo'], seleccion)
            self.assertEqual(len(juego.agente.historial), numero + 1)
        juego.iniciar()
        self.assertEqual(juego.agente.historial, [])


class PruebasCierre(unittest.TestCase):
    def robot_con_motores_falsos(self):
        robot = Robot.__new__(Robot)
        robot.simular, robot.movimientos = False, True
        robot.mano, robot.brazo, robot.postura_inicial = Mock(), Mock(), Mock()
        return robot

    def test_apreton_ofrece_mano_abierta_espera_diez_y_retorna_a_neutral(self):
        robot = self.robot_con_motores_falsos()
        orden = []
        robot.mano.side_effect = lambda abierta: orden.append(('mano', abierta))
        robot.brazo.side_effect = lambda *args: orden.append(('brazo', args))
        robot.postura_inicial.side_effect = lambda: orden.append(('neutral',))
        cancelar = Mock(is_set=Mock(return_value=False),
                        wait=Mock(side_effect=lambda t: orden.append(('espera', t))))
        robot.ofrecer_mano(cancelar)
        self.assertEqual(orden, [('mano', True), ('brazo', (0.0, 0.1, .8)),
                                 ('espera', 10.0), ('neutral',)])

    def test_apreton_restaura_postura_si_se_interrumpe_la_espera(self):
        robot = self.robot_con_motores_falsos()
        cancelar = Mock(is_set=Mock(return_value=False), wait=Mock(side_effect=RuntimeError('FALLO_SINTETICO')))
        with self.assertRaises(RuntimeError):
            robot.ofrecer_mano(cancelar)
        robot.postura_inicial.assert_called_once()

    def test_pausa_previa_devuelve_postura_sin_ofrecer_ni_mantener_la_mano(self):
        robot = self.robot_con_motores_falsos()
        cancelar = Mock(is_set=Mock(return_value=True))
        robot.ofrecer_mano(cancelar)
        robot.mano.assert_not_called()
        cancelar.wait.assert_not_called()
        robot.postura_inicial.assert_called_once()

    def test_sin_movimientos_no_envia_motores_ni_espera_diez_segundos(self):
        for simular, movimientos in ((True, True), (False, False)):
            robot = self.robot_con_motores_falsos()
            robot.simular, robot.movimientos = simular, movimientos
            cancelar = Mock()
            robot.ofrecer_mano(cancelar)
            robot.celebrar()
            robot.mano.assert_not_called()
            robot.brazo.assert_not_called()
            cancelar.wait.assert_not_called()

    def test_victoria_depende_del_marcador_final_y_anuncia_el_estribillo(self):
        robot = Mock()
        sesion = Sesion(Mock(), robot)
        sesion.estado.marcador = {'neo': 2, 'jugador': 1}
        sesion.estado.ultima_ronda = {'ganador': 'jugador'}
        sesion.cerrar_partida()
        robot.cantar.assert_called_once_with(JINGLE_VICTORIA)
        robot.celebrar.assert_called_once()
        robot.ofrecer_mano.assert_not_called()

    def test_derrota_ofrece_mano_incluso_si_falla_la_invitacion_de_voz(self):
        robot = Mock(decir=Mock(side_effect=ErrorPuenteVoz('NUBE_FALSA')))
        sesion = Sesion(Mock(), robot)
        sesion.estado.marcador = {'neo': 0, 'jugador': 1}
        with self.assertRaises(ErrorPuenteVoz):
            sesion.cerrar_partida()
        robot.decir.assert_called_once_with(INVITACION_APRETON)
        robot.ofrecer_mano.assert_called_once_with(sesion.pause_requested)
        robot.cantar.assert_not_called()
        mensajes = [json.loads(c.args[0]) for c in sesion.conn.sendall.call_args_list]
        self.assertFalse(mensajes[-1]['active'])

    def test_empate_final_no_canta_victoria_ni_pide_apreton_por_derrota(self):
        robot = Mock()
        sesion = Sesion(Mock(), robot)
        sesion.cerrar_partida()
        robot.cantar.assert_not_called()
        robot.ofrecer_mano.assert_not_called()
        self.assertIn('Empate final', robot.decir.call_args.args[0])


class PruebasNombreYCanto(unittest.TestCase):
    def test_nombre_y_variantes_foneticas_activan_comandos_sin_ia(self):
        conexion, conversador = Mock(), Mock()
        nombres = ('Naoqi', 'Naoki', 'Naoqui', 'Nao ki', 'Nao qi', 'Nao qui')
        for nombre in nombres:
            texto = nombre + ', siguiente'
            self.assertTrue(procesar_texto(texto, conexion, conversador, requiere_nombre=True))
        self.assertEqual(conexion.comando.call_count, len(nombres))
        conversador.pedir.assert_not_called()
        self.assertIn('Soy Naoqi', SALUDO)
        self.assertNotIn('generada', SALUDO)
        self.assertEqual(normalizar_lectura('Gano Naoqi'), normalizar_lectura('Gano Naoki'))

    def test_canto_y_habla_tienen_instrucciones_y_cache_separadas(self):
        sockets = [WebSocketFalso(JINGLE_VICTORIA), WebSocketFalso(JINGLE_VICTORIA)]
        conectar = Mock(side_effect=sockets)
        lector = LectorOpenAI('CLAVE_FALSA', conectar=conectar)
        self.assertEqual(lector.sintetizar(JINGLE_VICTORIA), PCM)
        self.assertEqual(lector.sintetizar(JINGLE_VICTORIA, estilo='cantado'), PCM)
        self.assertEqual(lector.sintetizar(JINGLE_VICTORIA, estilo='cantado'), PCM)
        self.assertEqual(conectar.call_count, 2)
        self.assertNotEqual(sockets[0].enviados[0]['session']['instructions'],
                            sockets[1].enviados[0]['session']['instructions'])
        self.assertIn('original victory jingle', sockets[1].enviados[0]['session']['instructions'])
        with self.assertRaises(ErrorVoz):
            lector.sintetizar(JINGLE_VICTORIA, estilo='COMANDO_NO_PERMITIDO')
        self.assertEqual(conectar.call_count, 2)

    def test_http_transporta_el_estilo_hasta_el_lector_sin_cambiar_el_pcm(self):
        lector = Mock(sintetizar=Mock(return_value=PCM))
        servicio = ServicioVoz(lector, puerto=0)
        try:
            salida = Mock()
            ClienteVoz(servicio.puerto, servicio.token, salida).cantar(JINGLE_VICTORIA)
            lector.sintetizar.assert_called_once_with(JINGLE_VICTORIA, estilo='cantado')
            salida.reproducir.assert_called_once_with(PCM)
            lector.sintetizar.reset_mock()
            with self.assertRaises(ErrorPuenteVoz):
                ClienteVoz(servicio.puerto, servicio.token, salida).cantar(['TEXTO_NO_VALIDO'])
            lector.sintetizar.assert_not_called()
        finally:
            servicio.cerrar()

    def test_cierre_no_preparado_no_impide_jugar_ni_repite_la_consulta_de_pago(self):
        def sintetizar(texto, estilo='hablado'):
            if estilo == 'cantado':
                raise ErrorVoz('FALLO_CANTO_SIMULADO')
            return PCM
        lector = Mock(sintetizar=Mock(side_effect=sintetizar))
        servicio = ServicioVoz(lector, puerto=0)
        try:
            servicio.preparar_cuenta(reintentos=0)
            self.assertEqual(lector.sintetizar.call_count, 7)
            with self.assertRaises(ErrorPuenteVoz):
                ClienteVoz(servicio.puerto, servicio.token, Mock()).cantar(JINGLE_VICTORIA)
            self.assertEqual(lector.sintetizar.call_count, 7)
        finally:
            servicio.cerrar()


if __name__ == '__main__':
    unittest.main()
