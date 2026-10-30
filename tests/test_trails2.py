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


def test_lee_mira_tiempo_y_grupo(attach):
    g = loaded()
    v = attach(g).read(g.mem)
    assert v['status'] == 'Lectura OK'
    assert v['mira'] == 123456
    assert v['playtime'] == '3 h 25 min'
    assert 'sepith' not in v                                   # no hace falta en el panel
    assert v['p1_name'] == 'Estelle' and v['p2_name'] == 'Joshua'
    assert v['p1_lv'] == 'Nv 20'
    assert (v['p1_hp'], v['p1_hp_max'], v['p1_ep'], v['p1_ep_max'], v['p1_cp'], v['p1_cp_max']) == \
        (900, 1000, 80, 100, 50, 200)
    assert v['p4_name'] == 'Olivier' and 'p5_name' not in v
    assert f'serie de 10 cada 0x{STRIDE:X}' in v['dbg_roster'] and 'Kevin' in v['dbg_roster']
    assert 'leído de la firma' in v['dbg_sig']


def test_el_offset_del_tiempo_sale_de_la_firma(attach):
    # Un parche que mueve el bloque: Mira sigue al offset leído del código
    g = loaded(playtime_off=0x20B700)
    v = attach(g).read(g.mem)
    assert v['mira'] == 123456
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
    assert v['mira'] == 500 and v['status'] == 'Mira y tiempo de juego OK; personajes aún no encontrados'
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
    assert ids['trails2'].version == '0.7.0'


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


def test_lista_del_grupo_en_el_diagnostico(attach, capsys):
    g = loaded()
    for i, cid in enumerate((0, 2, 4, 3)):                 # Estelle, Scherazard, Kloe, Olivier
        g.mem.put('u16', g.block + 0x50000 + i * 2, cid)
    plugin = attach(g)
    assert plugin.read(g.mem)['dbg_party'] == 'buscando…'   # una forma de lista por lectura
    for _ in range(10):
        v = plugin.read(g.mem)
    assert 'u16/2 +0x50000: Estelle, Scherazard, Kloe, Olivier' in v['dbg_party']
    assert 'grupo? ' in capsys.readouterr().out


def test_retratos(attach, data_home):
    g = loaded()
    folder = data_home / 'gamepad' / 'portraits' / 'trails2'
    folder.mkdir(parents=True)
    (folder / 'estelle.png').write_bytes(b'x')
    v = attach(g).read(g.mem)
    assert v['p1_img'] == '/portraits/trails2/estelle.png' and v['p2_img'] is None


# Código real de sora_2nd.exe 1.03.1 (launcher.log del usuario): "siguiente nivel" en
# exe+0xF9C20 y "EXP total" en exe+0xF9B30.
SIGUIENTE = bytes.fromhex(
    '48895c2408574883ec20488b3d172bb600488bd9488b4f108b13488b4908e83d'
    'bc15004885c07421488b4f28488b5040488b4908e817ed15004885c0740b8078'
    '1001b8af0000007405b8c8000000448b4304443bc07c0d33c0488b5c24304883'
    'c4205fc38b1341ffc0488bcbe89ffeffff2b4308488b5c24304883c4205fc3cc')
TOTAL = bytes.fromhex(
    '48895c240848896c241048897424184889 7c2420415648 83ec20418bd88bfa81'.replace(' ', '')
    + 'faffff000075028b11488b35e82bb600488b4610488b6808488bcde810bd1500'
    '4885c07421488b4e28488b5040488b4908e8eaed15004885c0740b80781001b8'
    'af0000007405b8c80000003bd88bd7488bcd0f4fd84533f68d43030fafc36bd8'
    '64e8cabc15004885c07442488b4e28488b5040488b4908e8a4ed15004885c074'
    '0af30f1090e8000000eb08f30f1015712fa300660f6ec30f5bc00f28c8f30f59'
    'caf30f5cc8f30f2cc103c3eb04418d041e488b5c2430488b6c2438488b742440'
    '488b7c24484883c420415ec3cccccccc48895c2408574883ec20488b3d172bb6')


