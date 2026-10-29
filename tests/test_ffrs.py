"""Plugin FFRS contra la memoria sintética: los casos de la sección 10 del HANDOFF."""
from fake_ue import HP_PROPS, FakeGame, build_ffrs, cumulative


def party(values, n):
    return {k: v for k, v in values.items() if k.startswith(f'p{n}_')}


def test_fuera_de_batalla_equipo_de_2(attach):
    g = build_ffrs(party=(1001, 1002))
    v = attach(g).read(g.mem)
    assert v['status'] == 'Lectura OK'
    assert v['gil'] == 12345
    assert v['battle'] == 'fuera de batalla'
    assert v['world'] == 'Mucha_World'
    assert v['p1_name'] == 'Rain' and v['p2_name'] == 'Lasswell'
    assert v['p1_lv'] == 'Nv 5 · faltan 600 EXP'
    assert v['p2_lv'] == 'Nv 10 · faltan 1.100 EXP'
    assert not party(v, 3) and not party(v, 4)
    assert not any(k.endswith(('_hp', '_mp', '_hp_max', '_mp_max')) for k in v)
    assert v['hp_source'] == 'esperando una batalla'


def test_nivel_maximo_y_parcial(attach):
    g = build_ffrs(party=(1001, 1002), units={1001: cumulative(99) + 5, 1002: cumulative(7) + 50})
    v = attach(g).read(g.mem)
    assert v['p1_lv'] == 'Nv 99 · máximo'
    assert v['p2_lv'] == f'Nv 7 · faltan {cumulative(8) - cumulative(7) - 50} EXP'


def test_en_batalla_hp_mp_y_orden(attach):
    battle = [(1002, {'hp': 800, 'hp_max': 1000, 'mp': 40, 'mp_max': 90}),
              (1001, {'hp': 1200, 'hp_max': 1200, 'mp': 0, 'mp_max': 60})]
    g = build_ffrs(party=(1001, 1002), battle=battle)
    plugin = attach(g)
    v = plugin.read(g.mem)
    assert v['battle'] == 'en batalla (2)'
    assert v['p1_name'] == 'Lasswell' and v['p2_name'] == 'Rain'      # orden de batalla
    assert (v['p1_hp'], v['p1_hp_max'], v['p1_mp'], v['p1_mp_max']) == (800, 1000, 40, 90)
    assert (v['p2_hp'], v['p2_hp_max'], v['p2_mp'], v['p2_mp_max']) == (1200, 1200, 0, 60)
    assert v['p1_lv'] == 'Nv 10 · faltan 1.100 EXP'                  # la EXP sigue al ID
    assert v['hp_source'] == 'por nombre: hp@0xE0, hp_max@0xE4, mp@0xE8, mp_max@0xEC'
    # La segunda lectura reutiliza los offsets resueltos
    assert plugin.read(g.mem)['p1_hp'] == 800


def test_personaje_sin_curva_no_rompe_los_demas(attach):
    g = build_ffrs(party=(1001, 1006), curve_for=(1001, 1002, 1003))
    plugin = attach(g)
    v = plugin.read(g.mem)
    assert v['p1_lv'] == 'Nv 5 · faltan 600 EXP'
    assert v.get('p2_lv') is None and v['p2_name']
    assert sorted(plugin.curves) == [1001, 1002, 1003]


def test_build_distinta_no_lee(attach):
    g = FakeGame(build={'timestamp': 0x12345678, 'image_size': 503013376})
    build_ffrs(g)
    plugin = attach(g)
    assert plugin.ue is None
    v = plugin.read(g.mem)
    assert 'Build distinta' in v['status']
    assert v['build'].endswith('(build distinta)')
    assert 'gil' not in v and 'p1_name' not in v


def test_reflexion_no_verificada(attach):
    props = [p for p in HP_PROPS if p[2] != 0x118]
    g = build_ffrs(battle=[(1001, {'hp': 1, 'hp_max': 2, 'mp': 3, 'mp_max': 4})], props=props)
    v = attach(g).read(g.mem)
    assert v['hp_source'].startswith('reflexión no verificada')
    assert v['p1_name'] == 'Rain'
    assert 'p1_hp' not in v and 'p1_mp' not in v


def test_reflexion_ausente(attach):
    g = build_ffrs(battle=[(1001, {'hp': 1})], props=None)
    v = attach(g).read(g.mem)
    assert v['hp_source'].startswith('reflexión no verificada')
    assert 'p1_hp' not in v


def test_nombres_ambiguos_se_descartan(attach):
    props = HP_PROPS + [('CurrentHP', 'IntProperty', 0xF0, 'CPP_UnitParameter')]
    g = build_ffrs(battle=[(1001, {'hp': 500, 'hp_max': 900, 'mp': 10, 'mp_max': 20})], props=props)
    v = attach(g).read(g.mem)
    assert 'p1_hp' not in v
    assert v['p1_hp_max'] == 900 and v['p1_mp'] == 10
    assert 'faltan hp' in v['hp_source']


def test_sin_partida_cargada(attach):
    g = build_ffrs(save=False)
    v = attach(g).read(g.mem)
    assert v['status'] == 'Esperando a que cargues una partida'
    assert 'gil' not in v


def test_ignora_el_cdo_del_gestor(attach):
    # build_ffrs crea un Default__CPP_MuchaSaveDataManager con el mismo outer:
    # si el escaneo no lo descartara, habría 2 gestores y no leería nada.
    g = build_ffrs()
    assert attach(g).read(g.mem)['status'] == 'Lectura OK'
