import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from server.plugins import import_module  # noqa: E402


def load_plugin(stem, submodule=None):
    """El plugin plugins/<stem>/ como paquete, igual que lo carga el hub (o uno de sus módulos)."""
    folder = ROOT / 'plugins' / stem
    if not (folder / 'plugin.py').is_file():
        pytest.skip(f'el plugin {stem} no está en este paquete (se distribuye aparte)', allow_module_level=True)
    name = f'test_plugin_{stem}'
    module = sys.modules.get(name) or import_module(name, folder / 'plugin.py', package_dir=folder)
    return importlib.import_module(f'{name}.{submodule}') if submodule else module


@pytest.fixture(autouse=True)
def data_home(tmp_path, monkeypatch):
    """Retratos y demás datos del usuario en una carpeta temporal."""
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'share'))
    return tmp_path / 'share'


@pytest.fixture
def ffrs():
    return load_plugin('ffrs')


@pytest.fixture
def attach(ffrs):
    """attach(game) -> plugin enganchado a la memoria sintética."""
    def _attach(game):
        plugin = ffrs.Plugin()
        plugin.on_attach(game.mem, game.proc())
        return plugin
    return _attach
