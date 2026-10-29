"""Paquetes de plugin: cargador (manifiesto, prioridad, validación) e instalador (zip)."""
import asyncio
import json
import stat
import threading
import zipfile

import pytest

from server import plugin_pkg, plugins as P
from server.memory import ProcInfo

CODE = '''from server.plugin_api import Field, GamePlugin

class Plugin(GamePlugin):
    id = {pid!r}
    name = 'Juego {tag}'
    process_names = ('Juego.exe',)
    fields = [Field('gold', 'Oro', tone='gold')]

    def read(self, mem):
        return {{'gold': {tag!r}}}
'''


def make_pkg(base, pid='mi_juego', tag='a', manifest=None, code=None):
    folder = base / pid
    folder.mkdir(parents=True)
    m = {'id': pid, 'name': 'Mi Juego', 'version': '1.2.0', 'api': P.API_VERSION, 'entry': 'plugin.py'}
    (folder / 'plugin.json').write_text(json.dumps(m if manifest is None else manifest))
    (folder / 'plugin.py').write_text(code or CODE.format(pid=pid, tag=tag))
    return folder


def make_zip(path, entries):
    with zipfile.ZipFile(path, 'w') as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


def good_zip(tmp_path, pid='mi_juego', tag='z', version='1.2.0'):
    m = {'id': pid, 'name': 'Mi Juego', 'version': version, 'api': P.API_VERSION}
    return make_zip(tmp_path / f'{pid}-{tag}.zip', {
        f'{pid}/plugin.json': json.dumps(m),
        f'{pid}/plugin.py': CODE.format(pid=pid, tag=tag),
        f'{pid}/README.md': 'hola'})


# --- cargador ---

def test_carga_paquete_con_version(tmp_path):
    make_pkg(tmp_path)
    [plugin] = P.load_plugins(tmp_path)
    assert plugin.id == 'mi_juego' and plugin.version == '1.2.0' and plugin.read(None) == {'gold': 'a'}


def test_el_instalado_gana_al_incluido(tmp_path, capsys):
    make_pkg(tmp_path / 'incluidos', tag='viejo')
    make_pkg(tmp_path / 'instalados', tag='nuevo')
    [plugin] = P.load_plugins([tmp_path / 'incluidos', tmp_path / 'instalados'])
    assert plugin.read(None) == {'gold': 'nuevo'}
    assert 'se usa' in capsys.readouterr().out


def test_paquete_gana_al_archivo_suelto_antiguo(tmp_path):
    (tmp_path / 'incluidos').mkdir()
    (tmp_path / 'incluidos' / 'mi_juego.py').write_text(CODE.format(pid='mi_juego', tag='suelto'))
    make_pkg(tmp_path / 'instalados', tag='paquete')
    [plugin] = P.load_plugins([tmp_path / 'incluidos', tmp_path / 'instalados'])
    assert plugin.read(None) == {'gold': 'paquete'}


@pytest.mark.parametrize('manifest, error', [
    ({'id': 'mi_juego', 'name': 'x', 'version': '1.0', 'api': 99}, 'API 99'),
    ({'id': 'otro', 'name': 'x', 'version': '1.0', 'api': 1}, 'no coincide'),
    ({'id': 'mi_juego', 'name': 'x', 'version': 'beta', 'api': 1}, 'versión inválida'),
    ({'id': 'mi_juego', 'name': 'x', 'version': '1.0', 'api': 1, 'entry': '../x.py'}, 'entry inválido'),
    ({'id': 'mi_juego', 'version': '1.0', 'api': 1}, 'falta "name"'),
])
def test_manifiestos_invalidos_se_ignoran(tmp_path, capsys, manifest, error):
    make_pkg(tmp_path, manifest=manifest)
    assert P.load_plugins(tmp_path) == []
    assert error in capsys.readouterr().out


def test_campos_invalidos(tmp_path, capsys):
    bad = CODE.format(pid='mi_juego', tag='a').replace(
        "fields = [Field('gold', 'Oro', tone='gold')]",
        "fields = [Field('gold', 'Oro'), Field('gold', 'Otra vez')]")
    make_pkg(tmp_path, code=bad)
    assert P.load_plugins(tmp_path) == []
    assert "campo repetido 'gold'" in capsys.readouterr().out


