"""Plugin trails2 contra la memoria sintética de sora_2nd.exe."""
import pytest

from conftest import load_plugin
from fake_trails import BASE, HEAP, TEXT_RVA, FakeTrails

SEPITH = [11, 22, 33, 44, 55, 66, 77, 888]


@pytest.fixture
def trails():
    return load_plugin('trails2')


@pytest.fixture
def attach(trails):
    def _attach(game):
        plugin = trails.Plugin()
        assert plugin.matches(game.proc())
        plugin.on_attach(game.mem, game.proc())
        return plugin
    return _attach


def loaded(**kw):
    g = FakeTrails(**kw)
    g.money(123456, SEPITH, 3 * 3600 + 25 * 60 + 9.5)
    return g


def test_lee_mira_y_tiempo(attach):
    g = loaded()
    v = attach(g).read(g.mem)
    assert v['status'] == 'Lectura OK'
    assert v['mira'] == 123456 and v['playtime'] == '3 h 25 min'
    assert 'leído de la firma' in v['dbg_sig']
    assert not any(k.startswith('p1_') for k in v) and 'sepith' not in v   # sin personajes


def test_brave_gauge_y_su_tope(attach):
    g = loaded()
    g.brave(487)
    plugin = attach(g)
    v = plugin.read(g.mem)
    assert (v['brave'], v['brave_max']) == (4, 5)               # el juego muestra centenas
    assert '487/500' in v['dbg_brave'] and '+0x2C50]+0x260]+0x48' in v['dbg_brave']
    g.brave(650, flags=4)                                       # tope 700 con el bit 4
    assert (plugin.read(g.mem)['brave'], plugin.read(g.mem)['brave_max']) == (6, 7)
    g.brave(600, flags=2)
    assert plugin.read(g.mem)['brave_max'] == 6


def test_brave_sin_datos_o_fuera_de_rango_no_se_muestra(attach):
    g = loaded()
    g.brave(900)                                                # mayor que el tope: no es la gauge
    plugin = attach(g)
    assert 'brave' not in plugin.read(g.mem)
    g.mem.put('u64', BASE + 0x50000 + 0x300, 0)                 # aún sin objeto (título, carga)
    v = plugin.read(g.mem)
    assert 'brave' not in v and v['mira'] == 123456


def test_sin_firma_de_brave_lo_demas_sigue(attach):
    g = loaded()
    g.brave(300, code=False)
    v = attach(g).read(g.mem)
    assert 'brave' not in v and v['mira'] == 123456 and 'firma de Brave no encontrada' in v['dbg_brave']


def test_el_offset_del_tiempo_sale_de_la_firma(attach):
    g = loaded(playtime_off=0x20B700)
    v = attach(g).read(g.mem)
    assert v['mira'] == 123456 and '0x20B700 (leído de la firma)' in v['dbg_sig']


def test_sin_firma_del_tiempo_usa_el_offset_de_la_tabla(attach):
    g = loaded(playtime_sig=False)
    v = attach(g).read(g.mem)
    assert v['mira'] == 123456 and 'de la tabla' in v['dbg_sig']


def test_sin_firma_del_bloque_no_inventa_datos(attach):
    g = loaded(state_sig=False)
    v = attach(g).read(g.mem)
    assert 'firma de Mira no encontrada' in v['status'] and 'mira' not in v


def test_firma_ambigua(attach):
    from fake_trails import state_insn
    g = loaded()
    at = BASE + TEXT_RVA + 0x8000
    g.mem.write(at, state_insn(at))
    assert 'ambigua' in attach(g).read(g.mem)['status']


def test_pantalla_de_titulo_y_despues_partida(attach):
    g = FakeTrails(block=False)
    plugin = attach(g)
    assert plugin.read(g.mem)['status'] == 'Esperando a que el juego cree sus datos'
    g.new_block(HEAP)
    assert plugin.read(g.mem)['status'] == 'Esperando a que cargues una partida'
    g.money(500, SEPITH, 60.0)
    v = plugin.read(g.mem)
    assert v['mira'] == 500 and v['status'] == 'Lectura OK'


def test_datos_que_no_cuadran(attach):
    g = loaded()
    g.money(123, SEPITH, float('nan'))
    v = attach(g).read(g.mem)
    assert v['status'].startswith('Los datos no cuadran') and 'mira' not in v


def test_firmas_partidas_entre_trozos(monkeypatch):
    scan = load_plugin('trails2', 'scan')
    g = FakeTrails(state_sig=False, playtime_sig=False)
    from fake_trails import playtime_insn
    monkeypatch.setattr(scan, 'CHUNK', 0x1000)
    at = BASE + TEXT_RVA + 0x1000 - 5           # cruza el límite de un trozo
    g.mem.write(at, playtime_insn(0x1234))
    assert scan.find(g.mem, BASE, 'F2??????????????F2??????????????0F57??F3') == [at]
    assert scan.find(g.mem, BASE, 'F2 0F 58 83 34 12 00 00') == [at]
    with pytest.raises(ValueError):
        scan.compile_aob('F2 0')


def test_el_plugin_es_valido_para_el_hub():
    from server import plugins as P
    from conftest import ROOT
    ids = {p.id: p for p in P.load_plugins(ROOT / 'plugins')}
    assert ids['trails2'].version == '0.8.0'
    assert next(f for f in ids['trails2'].fields if f.key == 'brave').kind == 'gear'
