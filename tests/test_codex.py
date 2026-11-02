"""Ejecuta una CLI FALSA local: no llama a Codex ni consume limites del plan."""
import json
import os
import shutil
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_neo import CodexLocal, ErrorCodex, entorno_sin_claves_api
from cliente_neo import Conversador
from estado_juego import EstadoJuego
from ia_neo import CerebroNeo, HERRAMIENTA, INSTRUCCIONES, ErrorIA


CLI_FALSA = '''import json, os, sys, time
from pathlib import Path
if sys.argv[1:] == ['login', 'status']:
    tipo = os.environ.get('NEO_FAKE_AUTH', 'ChatGPT')
    print('Logged in using ' + tipo, file=sys.stderr)
    sys.exit(0)
assert 'OPENAI_API_KEY' not in os.environ
assert 'CODEX_API_KEY' not in os.environ
assert '--ignore-user-config' in sys.argv
assert '--sandbox' in sys.argv
assert sys.argv[sys.argv.index('--sandbox') + 1] == 'read-only'
assert '--ephemeral' in sys.argv
assert '--dangerously-bypass-approvals-and-sandbox' not in sys.argv
prompt = sys.stdin.read()
assert 'No leas archivos' in prompt
if os.environ.get('NEO_FAKE_SLEEP'):
    if os.environ.get('NEO_FAKE_MARKER'):
        Path(os.environ['NEO_FAKE_MARKER']).write_text(str(os.getpid()))
    time.sleep(2)
schema = json.loads(Path(sys.argv[sys.argv.index('--output-schema') + 1]).read_text())
assert schema['additionalProperties'] is False
assert set(schema['required']) == {'accion', 'texto'}
out = Path(sys.argv[sys.argv.index('--output-last-message') + 1])
if os.environ.get('NEO_FAKE_BAD_JSON'):
    out.write_text('no es JSON')
else:
    out.write_text(json.dumps({'accion': 'hablar', 'texto': 'Respuesta de una CLI simulada.'}))
'''


class PruebasCodex(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.archivo = Path(self.temporal.name) / 'codex_falso.py'
        self.archivo.write_text(CLI_FALSA, encoding='utf-8')
        self.comando = [sys.executable, str(self.archivo)]

    def test_codex_sin_clave_api_y_salida_validada(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'NO_DEBE_SALIR', 'CODEX_API_KEY': 'TAMPOCO'}):
            cliente = CodexLocal(comando=self.comando)
            data = cliente.responder(INSTRUCCIONES,
                [{'role': 'user', 'content': 'Hola; $(comando) & otro comando'}], HERRAMIENTA['parameters'])
        self.assertEqual(data, {'accion': 'hablar', 'texto': 'Respuesta de una CLI simulada.'})

    def test_rechaza_login_api_en_modalidad_chatgpt(self):
        with patch.dict(os.environ, {'NEO_FAKE_AUTH': 'API key'}):
            with self.assertRaises(ErrorCodex):
                CodexLocal(comando=self.comando).verificar_sesion()

    def test_json_mal_formado_no_se_ejecuta(self):
        with patch.dict(os.environ, {'NEO_FAKE_BAD_JSON': '1'}):
            with self.assertRaises(ErrorCodex):
                CodexLocal(comando=self.comando).responder(INSTRUCCIONES, [], HERRAMIENTA['parameters'])

    def test_fabrica_codex_funciona_sin_clave(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': '', 'NEO_IA_PROVIDER': 'codex'}):
            with patch('codex_neo.localizar_codex', return_value=self.comando):
                cerebro = CerebroNeo()
                resultado = cerebro.responder(EstadoJuego().snapshot(), 'Hola')
        self.assertEqual(cerebro.provider, 'codex')
        self.assertEqual(resultado['accion'], 'hablar')
        self.assertGreaterEqual(resultado['latencia_ms'], 0)

    def test_no_fallback_automatico_a_api_si_codex_falla(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'NO_AUTORIZA_UN_FALLBACK', 'NEO_IA_PROVIDER': 'codex'}):
            with patch('codex_neo.localizar_codex', side_effect=ErrorCodex('Falta CLI')):
                with patch('urllib.request.urlopen') as http:
                    with self.assertRaises(ErrorIA):
                        CerebroNeo()
                    http.assert_not_called()

    def test_entorno_no_envia_claves_y_no_muta_proceso_padre(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'SENTINELA', 'CODEX_API_KEY': 'OTRA'}):
            child = entorno_sin_claves_api()
            self.assertNotIn('OPENAI_API_KEY', child)
            self.assertNotIn('CODEX_API_KEY', child)
            self.assertEqual(os.environ['OPENAI_API_KEY'], 'SENTINELA')

    def test_timeout_termina_la_cli_falsa(self):
        with patch.dict(os.environ, {'NEO_FAKE_SLEEP': '1'}):
            with self.assertRaisesRegex(ErrorCodex, 'tiempo de espera'):
                CodexLocal(comando=self.comando, timeout=0.1).responder(
                    INSTRUCCIONES, [], HERRAMIENTA['parameters'])

    def test_cierre_del_conversador_espera_el_hilo_y_detiene_sus_procesos(self):
        marcador = Path(self.temporal.name) / 'proceso_iniciado'
        procesos = []
        popen_real = __import__('subprocess').Popen
        def ejecutar(*args, **kwargs):
            proceso = popen_real(*args, **kwargs)
            procesos.append(proceso)
            return proceso
        conexion = SimpleNamespace(closed=threading.Event(), snapshot=lambda: EstadoJuego().snapshot(),
                                   enviar=Mock(return_value=True))
        with patch.dict(os.environ, {'NEO_FAKE_SLEEP': '1', 'NEO_FAKE_MARKER': str(marcador)}):
            with patch('codex_neo.localizar_codex', return_value=self.comando), \
                 patch('codex_neo.subprocess.Popen', side_effect=ejecutar):
                cerebro = CerebroNeo(provider='codex')
                conversador = Conversador(conexion, cerebro, comentarios=False)
                try:
                    conversador.pedir('Hola')
                    fin = time.monotonic() + 3
                    while not marcador.exists() and time.monotonic() < fin:
                        time.sleep(.01)
                    self.assertTrue(marcador.exists())
                    conversador.cerrar()
                    self.assertFalse(conversador.hilo.is_alive())
                    self.assertTrue(all(p.poll() is not None for p in procesos))
                    conexion.enviar.assert_not_called()
                finally:
                    conversador.cerrar()

    def test_bloqueo_de_carpeta_tipo_windows_no_oculta_una_respuesta_valida(self):
        rmdir_real, unlink_real = os.rmdir, os.unlink
        carpetas = set()
        def bloquear(funcion, ruta, *args, **kwargs):
            if Path(ruta).name.startswith('neo_codex_'):
                carpetas.add(str(ruta))
                error = PermissionError('WINERROR_32_SIMULADO')
                error.winerror = 32
                raise error
            return funcion(ruta, *args, **kwargs)
        try:
            with patch('tempfile._os.rmdir', side_effect=lambda p, *a, **k: bloquear(rmdir_real, p, *a, **k)), \
                 patch('tempfile._os.unlink', side_effect=lambda p, *a, **k: bloquear(unlink_real, p, *a, **k)):
                respuesta = CodexLocal(comando=self.comando).responder(
                    INSTRUCCIONES, [], HERRAMIENTA['parameters'])
            self.assertEqual(respuesta['accion'], 'hablar')
            self.assertTrue(carpetas)
        finally:
            for carpeta in carpetas:
                shutil.rmtree(carpeta, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
