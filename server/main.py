"""`gamepad serve`: servicio permanente sin root.

WebSocket LAN -> mando virtual + telemetría. Los datos de juego llegan del
lanzador (`gamepad run`) por un socket Unix privado; este proceso no puede
leer la memoria de ningún juego.
"""
import argparse
import asyncio
import json
import os
import platform
import string
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web, WSMsgType

from . import VERSION, auth, paths, portraits, protocol, status
from .auth import COOKIE, SESSION_TTL, AuthGuard, SessionStore
from .pad import create_pad
from .telemetry import MangoHudTail, SystemTelemetry

ROOT = Path(__file__).resolve().parent.parent
GAME_TYPES = {'game', 'gv'}
NO_GAME = {'t': 'game', 'state': 'none', 'plugins': []}

INPUT_TIMEOUT = 0.5   # s sin mensajes de entrada => se sueltan todos los controles


class Hub:
    def __init__(self, pad):
        self.pad = pad
        self.ws = None
        self.last_input = 0.0

    async def send(self, msg):
        ws = self.ws
        if ws is None or ws.closed:
            return
        try:
            await ws.send_str(json.dumps(msg, separators=(',', ':')))
        except (ConnectionResetError, RuntimeError):
            pass


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog='gamepad serve', description='GamePad Hub')
    p.add_argument('--host', default='0.0.0.0')
    p.add_argument('--port', type=int, default=status.PORT)
    p.add_argument('--token', help='4 letras A-Z (si no, el código guardado; ver `gamepad code`)')
    p.add_argument('--pad', choices=('auto', 'uinput', 'null'), default='auto',
                   help='auto: si no hay /dev/uinput, sigue sin mando y lo reintenta; '
                        'uinput: obligatorio (falla sin él); null: sin mando virtual (pruebas)')
    p.add_argument('--telemetry-hz', type=float, default=4.0)
    p.add_argument('--mangohud-dir', default=None,
                   help='carpeta de logs de MangoHud (por defecto la misma que usa `gamepad run`)')
    p.add_argument('--sessions-file', default=None)
    args = p.parse_args(argv)
    if args.token is not None:
        args.token = args.token.upper()
        if len(args.token) != 4 or not all(c in string.ascii_uppercase for c in args.token):
            p.error('--token debe tener exactamente 4 letras A-Z')
    return args


