"""Lanzador: logging de MangoHud según cómo se lance el juego."""
from server import launcher


def conf(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher.paths, 'cache_dir', lambda: tmp_path)
    return tmp_path / 'mangohud.conf'


def test_sin_mangohud_se_activa_solo_para_registrar(tmp_path, monkeypatch):
    # Steam Big Picture: el contador es mangoapp; el juego no carga MangoHud por sí solo
    target = conf(tmp_path, monkeypatch)
    env = {'MANGOHUD_CONFIGFILE': str(tmp_path / 'steam.conf')}
    (tmp_path / 'steam.conf').write_text('fps\nframe_timing=1\nno_display=0\n')
    note = launcher.mangohud_env(env, tmp_path / 'logs', ['/usr/bin/umu-run', 'game.exe'])
    assert env['MANGOHUD'] == '1' and 'solo para registrar' in note
    text = target.read_text()
    assert 'no_display=1' in text and 'no_display=0' not in text and 'output_folder=' in text


def test_con_mangohud_del_jugador_se_respeta_su_overlay(tmp_path, monkeypatch):
    target = conf(tmp_path, monkeypatch)
    for env, cmd in (({'MANGOHUD': '1'}, ['umu-run', 'g.exe']), ({}, ['/usr/bin/mangohud', '--dlsym', 'umu-run'])):
        note = launcher.mangohud_env(env, tmp_path / 'logs', cmd)
        assert 'no_display' not in target.read_text() and 'solo para registrar' not in note


def test_config_en_linea(tmp_path):
    env = {'MANGOHUD_CONFIG': 'fps,no_display=0'}
    launcher.mangohud_env(env, tmp_path, [])
    assert env['MANGOHUD_CONFIG'].endswith('no_display=1') and 'no_display=0' not in env['MANGOHUD_CONFIG']