def with_exp_code(g, mult=1.0):
    """Pone el código real en la imagen sintética (misma distancia entre funciones)."""
    import struct
    total = BASE + TEXT_RVA + 0x10000
    g.mem.write(total, TOTAL)
    g.mem.write(total + 0xF0, SIGUIENTE)
    movss = total + 0xAB                                   # f3 0f 10 15 <disp>: multiplicador por defecto
    const = BASE + 0x50000 + 0x100                          # en .data de la imagen sintética
    g.mem.put('f32', const, mult)
    g.mem.write(movss + 4, struct.pack('<i', const - (movss + 8)))
    return total


def test_formula_de_exp_leida_del_codigo_real(trails):
    expcurve = load_plugin('trails2', 'expcurve')
    g = loaded()
    total = with_exp_code(g)
    curve = expcurve.from_code(g.mem, total)
    assert (curve.add, curve.mul, curve.mult) == (3, 100, 1.0)
    assert curve.total(47) == 100 * 47 * 50 and curve.total(1) == 400
    assert curve.total(46) == 225_400 and curve.next(46, 230_000) == 5_000
    assert curve.consistent(46, 230_000) and not curve.consistent(46, 220_000) and not curve.consistent(46, 300_000)
    assert curve.next(200, 9_999_999) == 0
    boosted = expcurve.Curve(3, 100, 1.5)                   # multiplicador: base + trunc(base*0.5)
    assert boosted.total(10) == 13_000 + 6_500


def test_siguiente_nivel_en_las_tarjetas(attach, capsys):
    g = FakeTrails()
    g.money(1, SEPITH, 10.0)
    g.character(0, 0, 46, 230_000, 900, 1000, 80, 100, 50)    # Estelle
    g.character(1, 3, 46, 300_000, 900, 1000, 80, 100, 50)    # EXP que no cuadra con la fórmula
    with_exp_code(g)
    plugin = attach(g)
    assert 'EXP total = 100·N·(N+3) × 1' in capsys.readouterr().out
    v = plugin.read(g.mem)
    assert v['p1_lv'] == 'Nv 46 · Sig. 5.000'
    assert v['p2_lv'] == 'Nv 46' and 'no cuadra con Olivier' in v['dbg_exp']


def test_sin_codigo_de_exp_solo_el_nivel(attach, capsys):
    g = loaded()
    v = attach(g).read(g.mem)
    assert v['p1_lv'] == 'Nv 20' and 'sin "siguiente nivel"' in capsys.readouterr().out


def test_registra_los_personajes_en_el_log(attach, capsys):
    g = loaded()
    attach(g).read(g.mem)
    out = capsys.readouterr().out
    assert '[trails2]   bloque+0x18000 ID 0 Estelle Nv 20' in out and 'ID 119 Kevin' in out


def test_estilo_de_tarjetas(trails):
    from server import plugins as P
    assert trails.Plugin.party_style == 'ring'
    bad = trails.Plugin()
    bad.party_style = 'otro'
    import pytest as _p
    with _p.raises(ValueError, match='party_style'):
        P.check_plugin(bad)


def test_grupo_activo_desde_la_lista_del_juego(attach, capsys):
    # Como en la 1.03.1: registros cada 0x540; Estelle no pasa la comprobación estricta
    # (aquí, MOV fuera de rango) pero está en la rejilla; la lista manda el orden.
    g = FakeTrails()
    g.money(83930, SEPITH, 84000.0)
    order = [5, 0, 2, 4, 3, 6, 7, 124]                       # orden de los registros en memoria
    for i, cid in enumerate(order):
        g.character(i, cid, 46, 233_284, 4000 + i, 4074, 800, 871, 165, at=0x114000, stride=0x540)
    g.mem.put('u32', g.block + 0x114000 + 1 * 0x540 + 0x40, 0)      # MOV de Estelle = 0
    for i, cid in enumerate((0, 2, 4, 3, 5, 6, 7, 101)):
        g.mem.put('u16', g.block + 0x5145C + i * 2, cid)
    v = attach(g).read(g.mem)
    assert [v[f'p{n}_name'] for n in range(1, 5)] == ['Estelle', 'Scherazard', 'Kloe', 'Olivier']
    assert v['dbg_party'].startswith('lista del juego')
    out = capsys.readouterr().out
    assert 'rejilla bloque+0x114000' in out and 'ID 0 Estelle' in out


