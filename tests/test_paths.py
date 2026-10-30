"""Rutas del usuario, también dentro del sandbox de Flatpak (Heroic)."""
from server import paths


def flatpak(monkeypatch, tmp_path, on=True):
    monkeypatch.setattr(paths, 'in_flatpak', lambda: on)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('XDG_RUNTIME_DIR', str(tmp_path / 'run'))
    # Lo que pone Flatpak: carpetas propias de la app
    for name, sub in (('XDG_CACHE_HOME', 'cache'), ('XDG_DATA_HOME', 'data'), ('XDG_STATE_HOME', '.local/state')):
        monkeypatch.setenv(name, str(tmp_path / '.var/app/com.heroicgameslauncher.hgl' / sub))
        monkeypatch.delenv('HOST_' + name, raising=False)


def test_en_flatpak_se_usan_las_carpetas_del_sistema(monkeypatch, tmp_path):
    flatpak(monkeypatch, tmp_path)
    assert paths.cache_dir() == tmp_path / '.cache/gamepad'
    assert paths.plugins_dir() == tmp_path / '.local/share/gamepad/plugins'
    assert paths.mangohud_dir() == tmp_path / '.cache/gamepad/mangologs'   # la misma que lee el servicio
    assert paths.socket_path() == tmp_path / '.cache/gamepad/hub.sock'
    assert paths.log_dir() == tmp_path / '.cache/gamepad'
    assert (paths.cache_dir().stat().st_mode & 0o777) == 0o700


def test_en_flatpak_respeta_host_xdg(monkeypatch, tmp_path):
    flatpak(monkeypatch, tmp_path)
    monkeypatch.setenv('HOST_XDG_DATA_HOME', str(tmp_path / 'datos'))
    assert paths.data_dir() == tmp_path / 'datos/gamepad'


def test_fuera_de_flatpak_sin_cambios(monkeypatch, tmp_path):
    flatpak(monkeypatch, tmp_path, on=False)
    assert paths.socket_path() == tmp_path / 'run/gamepad/hub.sock'
    assert paths.log_dir() == tmp_path / 'run/gamepad'
    assert paths.data_dir() == tmp_path / '.var/app/com.heroicgameslauncher.hgl/data/gamepad'


def test_el_servicio_escucha_en_ambos_sockets(monkeypatch, tmp_path):
    flatpak(monkeypatch, tmp_path, on=False)
    assert paths.socket_paths() == [tmp_path / 'run/gamepad/hub.sock', tmp_path / '.var/app/com.heroicgameslauncher.hgl/cache/gamepad/hub.sock']
