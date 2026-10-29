"""Código fijo, `gamepad code/status` y notificación (sin red ni escritorio reales)."""
import json
import os
import stat

from server import auth, status


def test_codigo_fijo(tmp_path):
    path = tmp_path / 'code'
    code = auth.load_or_create_code(path)
    assert len(code) == 4 and code.isalpha() and code.isupper()
    assert auth.load_or_create_code(path) == code                 # no cambia entre reinicios
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    path.write_text('roto!\n')
    assert auth.load_or_create_code(path) != 'ROTO'               # inválido: se regenera


def test_code_new_cierra_sesiones(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path))
    sessions = tmp_path / 'gamepad' / 'sessions.json'
    sessions.parent.mkdir()
    sessions.write_text('{}')
    assert status.main(['code', '--new']) == 0
    assert not sessions.exists()
    new = capsys.readouterr().out.split('Código nuevo: ')[1][:4]
    assert auth.load_or_create_code(tmp_path / 'gamepad' / 'code') == new


def test_status_json(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path))
    monkeypatch.setattr(status, 'service_up', lambda port=8888: False)
    monkeypatch.setattr(status, 'lan_ip', lambda: '192.168.1.50')
    assert status.main(['status', '--json']) == 1
    info = json.loads(capsys.readouterr().out)
    assert info['up'] is False and info['url'] == 'http://192.168.1.50:8888' and len(info['code']) == 4


def test_notify_sin_escritorio_no_falla(monkeypatch):
    monkeypatch.setattr(status.shutil, 'which', lambda name: None)
    assert status.notify('t', 'b') is False


def test_notify_usa_notify_send(monkeypatch):
    calls = []
    monkeypatch.setattr(status.shutil, 'which', lambda name: '/usr/bin/' + name)
    monkeypatch.setattr(status.subprocess, 'Popen', lambda cmd, **kw: calls.append(cmd))
    assert status.notify('GamePad listo', 'Código: ABCD')
    assert calls[0][0] == 'notify-send' and calls[0][-2:] == ['GamePad listo', 'Código: ABCD']