def test_sin_lista_valida_usa_los_primeros_registros(attach):
    g = loaded()
    g.mem.put('u16', g.block + 0x5145C, 0)                     # ceros: no es una lista
    v = attach(g).read(g.mem)
    assert v['p1_name'] == 'Estelle' and v['p4_name'] == 'Olivier'


def test_grupo_con_registros_fuera_de_la_serie(attach, capsys):
    # Como en la partida real (1.03.1): la serie cada 0x540 solo tiene Olivier, Tita, Zin,
    # Dorothy, Kurt y Kevin; Estelle, Scherazard y Kloe están en otra zona y no pasan la
    # comprobación estricta. Se encuentran por ID, con la EXP validada por la fórmula.
    g = FakeTrails()
    g.money(83930, SEPITH, 84000.0)
    with_exp_code(g)
    serie = [(3, 46, 233_284), (6, 46, 231_721), (7, 47, 230_300), (124, 35, 133_000),
             (100, 25, 68_600), (119, 35, 135_887)]
    for i, (cid, lv, exp) in enumerate(serie):
        g.character(i, cid, lv, exp, 3000, 3100, 500, 520, 100, at=0x114D78, stride=0x540)
    for i, (cid, lv, exp) in enumerate([(0, 46, 230_000), (2, 46, 229_000), (4, 45, 220_000)]):
        r = g.character(i, cid, lv, exp, 2000, 2100, 300, 310, 50, at=0x300000, stride=0x2A8)
        g.mem.put('u32', r + 0x40, 0)                         # MOV = 0: no pasa la estricta
    g.character(0, 2, 99, 1, 10, 10, 1, 1, 1, at=0x200000)    # ID 2 con EXP absurda: se descarta
    for i, cid in enumerate((0, 2, 4, 3, 5, 6, 7, 101)):
        g.mem.put('u16', g.block + 0x5145C + i * 2, cid)
    v = attach(g).read(g.mem)
    assert [v[f'p{n}_name'] for n in range(1, 5)] == ['Estelle', 'Scherazard', 'Kloe', 'Olivier']
    assert v['p1_lv'] == 'Nv 46 · Sig. 5.000' and v['p4_lv'] == 'Nv 46 · Sig. 1.716'   # Olivier: como el juego
    out = capsys.readouterr().out
    assert 'registro de Estelle por ID: bloque+0x300000' in out
    assert 'grupo? ' not in out                                # la lista ya cuadra: sin diagnóstico


def with_char_params(g, total, params):
    """Estructuras del juego para la búsqueda de parámetros por personaje (ver charparams.py).
    params: {ID: (nombre interno, multiplicador, tope 175?)}"""
    import struct
    import zlib
    heap = 0x30000000
    g.mem.map(heap, 0x10000)
    put = g.mem.put
    slot = BASE + 0x50000 + 0x200                              # [exe+global] -> gestor de datos
    mov = total + TOTAL.find(b'\x48\x8b\x35')                # mov rsi,[rip+disp]
    g.mem.write(mov + 3, struct.pack('<i', slot - (mov + 7)))
    mgr, a, t, desc, a2, t2, head = (heap + o for o in (0x0, 0x100, 0x200, 0x300, 0x400, 0x500, 0x600))
    put('u64', slot, mgr)
    put('u64', mgr + 0x10, a), put('u64', a + 8, t)
    put('i32', t + 0x28, 1)                                    # idx 1: desc + 0x50
    put('u64', t + 0x20, desc - 0x50)
    entries, step = heap + 0x1000, 0x60
    put('u32', desc + 0x44, 0x10), put('u32', desc + 0x48, step), put('u32', desc + 0x4C, len(params))
    qword = 0x10 | step << 32                                  # u64 en +0x44 (incluye el paso, como en el juego)
    put('u64', t + 0x10, (entries - qword) & ((1 << 64) - 1))
    put('u64', mgr + 0x28, a2), put('u64', a2 + 8, t2), put('u64', t2 + 0x38, head)
    prev = head
    for i, (cid, (name, mult, cap175)) in enumerate(params.items()):
        e, text, node, p = entries + i * step, heap + 0x3000 + i * 0x40, heap + 0x4000 + i * 0x40, heap + 0x6000 + i * 0x100
        put('u16', e, cid), put('u64', e + 0x40, text)
        g.mem.write(text, name.encode() + b'\0')
        put('u64', prev, node)                                 # siguiente
        put('u32', node + 0x10, zlib.crc32(name.encode())), put('u64', node + 0x18, p)
        put('u8', p + 0x10, 1 if cap175 else 0), put('f32', p + 0xE8, mult)
        prev = node
    put('u64', prev, head)


