"""UInputPad sin evdev: secuencia de ioctl y eventos escritos (sin /dev/uinput real).

Los números de ioctl y los tamaños se comprobaron contra linux/uinput.h:
UI_DEV_SETUP 0x405c5503, UI_ABS_SETUP 0x401c5504, UI_SET_EVBIT 0x40045564,
UI_SET_KEYBIT 0x40045565, UI_SET_ABSBIT 0x40045567; uinput_setup 92 bytes,
uinput_abs_setup 28, input_event 24 (x86_64).
"""
import struct

import pytest

from server import pad, protocol


@pytest.fixture
def dev(monkeypatch):
    calls, writes = [], []
    monkeypatch.setattr(pad.os, 'open', lambda path, flags: 99)
    monkeypatch.setattr(pad.os, 'close', lambda fd: calls.append(('close', fd)))
    monkeypatch.setattr(pad.os, 'write', lambda fd, data: writes.append(data) or len(data))
    monkeypatch.setattr(pad.fcntl, 'ioctl', lambda fd, req, arg=0: calls.append((req, arg)))
    p = pad.UInputPad()
    return p, calls, writes


def events(data):
    return [pad.EVENT.unpack_from(data, i)[2:] for i in range(0, len(data), pad.EVENT.size)]


def test_constantes_del_kernel():
    assert (pad.UI_DEV_SETUP, pad.UI_ABS_SETUP) == (0x405C5503, 0x401C5504)
    assert (pad.UI_SET_EVBIT, pad.UI_SET_KEYBIT, pad.UI_SET_ABSBIT) == (0x40045564, 0x40045565, 0x40045567)
    assert pad.EVENT.size == 24


def test_creacion(dev):
    _, calls, _ = dev
    reqs = [c[0] for c in calls]
    assert reqs[-1] == pad.UI_DEV_CREATE and reqs[-2] == pad.UI_DEV_SETUP
    keys = sorted(arg for req, arg in calls if req == pad.UI_SET_KEYBIT)
    assert keys == sorted(pad.BTN.values())
    setup = calls[-2][1]
    assert len(setup) == 92
    bus, vendor, product, version, name, ff = struct.unpack('<4H80sI', setup)
    assert (bus, vendor, product, version) == (3, 0x045E, 0x028E, 0x0114)
    assert name.rstrip(b'\0') == b'GamePad Virtual Xbox 360'
    absinfo = {struct.unpack('<H2x6i', arg)[0]: struct.unpack('<H2x6i', arg)[1:]
               for req, arg in calls if req == pad.UI_ABS_SETUP}
    assert absinfo[0x00] == (0, -32768, 32767, 16, 128, 0)      # ABS_X
    assert absinfo[0x05] == (0, 0, 255, 0, 0, 0)                # ABS_RZ (RT)
    assert absinfo[0x11] == (0, -1, 1, 0, 0, 0)                 # ABS_HAT0Y


def test_eventos_y_sincronizacion(dev):
    p, _, writes = dev
    state = protocol.neutral() | {'a': 1, 'lx': -32768, 'rt': 255, 'dy': -1}
    p.apply(state)
    assert sorted(events(writes[-1])[:-1]) == sorted(
        [(1, 0x130, 1), (3, 0x00, -32768), (3, 0x05, 255), (3, 0x11, -1)])
    assert events(writes[-1])[-1] == (0, 0, 0)                  # SYN_REPORT al final
    p.apply(state)
    assert len(writes) == 1                                     # sin cambios no escribe
    p.reset()
    assert sorted(events(writes[-1])[:-1]) == sorted(
        [(1, 0x130, 0), (3, 0x00, 0), (3, 0x05, 0), (3, 0x11, 0)])


def test_cierre(dev):
    p, calls, _ = dev
    p.close()
    assert calls[-2:] == [(pad.UI_DEV_DESTROY, 0), ('close', 99)]
    p.close()                                                   # idempotente


def test_sin_permiso_sigue_y_reintenta(monkeypatch, capsys):
    calls = {'n': 0}
    real_open = lambda path, flags: 99

    def denied(path, flags):
        calls['n'] += 1
        raise PermissionError(13, 'Permission denied', path)
    monkeypatch.setattr(pad.os, 'open', denied)
    monkeypatch.setattr(pad.fcntl, 'ioctl', lambda fd, req, arg=0: None)
    monkeypatch.setattr(pad.os, 'write', lambda fd, data: len(data))
    p = pad.create_pad('auto')
    assert isinstance(p, pad.RetryPad) and p.name == 'sin mando virtual'
    assert 'sin permiso para /dev/uinput' in p.error
    assert 'reintenta cada 10 s' in capsys.readouterr().out
    p.apply(protocol.neutral() | {'a': 1})                 # sin mando: se guarda el estado
    assert not p.retry(now=0)                               # aún no toca
    assert not p.retry(now=1e9) and p.inner is None         # sigue sin permiso
    monkeypatch.setattr(pad.os, 'open', real_open)          # el permiso aparece (p. ej. regla udev)
    assert not p.retry(now=1e9 + 1)                         # respeta el intervalo
    assert p.retry(now=1e9 + 20)
    assert p.error is None and p.name == 'GamePad Virtual Xbox 360'
    assert p.inner.state['a'] == 1                          # recupera lo que se estaba pulsando
    with pytest.raises(PermissionError):
        monkeypatch.setattr(pad.os, 'open', denied)
        pad.create_pad('uinput')                            # obligatorio: falla


def test_sin_modulo_uinput(monkeypatch):
    def missing(path, flags):
        raise FileNotFoundError(2, 'No such file', path)
    monkeypatch.setattr(pad.os, 'open', missing)
    assert 'modprobe uinput' in pad.create_pad('auto').error
    assert isinstance(pad.create_pad('null'), pad.NullPad)