def main(argv=None):
    args = parse_args(argv)
    if os.geteuid() == 0:
        print('AVISO: no hace falta root. Ejecuta `gamepad serve` con tu usuario (ver README).', flush=True)
    token = args.token or auth.load_or_create_code(paths.code_file())
    mangohud_dir = args.mangohud_dir or str(paths.mangohud_dir())
    sessions_file = args.sessions_file or str(paths.sessions_file())

    pad = create_pad(args.pad)
    hub = Hub(pad)
    guard = AuthGuard(token)
    sessions = SessionStore(sessions_file)
    sysmon = SystemTelemetry()
    mango = MangoHudTail(mangohud_dir)
    game = {'meta': NO_GAME, 'writer': None}
    print(f'[telemetry] fuentes: {sysmon.sources()}', flush=True)
    print(f'[mangohud] leyendo logs de {mangohud_dir}', flush=True)

    def same_origin(request):
        origin = request.headers.get('Origin')
        return origin is None or urlsplit(origin).netloc == request.host

    def authorized(request):
        return sessions.valid(request.cookies.get(COOKIE))

    # --- HTTP ---
    async def index(request):
        return web.FileResponse(ROOT / 'web' / 'index.html', headers={'Cache-Control': 'no-store'})

    def media(kind):
        async def handler(request):
            if not authorized(request):
                raise web.HTTPForbidden(text='Sin sesión')
            path = portraits.resolve(request.match_info['plugin'], request.match_info['name'], kind=kind)
            if path is None:
                raise web.HTTPNotFound()
            return web.FileResponse(path, headers={
                'Content-Type': portraits.content_type(path),
                'X-Content-Type-Options': 'nosniff',
                'Cache-Control': 'private, max-age=3600'})
        return handler

    async def api_media(request):
        if not authorized(request):
            raise web.HTTPForbidden(text='Sin sesión')
        return web.json_response({'backgrounds': portraits.listing(request.match_info['plugin'], 'backgrounds')},
                                 headers={'Cache-Control': 'no-store'})

    async def api_session(request):
        return web.json_response({'ok': authorized(request)})

    async def api_login(request):
        if not same_origin(request):
            raise web.HTTPForbidden(text='Origen no permitido')
        ip = request.remote or '?'
        try:
            given = str((await request.json()).get('token', ''))
        except (ValueError, AttributeError):
            given = ''
        verdict = guard.check(ip, given)
        if verdict == 'blocked':
            print(f'[auth] {ip}: bloqueado temporalmente por demasiados intentos', flush=True)
            return web.json_response({'ok': False, 'msg': 'Demasiados intentos. Espera un minuto.'}, status=429)
        if verdict == 'bad':
            print(f'[auth] {ip}: token incorrecto', flush=True)
            return web.json_response({'ok': False, 'msg': 'Código incorrecto.'}, status=403)
        resp = web.json_response({'ok': True})
        resp.set_cookie(COOKIE, sessions.create(), max_age=SESSION_TTL, httponly=True,
                        samesite='Strict', path='/')
        print(f'[auth] {ip}: sesión iniciada (24 h)', flush=True)
        return resp

    async def api_logout(request):
        sessions.revoke(request.cookies.get(COOKIE))
        resp = web.json_response({'ok': True})
        resp.del_cookie(COOKIE, path='/')
        return resp

    # --- WebSocket ---
    async def handle_text(ws, raw):
        try:
            data = json.loads(raw)
        except ValueError:
            await ws.send_json({'t': 'err', 'msg': 'JSON inválido'})
            return
        if not isinstance(data, dict):
            await ws.send_json({'t': 'err', 'msg': 'se esperaba un objeto'})
            return
        kind = data.get('t')
        if kind == 'in' or kind is None:          # None: cliente v0.2 (estado sin sobre)
            try:
                state = protocol.parse_input(data.get('s') if kind else data)
            except ValueError as ex:
                await ws.send_json({'t': 'err', 'msg': str(ex)})
                return
            pad.apply(state)
            hub.last_input = time.monotonic()
        elif kind == 'ping':
            await ws.send_json({'t': 'pong', 'id': data.get('id'), 'ct': data.get('ct')})
        else:
            await ws.send_json({'t': 'err', 'msg': f'tipo de mensaje desconocido: {kind!r}'})

    async def ws_handler(request):
        ip = request.remote or '?'
        if not same_origin(request):
            raise web.HTTPForbidden(text='Origen no permitido')
        if not authorized(request):
            # compatibilidad con el cliente v0.2: ?token=XXXX (solo cuenta como intento si viene)
            given = request.query.get('token')
            if given is None or guard.check(ip, given) != 'ok':
                raise web.HTTPForbidden(text='Sin sesión')
        if hub.ws is not None:
            print(f'[ws] {ip}: rechazado, ya hay un cliente conectado', flush=True)
            raise web.HTTPConflict(text='Solo se permite un cliente activo')

        ws = web.WebSocketResponse(heartbeat=5, max_msg_size=8192)
        await ws.prepare(request)
        hub.ws = ws
        hub.last_input = time.monotonic()
        print(f'[ws] {ip}: cliente conectado', flush=True)
        await hub.send({'t': 'hello', 'v': VERSION, 'host': platform.node(), 'pad': pad.name, 'padErr': pad.error})
        await hub.send(game['meta'])
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await handle_text(ws, msg.data)
                elif msg.type == WSMsgType.ERROR:
                    break
        finally:
            pad.reset()
            hub.ws = None
            print(f'[ws] {ip}: desconectado; controles liberados', flush=True)
        return ws

    # --- bucles ---
    async def pad_retry():
        """Sin /dev/uinput al arrancar: reintenta y avisa a Android cuando el mando ya existe."""
        while hasattr(pad, 'retry'):
            await asyncio.sleep(2)
            if pad.retry():
                print(f'[pad] mando virtual creado: {pad.name}', flush=True)
                await hub.send({'t': 'pad', 'name': pad.name, 'err': None})
                return

    async def input_watchdog():
        while True:
            await asyncio.sleep(0.1)
            if hub.ws is not None and time.monotonic() - hub.last_input > INPUT_TIMEOUT:
                pad.reset()   # no escribe nada si ya estaba neutro

    async def telemetry_loop():
        period = 1.0 / args.telemetry_hz
        while True:
            await asyncio.sleep(period)
            if hub.ws is None:
                continue
            await hub.send({'t': 'tel', **sysmon.sample(), **mango.poll()})

    async def bridge_client(reader, writer):
        """Un lanzador conectado. Solo se aceptan mensajes de datos de juego."""
        if game['writer'] is not None:
            game['writer'].close()          # el lanzador más reciente sustituye al anterior
        game['writer'] = writer
        print('[bridge] lanzador conectado', flush=True)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(msg, dict) or msg.get('t') not in GAME_TYPES:
                    continue
                if msg['t'] == 'game':
                    game['meta'] = msg
                await hub.send(msg)
        except (asyncio.LimitOverrunError, ValueError, ConnectionError):
            pass
        finally:
            if game['writer'] is writer:
                game['writer'] = None
                game['meta'] = NO_GAME
                await hub.send(NO_GAME)
                print('[bridge] lanzador desconectado', flush=True)
            writer.close()

    async def bridge_server():
        # Dos sockets: /run/user (normal) y ~/.cache (lanzadores dentro de Flatpak, como Heroic).
        servers = []
        for sock in paths.socket_paths():
            try:
                sock.unlink(missing_ok=True)
                servers.append((sock, await asyncio.start_unix_server(bridge_client, str(sock), limit=65536)))
                os.chmod(sock, 0o600)
                print(f'[bridge] escuchando en {sock}', flush=True)
            except OSError as ex:
                print(f'[bridge] no se pudo abrir {sock}: {ex}', flush=True)
        try:
            await asyncio.Event().wait()
        finally:
            for sock, server in servers:
                server.close()
                sock.unlink(missing_ok=True)

    async def lifetime(app):
        tasks = [asyncio.create_task(c()) for c in (input_watchdog, telemetry_loop, bridge_server, pad_retry)]
        status.notify(f'GamePad {VERSION} listo', f'Android: {status.url(args.port)}\nCódigo: {token}')
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            pad.close()

    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_get('/api/session', api_session)
    app.router.add_post('/api/login', api_login)
    app.router.add_post('/api/logout', api_logout)
    app.router.add_get('/ws', ws_handler)
    app.router.add_get('/portraits/{plugin}/{name}', media('portraits'))
    app.router.add_get('/backgrounds/{plugin}/{name}', media('backgrounds'))
    app.router.add_get('/api/media/{plugin}', api_media)
    app.cleanup_ctx.append(lifetime)

    print(f'GamePad Hub {VERSION} · mando: {pad.name}', flush=True)
    print(f'Abre en Android: {status.url(args.port)}', flush=True)
    print(f'Código de acceso: {token}   (la sesión dura 24 h)', flush=True)
    print('Solo red local de confianza: sin cifrado. No expongas el puerto a Internet.', flush=True)
    web.run_app(app, host=args.host, port=args.port, print=None)
