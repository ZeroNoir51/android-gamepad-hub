"""Plugin trails2 contra la memoria sintética de sora_2nd.exe."""
import pytest

from conftest import load_plugin
from fake_trails import BASE, HEAP, STRIDE, TEXT_RVA, FakeTrails

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
    g.party()
    return g


def test_lee_mira_sepith_tiempo_y_grupo(attach):
    g = loaded()
    v = attach(g).read(g.mem)
    assert v['status'] == 'Lectura OK'
    assert v['mira'] == 123456
    assert v['playtime'] == '3 h 25 min'
    assert v['sepith'].startswith('Tierra 11 · Agua 22') and v['sepith'].endswith('Masa 888')
    assert v['p1_name'] == 'Estelle' and v['p2_name'] == 'Joshua'
    assert v['p1_lv'] == 'Nv 20 · 20.000 EXP'
    assert (v['p1_hp'], v['p1_hp_max'], v['p1_ep'], v['p1_ep_max'], v['p1_cp'], v['p1_cp_max']) == \
        (900, 1000, 80, 100, 50, 200)
    assert v['p4_name'] == 'Olivier' and 'p5_name' not in v
    assert f'serie de 10 cada 0x{STRIDE:X}' in v['dbg_roster'] and 'Kevin Nv29' in v['dbg_roster']
    assert 'leído de la firma' in v['dbg_sig']


def test_el_offset_del_tiempo_sale_de_la_firma(attach):
    # Un parche que mueve el bloque: Mira y sepith siguen al offset leído del código
    g = loaded(playtime_off=0x20B700)
    v = attach(g).read(g.mem)
    assert v['mira'] == 123456 and v['sepith'].endswith('Masa 888')
    assert '0x20B700 (leído de la firma)' in v['dbg_sig']


def test_sin_firma_del_tiempo_usa_el_offset_de_la_tabla(attach):
    g = loaded(playtime_sig=False)
    v = attach(g).read(g.mem)
    assert v['mira'] == 123456 and 'de la tabla' in v['dbg_sig']


def test_sin_firma_del_bloque_no_inventa_datos(attach):
    g = loaded(state_sig=False)
    v = attach(g).read(g.mem)
    assert 'firma de Mira/sepith no encontrada' in v['status'] and 'mira' not in v


def test_firma_ambigua(attach, trails):
    g = loaded()
    from fake_trails import state_insn
    at = BASE + TEXT_RVA + 0x8000
    g.mem.write(at, state_insn(at))
    v = attach(g).read(g.mem)
    assert 'ambigua' in v['status']


def test_pantalla_de_titulo_y_despues_partida(attach):
    g = FakeTrails(block=False)
    plugin = attach(g)
    assert plugin.read(g.mem)['status'] == 'Esperando a que el juego cree sus datos'
    g.new_block(HEAP)
    assert plugin.read(g.mem)['status'] == 'Esperando a que cargues una partida'
    g.money(500, SEPITH, 60.0)
    plugin._next_scan = 0.0
    v = plugin.read(g.mem)
    assert v['mira'] == 500 and v['status'] == 'Mira y sepith OK; personajes aún no encontrados'
    g.party()
    plugin._next_scan = 0.0            # sin esperar los 10 s entre búsquedas
    assert plugin.read(g.mem)['p1_name'] == 'Estelle'


def test_cargar_otra_partida_vuelve_a_buscar(attach):
    g = loaded()
    plugin = attach(g)
    assert plugin.read(g.mem)['p1_name'] == 'Estelle'
    g.new_block(HEAP + 0x1000000)      # bloque nuevo en otra dirección
    g.money(7, SEPITH, 10.0)
    g.party(n=3)
    v = plugin.read(g.mem)
    assert v['mira'] == 7 and 'serie de 3' in v['dbg_roster']


def test_datos_que_no_cuadran(attach):
    g = loaded()
    g.money(123, SEPITH, float('nan'))
    v = attach(g).read(g.mem)
    assert v['status'].startswith('Los datos no cuadran') and 'mira' not in v


def test_registros_sueltos_no_ganan_al_array(trails):
    roster = load_plugin('trails2', 'roster')
    assert roster.best_run([0x100, 0x5000, 0x5400, 0x5800, 0x5C00, 0x9000]) == (0x5000, 0x400, 4)
    assert roster.best_run([0x100, 0x104, 0x108, 0x10C]) == (0x100, 0, 1)   # se solaparían
    assert roster.best_run([0x100]) == (0x100, 0, 1)
    assert roster.best_run([]) is None
    assert roster.RECORD.size == 0x48


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


def test_el_plugin_es_valido_para_el_hub(tmp_path):
    from server import plugins as P
    from conftest import ROOT
    ids = {p.id: p for p in P.load_plugins(ROOT / 'plugins')}
    assert ids['trails2'].version == '0.1.0'


def test_un_array_de_numeros_parecidos_no_gana_al_grupo(attach):
    g = loaded()
    # 30 copias seguidas del mismo personaje (más larga que el grupo) y una copia suelta;
    # sus "ventanas" desplazadas también cuadran y tienen IDs distintos (pero desconocidos)
    for k in range(30):
        g.character(k, 3, 40, 1, 10, 10, 1, 1, 1, at=0x300000, stride=0x48)
    g.character(0, 3, 40, 1, 10, 10, 1, 1, 1, at=0x400000)
    plugin = attach(g)
    assert len(load_plugin('trails2', 'roster').candidates(g.mem, g.block, 0x700000)) > 41   # + ventanas
    v = plugin.read(g.mem)
    assert v['p1_name'] == 'Estelle' and f'serie de 10 cada 0x{STRIDE:X}' in v['dbg_roster']


def test_registros_con_mismo_id_cuentan_una_vez(trails):
    roster = load_plugin('trails2', 'roster')
    ids = {0x100: 1, 0x200: 1, 0x300: 1, 0x5000: 1, 0x5400: 2, 0x5800: 3}
    assert roster.best_run(sorted(ids), ids.get) == (0x5000, 0x400, 3)


def test_ventana_desplazada_anterior_no_gana_por_empate(trails):
    roster = load_plugin('trails2', 'roster')
    ids = {0x1000: 0, 0x1400: 1, 0x1800: 2, 0x0FF0: 900, 0x13F0: 901, 0x17F0: 902}
    assert roster.best_run(sorted(ids), ids.get, known={0, 1, 2}) == (0x1000, 0x400, 3)
