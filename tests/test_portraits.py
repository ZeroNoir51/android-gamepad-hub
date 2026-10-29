"""Validación de rutas de retratos (lo que expone el servicio por HTTP)."""
import os

import pytest

from server import portraits


@pytest.fixture
def root(tmp_path):
    (tmp_path / 'ffrs').mkdir()
    (tmp_path / 'ffrs' / '1001.png').write_bytes(b'x')
    (tmp_path / 'ffrs' / 'evil.svg').write_bytes(b'<svg/>')
    (tmp_path / 'secret.png').write_bytes(b'x')
    (tmp_path / 'outside').mkdir()
    (tmp_path / 'outside' / 'x.png').write_bytes(b'x')
    os.symlink(tmp_path / 'outside' / 'x.png', tmp_path / 'ffrs' / 'link.png')
    return tmp_path


def test_valido(root):
    assert portraits.resolve('ffrs', '1001.png', root) == root / 'ffrs' / '1001.png'
    assert portraits.content_type(root / 'ffrs' / '1001.png') == 'image/png'


@pytest.mark.parametrize('plugin,name', [
    ('ffrs', 'evil.svg'),            # SVG puede llevar scripts
    ('ffrs', '../secret.png'),
    ('..', 'secret.png'),
    ('ffrs', '..%2Fsecret.png'),
    ('FFRS', '1001.png'),
    ('ffrs', '1001.PNG.exe'),
    ('ffrs', 'nope.png'),             # no existe
    ('ffrs', 'link.png'),             # enlace que sale de la carpeta
    ('', ''),
    (None, None),
])
def test_rechazados(root, plugin, name):
    assert portraits.resolve(plugin, name, root) is None


def test_finder_cachea_y_recoge_nuevas(tmp_path, monkeypatch):
    (tmp_path / 'ffrs').mkdir()
    finder = portraits.Finder('ffrs', tmp_path)
    assert finder.url(1001, ('rain',)) is None
    (tmp_path / 'ffrs' / 'rain.jpg').write_bytes(b'x')
    assert finder.url(1001, ('rain',)) is None        # caché de 10 s
    monkeypatch.setattr(portraits, 'RECHECK_EVERY', 0)
    finder._cache.clear()
    assert finder.url(1001, ('rain',)) == '/portraits/ffrs/rain.jpg'
