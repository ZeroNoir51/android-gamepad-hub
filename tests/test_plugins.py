"""PluginManager: reintentos al enganchar mientras el juego arranca."""
import pytest

from server import plugins as P
from server.memory import MemoryReadError, ProcInfo

PROC = ProcInfo(500, 'Game.exe', 'Game.exe', 'Game.exe')


class FakeMem:
    closed = 0

    def close(self):
        FakeMem.closed += 1


class Flaky(P.GamePlugin):
    id = 'flaky'
    process_names = ('Game.exe',)

    def __init__(self, failures, exc=MemoryReadError):
        self.failures, self.exc = failures, exc

    def on_attach(self, mem, proc):
        if self.failures:
            self.failures -= 1
            raise self.exc('dirección inválida 0x0')


@pytest.fixture(autouse=True)
def fake_proc(monkeypatch):
    FakeMem.closed = 0
    monkeypatch.setattr(P, 'descendants', lambda root: [PROC])
    monkeypatch.setattr(P, 'open_process', lambda pid, ptr: FakeMem())


def test_reintenta_mientras_el_juego_arranca(capsys):
    m = P.PluginManager([Flaky(failures=3)], root_pid=1)
    assert [m._scan() for _ in range(3)] == [None, None, None]
    active = m._scan()
    assert active and active[2] is PROC
    assert FakeMem.closed == 3                        # cada intento fallido cierra su descriptor
    out = capsys.readouterr().out
    assert out.count('aún no se puede leer') == 1     # sin llenar el log
    assert 'ya se puede leer' in out


def test_error_definitivo_no_se_reintenta():
    plugin = Flaky(failures=1, exc=PermissionError)
    m = P.PluginManager([plugin], root_pid=1)
    assert m._scan() is None
    assert m._scan() is None and plugin.failures == 0  # no volvió a llamar a on_attach
    assert FakeMem.closed == 1


def test_explica_cuando_el_juego_corre_fuera_del_arbol(monkeypatch, capsys):
    shell = ProcInfo(501, 'gamemoderun', 'gamemoderun', 'gamemoderun umu_run.py')
    monkeypatch.setattr(P, 'descendants', lambda root: [shell])
    monkeypatch.setattr(P, 'iter_processes', lambda: [shell, PROC])   # el juego, en otra rama
    m = P.PluginManager([Flaky(failures=0)], root_pid=1)
    assert m._scan() is None and capsys.readouterr().out == ''        # aún arrancando: silencio
    m._started -= m.NOT_FOUND_LOG_AFTER
    assert m._scan() is None
    out = capsys.readouterr().out
    assert 'gamemoderun' in out and 'PID 500' in out and 'NO es descendiente' in out
    m._scan()
    assert capsys.readouterr().out == ''                              # una sola vez


def test_no_explica_si_el_juego_es_descendiente_pero_aun_arranca(capsys):
    m = P.PluginManager([Flaky(failures=5)], root_pid=1)
    m._started -= m.NOT_FOUND_LOG_AFTER
    m._scan()
    assert 'ningún juego' not in capsys.readouterr().out
