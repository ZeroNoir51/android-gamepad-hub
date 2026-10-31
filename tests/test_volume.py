"""Volumen del PC: comandos fijos, lectura del porcentaje y límite de frecuencia."""
import asyncio

from server import volume as V


def run(coro):
    return asyncio.run(coro)


def fake(tool, outputs, calls):
    vol = V.Volume(which=lambda name: f'/usr/bin/{name}' if name == tool else None)

    async def _run(cmd):
        calls.append(cmd)
        return outputs.pop(0)
    vol._run = _run
    return vol


def test_wpctl_sube_y_lee_el_porcentaje():
    calls = []
    vol = fake('wpctl', ['', 'Volume: 0.45\n'], calls)
    assert run(vol.change(1, now=10.0)) == {'t': 'vol', 'v': 45}
    assert calls == [['wpctl', 'set-volume', '-l', '1.0', '@DEFAULT_AUDIO_SINK@', '5%+'],
                     ['wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@']]


def test_pactl_si_no_hay_wpctl():
    calls = []
    vol = fake('pactl', ['', 'Volume: front-left: 26214 /  40% / -23.88 dB\n'], calls)
    assert run(vol.change(-1, now=10.0)) == {'t': 'vol', 'v': 40}
    assert calls[0] == ['pactl', 'set-sink-volume', '@DEFAULT_SINK@', '-5%']


def test_demasiado_rapido_se_ignora_y_sin_herramienta_avisa():
    calls = []
    vol = fake('wpctl', ['', 'Volume: 0.50', '', 'Volume: 0.55'], calls)
    run(vol.change(1, now=10.0))
    assert run(vol.change(1, now=10.01)) is None and len(calls) == 2
    none = V.Volume(which=lambda name: None)
    assert run(none.change(1, now=1.0)) == {'t': 'vol', 'err': 'no hay wpctl ni pactl en el PC'}


def test_error_del_comando_va_al_cliente():
    vol = V.Volume(which=lambda name: '/usr/bin/wpctl' if name == 'wpctl' else None)

    async def _run(cmd):
        raise RuntimeError('wpctl: sin servidor de audio')
    vol._run = _run
    assert run(vol.change(1, now=5.0)) == {'t': 'vol', 'err': 'wpctl: sin servidor de audio'}
