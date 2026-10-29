import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))


def load_plugin(stem):
    spec = importlib.util.spec_from_file_location(f'test_plugin_{stem}', ROOT / 'plugins' / f'{stem}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