def test_el_plugin_ffrs_del_repo_es_valido():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / 'plugins'
    if not (root / 'ffrs').is_dir():
        pytest.skip('ffrs se distribuye aparte')
    ids = {p.id: p for p in P.load_plugins(root)}
    assert ids['ffrs'].version and 'demo' in ids


# --- read() lento ---

def test_read_lento_no_lanza_otra_lectura(monkeypatch):
    release, calls = threading.Event(), []

    class Slow(P.GamePlugin):
        id = 'lento'

        def read(self, mem):
            calls.append(1)
            release.wait(5)
            return {'v': 1}

    class Mem:
        def alive(self): return True
        def close(self): pass

    m = P.PluginManager([Slow()], root_pid=1)
    m.READ_TIMEOUT = 0.05
    m.active = (m.plugins[0], Mem(), ProcInfo(1, 'x', 'x', 'x'))

    async def run():
        first = await m.tick()
        second = await m.tick()
        release.set()
        await asyncio.sleep(0.05)
        third = await m.tick()
        return first, second, third

    first, second, third = asyncio.run(run())
    assert first == [{'t': 'gv', 'err': 'el plugin tarda más de 0 s en leer'}]
    assert second == []                     # sigue esperando la misma lectura
    assert third == [{'t': 'gv', 'v': {'v': 1}}]
    assert len(calls) == 1


# --- instalador ---

def test_instalar_listar_actualizar_y_quitar(tmp_path):
    dest, out = tmp_path / 'plugins', []
    assert plugin_pkg.install(good_zip(tmp_path, tag='uno'), yes=True, dest=dest, out=out.append)
    assert (dest / 'mi_juego' / 'plugin.json').is_file()
    [plugin] = P.load_plugins(dest)
    assert plugin.read(None) == {'gold': 'uno'}
    assert plugin_pkg.install(good_zip(tmp_path, tag='dos', version='1.3.0'), yes=True, dest=dest, out=out.append)
    assert any('sustituye a 1.2.0' in line for line in out)
    assert P.load_plugins(dest)[0].read(None) == {'gold': 'dos'}
    assert sorted(p.name for p in dest.iterdir()) == ['mi_juego']        # sin restos .tmp/.old
    assert plugin_pkg.remove('mi_juego', yes=True, dest=dest, out=out.append)
    assert not (dest / 'mi_juego').exists()


def test_instalar_pide_confirmacion(tmp_path):
    dest = tmp_path / 'plugins'
    assert not plugin_pkg.install(good_zip(tmp_path), dest=dest, out=lambda *_: None, ask=lambda _: 'n')
    assert not (dest / 'mi_juego').exists()


@pytest.mark.parametrize('entries, error', [
    ({'mi_juego/plugin.json': '{}', '../evil.py': 'x'}, 'ruta no permitida'),
    ({'/etc/passwd': 'x'}, 'ruta no permitida'),
    ({'mi_juego/plugin.py': 'x', 'otro/plugin.py': 'x'}, 'una sola carpeta raíz'),
    ({'plugin.json': '{}'}, 'fuera de la carpeta'),
    ({'mi_juego/plugin.py': 'x'}, 'falta mi_juego/plugin.json'),
    ({'mi_juego/plugin.json': json.dumps({'id': 'mi_juego', 'name': 'x', 'version': '1.0', 'api': 1})},
     'no existe el archivo de entrada'),
    ({'mi_juego/plugin.json': json.dumps({'id': 'mi_juego', 'name': 'x', 'version': '1.0', 'api': 2}),
      'mi_juego/plugin.py': 'x'}, 'API 2'),
])
def test_zips_rechazados(tmp_path, entries, error):
    z = make_zip(tmp_path / 'malo.zip', entries)
    with pytest.raises(plugin_pkg.PackageError, match=error):
        plugin_pkg.install(z, yes=True, dest=tmp_path / 'plugins', out=lambda *_: None)
    assert not (tmp_path / 'plugins').exists() or not any((tmp_path / 'plugins').iterdir())


def test_zip_con_enlace_simbolico(tmp_path):
    z = tmp_path / 'link.zip'
    with zipfile.ZipFile(z, 'w') as zf:
        zf.writestr('mi_juego/plugin.json', '{}')
        info = zipfile.ZipInfo('mi_juego/plugin.py')
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, '/etc/passwd')
    with pytest.raises(plugin_pkg.PackageError, match='enlace simbólico'):
        plugin_pkg.inspect(z)
