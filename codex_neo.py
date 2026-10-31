"""Adaptador oficial Codex CLI: login ChatGPT y salida JSON para el prototipo."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path


class ErrorCodex(Exception):
    pass


def localizar_codex():
    ruta = os.environ.get('NEO_CODEX_EXE') or shutil.which('codex')
    if not ruta and os.name == 'nt':
        npm = Path(os.environ.get('APPDATA', '')) / 'npm' / 'codex.cmd'
        if npm.is_file():
            ruta = str(npm)
    if not ruta or not Path(ruta).is_file():
        raise ErrorCodex('Falta Codex CLI en esta laptop. Instala la CLI oficial y ejecuta codex login.')
    archivo = Path(ruta)
    if archivo.suffix.lower() in ('.cmd', '.bat', '.ps1', '.js'):
        # Evita pasar el prompt por cmd.exe/PowerShell y sus reglas de escape.
        js = archivo if archivo.suffix.lower() == '.js' else (
            archivo.parent / 'node_modules' / '@openai' / 'codex' / 'bin' / 'codex.js')
        candidatos_node = [shutil.which('node'), str(archivo.parent / 'node.exe')]
        if os.name == 'nt':
            pf = Path(os.environ.get('ProgramFiles', 'C:/Program Files'))
            candidatos_node += [str(pf / 'nodejs' / 'node.exe'),
                                str(pf / 'Huawei' / 'DevEco Studio' / 'tools' / 'node' / 'node.exe')]
        node = next((p for p in candidatos_node if p and Path(p).is_file()), None)
        if not js.is_file() or not node:
            raise ErrorCodex('No se encontro Node y el ejecutable de Codex. Revisa la instalacion oficial de la CLI.')
        return [node, str(js)]
    return [str(archivo)]


def entorno_sin_claves_api():
    entorno = dict(os.environ)
    for key in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_ADMIN_KEY'):
        entorno.pop(key, None)
    return entorno


def detener_proceso(proceso):
    if proceso.poll() is not None:
        return
    if os.name == 'nt':
        try:
            subprocess.run(['taskkill', '/PID', str(proceso.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            proceso.kill()
    else:
        try:
            os.killpg(proceso.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            proceso.kill()


class CodexLocal:
    def __init__(self, modelo=None, timeout=45, comando=None):
        self.comando = comando or localizar_codex()
        self.modelo = modelo or os.environ.get('NEO_CODEX_MODEL', '').strip() or None
        self.timeout = timeout

    def _ejecutar(self, args, prompt=None, cwd=None, timeout=None):
        kwargs = {'stdin': subprocess.PIPE, 'stdout': subprocess.PIPE, 'stderr': subprocess.PIPE,
                  'encoding': 'utf-8', 'errors': 'replace', 'env': entorno_sin_claves_api(),
                  'cwd': cwd, 'shell': False}
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs['start_new_session'] = True
        try:
            proceso = subprocess.Popen(self.comando + args, **kwargs)
            try:
                salida, errores = proceso.communicate(prompt, timeout=timeout or self.timeout)
            except subprocess.TimeoutExpired:
                detener_proceso(proceso)
                proceso.communicate(timeout=5)
                raise ErrorCodex('Codex excedio el tiempo de espera. El juego sigue disponible; no se reintenta automaticamente.')
        except (OSError, subprocess.SubprocessError):
            raise ErrorCodex('No se pudo ejecutar Codex CLI. Revisa codex --version en esta terminal.')
        if proceso.returncode != 0:
            mensaje = (salida + '\n' + errores).lower()
            if any(x in mensaje for x in ('limit', 'quota', 'credits', 'rate_limit')):
                raise ErrorCodex('Codex informo un limite de uso. Revisa /status y espera su restablecimiento.')
            if any(x in mensaje for x in ('login', 'logged in', 'authentication', 'unauthorized')):
                raise ErrorCodex('Codex no tiene una sesion ChatGPT disponible. Ejecuta codex login.')
            raise ErrorCodex('Codex no completo la consulta. Comprueba su instalacion, inicio de sesion y sandbox ejecutandolo directamente.')
        return salida, errores

    def verificar_sesion(self):
        salida, errores = self._ejecutar(['login', 'status'], timeout=8)
        if 'chatgpt' not in (salida + '\n' + errores).lower():
            raise ErrorCodex('Codex no indica inicio de sesion con ChatGPT. Ejecuta codex login y elige tu cuenta ChatGPT.')

    def responder(self, instrucciones, entrada, schema):
        self.verificar_sesion()
        prompt = (instrucciones + '\n\n'
                  'Esta es una prueba local de interaccion con un robot. No leas archivos, '
                  'no uses herramientas, no ejecutes comandos y no modifiques el proyecto. '
                  'Responde solo el objeto JSON solicitado; Python aplicara la accion si es valida.\n'
                  + json.dumps(entrada, ensure_ascii=False))
        with tempfile.TemporaryDirectory(prefix='neo_codex_') as temporal:
            schema_path = Path(temporal) / 'respuesta.schema.json'
            output_path = Path(temporal) / 'respuesta.json'
            schema_path.write_text(json.dumps(schema), encoding='utf-8')
            args = ['--ask-for-approval', 'never',
                    '-c', 'forced_login_method="chatgpt"',
                    '-c', 'model_reasoning_effort="low"',
                    'exec', '--ignore-user-config', '--sandbox', 'read-only',
                    '--skip-git-repo-check', '--ephemeral',
                    '--output-schema', str(schema_path), '--output-last-message', str(output_path)]
            if self.modelo:
                args.extend(['--model', self.modelo])
            args.append('-')  # El texto del jugador viaja por stdin, no como codigo de shell.
            self._ejecutar(args, prompt=prompt, cwd=temporal)
            if not output_path.is_file() or output_path.stat().st_size > 16384:
                raise ErrorCodex('Codex no genero el JSON final esperado.')
            try:
                return json.loads(output_path.read_text(encoding='utf-8-sig'))
            except (ValueError, UnicodeError):
                raise ErrorCodex('Codex devolvio una respuesta que no pudimos validar.')