def test_siguiente_nivel_con_multiplicador_propio(attach, capsys):
    # Zin (invitado): EXP 230.300 en el nivel 47 = umbral × 0,98. Con su multiplicador del
    # juego, "Sig." = total(48) × 0,98 - 230.300 = 239.904 - 230.300 = 9.604.
    g = FakeTrails()
    g.money(1, SEPITH, 10.0)
    total = with_exp_code(g)
    with_char_params(g, total, {7: ('zin', 0.98, False), 3: ('olivier', 1.0, False)})
    for i, (cid, lv, exp) in enumerate([(0, 46, 230_000), (7, 47, 230_300), (4, 45, 220_000), (3, 46, 233_284)]):
        g.character(i, cid, lv, exp, 3000, 3100, 500, 520, 100)
    for i, cid in enumerate((0, 7, 4, 3)):
        g.mem.put('u16', g.block + 0x5145C + i * 2, cid)
    v = attach(g).read(g.mem)
    assert v['p2_name'] == 'Zin' and v['p2_lv'] == 'Nv 47 · Sig. 9.604'
    assert v['p4_lv'] == 'Nv 46 · Sig. 1.716'
    assert 'parámetros de Zin: zin crc' in capsys.readouterr().out


def test_el_grupo_cambia_sin_recargar(attach, capsys):
    # La lista de +0x5145C solo se actualiza al cargar; otra copia cambia al momento
    g = loaded()
    for off in (0x5145C, 0x12A9E4):
        for i, cid in enumerate((0, 2, 4, 3)):
            g.mem.put('u16', g.block + off + i * 2, cid)
    plugin = attach(g)
    assert plugin.read(g.mem)['p2_name'] == 'Scherazard'
    g.mem.put('u16', g.block + 0x12A9E4 + 2, 7)               # Zin entra por Scherazard
    v = plugin.read(g.mem)
    assert [v[f'p{n}_name'] for n in range(1, 5)] == ['Estelle', 'Zin', 'Kloe', 'Olivier']
    out = capsys.readouterr().out
    assert 'copias de la lista del grupo: bloque+0x5145C, bloque+0x12A9E4' in out
    assert 'grupo cambiado en bloque+0x12A9E4: Estelle, Zin, Kloe, Olivier' in out


def test_el_grupo_cambia_en_una_lista_que_no_era_copia(attach, capsys):
    # La lista viva no coincide al principio con la del grupo (otro orden o formato): se
    # descubre al ver que un miembro cambia por otro personaje.
    g = loaded()
    for i, cid in enumerate((0, 2, 4, 3)):
        g.mem.put('u16', g.block + 0x5145C + i * 2, cid)
    for i, cid in enumerate((3, 0, 2, 4)):                    # lista viva, en otro orden
        g.mem.put('u16', g.block + 0x200000 + i * 2, cid)
    plugin = attach(g)
    assert plugin.read(g.mem)['p2_name'] == 'Scherazard'
    g.mem.put('u16', g.block + 0x200000 + 4, 6)               # Tita entra por Scherazard
    plugin._next_diff = 0.0
    v = plugin.read(g.mem)
    assert [v[f'p{n}_name'] for n in range(1, 5)] == ['Olivier', 'Estelle', 'Tita', 'Kloe']
    assert 'grupo cambiado (Scherazard -> Tita) en bloque+0x200000' in capsys.readouterr().out
    plugin._next_diff = 0.0
    assert plugin.read(g.mem)['p3_name'] == 'Tita'             # y se sigue leyendo de ahí
