"""tools/build-plugin.sh: empaquetar (con y sin imágenes), instalar y servir."""
import os
import subprocess
import zipfile
from pathlib import Path

import pytest

from server import plugin_pkg, portraits

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (ROOT / 'plugins' / 'ffrs').is_dir(), reason='ffrs se distribuye aparte')


def build(out, data_home, *extra):
    env = dict(os.environ, XDG_DATA_HOME=str(data_home))
    r = subprocess.run(['sh', str(ROOT / 'tools' / 'build-plugin.sh'), 'ffrs', str(out), *extra],
                       env=env, capture_output=True, text=True, check=True)
    return r.stdout


def test_sin_imagenes(tmp_path, data_home):
    print(build(tmp_path, data_home))
    [z] = tmp_path.glob('gamepad-plugin-ffrs-*.zip')
    assert '-media' not in z.name
    names = zipfile.ZipFile(z).namelist()
    assert 'ffrs/plugin.json' in names and not any('/portraits/' in n or '/backgrounds/' in n for n in names)


def test_con_imagenes_e_instalacion(tmp_path, data_home):
    (data_home / 'gamepad' / 'portraits' / 'ffrs').mkdir(parents=True)
    (data_home / 'gamepad' / 'backgrounds' / 'ffrs').mkdir(parents=True)
    (data_home / 'gamepad' / 'portraits' / 'ffrs' / 'rain.png').write_bytes(b'r')
    (data_home / 'gamepad' / 'backgrounds' / 'ffrs' / 'resonance.webp').write_bytes(b'b')
    (data_home / 'gamepad' / 'backgrounds' / 'ffrs' / 'con espacio.png').write_bytes(b'x')   # nombre no válido
    out = build(tmp_path, data_home, '--media')
    assert 'portraits: 1' in out and 'backgrounds: 1' in out
    [z] = tmp_path.glob('gamepad-plugin-ffrs-*-media.zip')
    names = set(zipfile.ZipFile(z).namelist())
    assert {'ffrs/portraits/rain.png', 'ffrs/backgrounds/resonance.webp'} <= names
    assert not any('espacio' in n for n in names)
    # Instalado en otra máquina (sin las imágenes en la carpeta del usuario): se sirven del plugin
    for kind in ('portraits', 'backgrounds'):
        for f in (data_home / 'gamepad' / kind / 'ffrs').iterdir():
            f.unlink()
    assert plugin_pkg.install(z, yes=True, out=lambda *_: None)
    assert portraits.resolve('ffrs', 'resonance.webp', kind='backgrounds').read_bytes() == b'b'
    assert portraits.listing('ffrs', 'backgrounds') == ['/backgrounds/ffrs/resonance.webp']
    assert portraits.Finder('ffrs').url(1001, ('rain',)) == '/portraits/ffrs/rain.png'
