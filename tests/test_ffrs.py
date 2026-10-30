"""Plugin FFRS contra la memoria sintética: los casos de la sección 10 del HANDOFF."""
from fake_ue import FakeGame, build_ffrs, cumulative, kill, unit_parameter, viewmodel

STATS = {1001: {'hp': 1200, 'hp_max': 1500, 'mp': 30, 'mp_max': 60},
         1002: {'hp': 800, 'hp_max': 1000, 'mp': 40, 'mp_max': 90}}


def party(values, n):
    return {k: v for k, v in values.items() if k.startswith(f'p{n}_')}


def hp(values, n):
    return tuple(values.get(f'p{n}_{k}') for k in ('hp', 'hp_max', 'mp', 'mp_max'))


# --- partida, equipo y nivel ---

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
    assert hp(v, 1) == (None,) * 4                    # sin parámetros ni ViewModels: sin HP
    assert v['hp_source'] == 'sin objetos de HP/MP todavía (fuera de batalla)'


def test_nivel_maximo_y_parcial(attach):
    g = build_ffrs(party=(1001, 1002), units={1001: cumulative(99) + 5, 1002: cumulative(7) + 50})
    v = attach(g).read(g.mem)
    assert v['p1_lv'] == 'Nv 99 · máximo'
    assert v['p2_lv'] == f'Nv 7 · faltan {cumulative(8) - cumulative(7) - 50} EXP'


def test_personaje_sin_curva_no_rompe_los_demas(attach):
    g = build_ffrs(party=(1001, 1006), curve_for=(1001, 1002, 1003))
    plugin = attach(g)
    v = plugin.read(g.mem)
    assert v['p1_lv'] == 'Nv 5 · faltan 600 EXP'
    assert v.get('p2_lv') is None and v['p2_name'] == 'Archwitch Fina'
    assert sorted(plugin.curves) == [1001, 1002, 1003]


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


def test_build_distinta_no_lee(attach):
    g = FakeGame(build={'timestamp': 0x12345678, 'image_size': 503013376})
    build_ffrs(g)
    plugin = attach(g)
    assert plugin.ue is None
    v = plugin.read(g.mem)
    assert 'Build distinta' in v['status']
    assert v['build'].endswith('(build distinta)')
    assert 'gil' not in v and 'p1_name' not in v


# --- HP/MP: actual de la unidad (+0x10C/+0x110), máximo del ViewModel ---

def test_en_batalla_hp_mp_y_orden(attach):
    g = build_ffrs(party=(1001, 1002), battle=[(1002, STATS[1002]), (1001, STATS[1001])])
    plugin = attach(g)
    v = plugin.read(g.mem)
    assert v['battle'] == 'en batalla (2)'
    assert v['p1_name'] == 'Lasswell' and v['p2_name'] == 'Rain'      # orden de batalla
    assert hp(v, 1) == (800, 1000, 40, 90)
    assert hp(v, 2) == (1200, 1500, 30, 60)
    assert v['p1_lv'] == 'Nv 10 · faltan 1.100 EXP'                  # la EXP sigue al ID
    assert v['hp_source'] == 'actual de la unidad + máximo de la interfaz (batalla)'
    assert v['dbg_hpmp'] == 'Lasswell HP 800/1000 MP 40/90 LB —/— · Rain HP 1200/1500 MP 30/60 LB —/—'


def test_hp_actual_en_vivo_aunque_la_interfaz_no_cambie(attach):
    g = build_ffrs(party=(1001,), battle=[(1001, STATS[1001])])
    plugin = attach(g)
    param = g.mem.ptr(g.mem.ptr(g.mem.ptr(next(o for o in g.objects
                                              if g.mem.u32(o + 0x18) == g.fname_index('CPP_BtlUnitManager_0')) + 0x28)) + 0x838)
    g.mem.put('i32', param + 0x10C, 777)                                # golpe en batalla
    assert hp(plugin.read(g.mem), 1) == (777, 1500, 30, 60)


def test_hp_mp_fuera_de_batalla(attach):
    g = build_ffrs(party=(1001, 1002), field=[(1001, STATS[1001]), (1002, STATS[1002])])
    v = attach(g).read(g.mem)
    assert v['battle'] == 'fuera de batalla'
    assert hp(v, 1) == (1200, 1500, 30, 60)
    assert hp(v, 2) == (800, 1000, 40, 90)
    assert v['hp_source'] == 'actual de la unidad + máximo de la interfaz (fuera de batalla)'


def test_sin_viewmodel_solo_actual(attach):
    g = build_ffrs(party=(1001,), field=[(1001, STATS[1001])], vms=[])
    v = attach(g).read(g.mem)
    assert hp(v, 1) == (1200, None, 30, None)
    assert v['hp_source'] == 'actual de la unidad (fuera de batalla)'


def test_sin_parametro_usa_la_interfaz(attach):
    g = build_ffrs(party=(1001,), vms=[(1001, STATS[1001])])
    assert hp(attach(g).read(g.mem), 1) == (1200, 1500, 30, 60)


def test_viewmodel_sin_nombres_esperados(attach, capsys):
    vm_props = [p for p in __import__('fake_ue').VM_PROPS if p[0] != 'MaxPoint']
    g = build_ffrs(party=(1001,), field=[(1001, STATS[1001])], vm_props=vm_props)
    v = attach(g).read(g.mem)
    assert hp(v, 1) == (1200, None, 30, None)                           # el actual sigue saliendo
    assert "no se pudo resolver el ViewModel por nombre: KeyError('MaxPoint')" in capsys.readouterr().out


def test_sin_reflexion_no_rompe_la_lectura(attach):
    # En el juego real la reflexión falló al principio y eso tumbaba TODA la lectura
    # (Gil congelado, "dirección inválida 0x0" en rojo). Ahora solo falta el máximo.
    g = build_ffrs(party=(1001, 1002), battle=[(1001, STATS[1001])], props=None, vm_props=None)
    v = attach(g).read(g.mem)
    assert v['status'] == 'Lectura OK' and v['gil'] == 12345
    assert v['battle'] == 'en batalla (1)'
    assert hp(v, 1) == (1200, None, 30, None)


def test_disposicion_de_reflexion_alternativa(attach):
    from fake_ue import U
    REFLECTION_LAYOUTS = U.REFLECTION_LAYOUTS
    for layout in REFLECTION_LAYOUTS:
        g = FakeGame(layout=layout)
        build_ffrs(g, party=(1001,), battle=[(1001, STATS[1001])])
        plugin = attach(g)
        assert hp(plugin.read(g.mem), 1) == (1200, 1500, 30, 60), layout
        assert plugin.ue.layout == layout


def test_valores_absurdos_no_se_muestran(attach):
    g = build_ffrs(party=(1001,), field=[(1001, {'hp': -5, 'mp': 30})], vms=[(1001, {'hp_max': 10**9, 'mp_max': 60})])
    assert hp(attach(g).read(g.mem), 1) == (None, None, 30, 60)
    g = build_ffrs(party=(1001,), field=[(1001, {'hp': 5, 'mp': 3})], vms=[(1001, {'hp_max': 0, 'mp_max': 0})])
    assert hp(attach(g).read(g.mem), 1) == (5, None, 3, None)          # máximo 0: aún sin datos


def test_fuera_de_batalla_id_duplicado_se_descarta(attach):
    g = build_ffrs(party=(1001, 1002),
                   field=[(1001, STATS[1001]), (1001, {'hp': 1}), (1002, STATS[1002])],
                   vms=[(1002, STATS[1002])])
    v = attach(g).read(g.mem)
    assert hp(v, 1) == (None,) * 4                    # dos objetos con 1001 y sin ViewModel
    assert hp(v, 2) == (800, 1000, 40, 90)


def test_viewmodel_duplicado_se_descarta(attach):
    g = build_ffrs(party=(1001,), field=[(1001, STATS[1001])], vms=[(1001, STATS[1001]), (1001, {'hp_max': 1})])
    assert hp(attach(g).read(g.mem), 1) == (1200, None, 30, None)


def test_batalla_tiene_prioridad(attach):
    g = build_ffrs(party=(1001,), field=[(1001, {'hp': 1, 'mp': 3})], battle=[(1001, STATS[1001])],
                   vms=[(1001, STATS[1001])])
    v = attach(g).read(g.mem)
    assert hp(v, 1) == (1200, 1500, 30, 60)


def test_objeto_destruido_y_reescaneo(attach):
    g = build_ffrs(party=(1001, 1002), field=[(1001, STATS[1001]), (1002, STATS[1002])], vms=[])
    plugin = attach(g)
    assert hp(plugin.read(g.mem), 1)[0] == 1200
    kill(g, g.field_params[0])                        # p. ej. cambio de mapa
    v = plugin.read(g.mem)
    assert hp(v, 1) == (None,) * 4                    # nunca un dato de un objeto muerto
    assert hp(v, 2)[0] == 800
    # El juego crea uno nuevo; aparece al reescanear (limitado en frecuencia)
    unit_parameter(g, 'CPP_UnitParameter', 1001, {'hp': 999}, outer=g.gi)
    plugin.next_param_scan = float('inf')
    assert plugin.read(g.mem).get('p1_hp') is None    # todavía dentro del límite
    plugin.next_param_scan = 0
    assert plugin.read(g.mem)['p1_hp'] == 999


def test_viewmodel_aparece_despues(attach):
    g = build_ffrs(party=(1001,), field=[(1001, STATS[1001])], vms=[])
    plugin = attach(g)
    assert hp(plugin.read(g.mem), 1)[1] is None
    viewmodel(g, 1001, STATS[1001])
    plugin.next_param_scan = 0
    assert hp(plugin.read(g.mem), 1) == (1200, 1500, 30, 60)


def test_id_cambiado_en_el_objeto(attach):
    g = build_ffrs(party=(1001,), field=[(1001, STATS[1001])], vms=[])
    plugin = attach(g)
    assert plugin.read(g.mem)['p1_hp'] == 1200
    g.mem.put('i32', g.field_params[0] + 0xD0, 1003)  # el objeto ahora es de otro personaje
    plugin.next_param_scan = float('inf')
    assert plugin.read(g.mem).get('p1_hp') is None


# --- retratos ---

def test_retratos_por_id_y_por_nombre(attach, data_home):
    folder = data_home / 'gamepad' / 'portraits' / 'ffrs'
    folder.mkdir(parents=True)
    (folder / '1001.webp').write_bytes(b'x')
    (folder / 'lasswell.png').write_bytes(b'x')
    (folder / 'dark_fina.png').write_bytes(b'x')
    g = build_ffrs(party=(1001, 1002, 1006, 1003))
    v = attach(g).read(g.mem)
    assert v['p1_img'] == '/portraits/ffrs/1001.webp'
    assert v['p2_img'] == '/portraits/ffrs/lasswell.png'
    assert v['p3_img'] == '/portraits/ffrs/dark_fina.png'
    assert v['p4_img'] is None                        # sin imagen: el cliente pone la inicial


# --- curvas de nivel y diagnóstico ---

def test_curvas_con_varias_tablas_del_mismo_tipo(attach):
    # Antes se usaba la primera tabla UNIT_PARAMETER: si era la de enemigos, no salía ningún nivel
    g = build_ffrs(party=(1001, 1002), enemy_table=True)
    v = attach(g).read(g.mem)
    assert v['p1_lv'] == 'Nv 5 · faltan 600 EXP'
    assert v['dbg_curves'] == '8/8 personajes; tablas UNIT_PARAMETER 2 (47 IDs)'


def test_curvas_se_reintentan(attach):
    from fake_ue import add_curves, level_table
    g = build_ffrs(party=(1001,), curve_for=())
    plugin = attach(g)
    v = plugin.read(g.mem)
    assert v.get('p1_lv') is None
    assert v['dbg_curves'].startswith('0/8 personajes; tablas UNIT_PARAMETER 1 (8 IDs); falta 1001: curva 10001 sin lista')
    add_curves(g, {10001: level_table(g)})            # la tabla aparece más tarde
    assert plugin.read(g.mem).get('p1_lv') is None    # todavía dentro del límite
    plugin.next_curve_try = 0
    v = plugin.read(g.mem)
    assert v['p1_lv'] == 'Nv 5 · faltan 600 EXP'
    assert v['dbg_curves'].startswith('1/8 personajes')


def test_sin_exp_en_la_partida(attach):
    g = build_ffrs(party=(1001, 1002), units={1001: 0})
    v = attach(g).read(g.mem)
    assert v.get('p2_lv') is None
    assert 'sin EXP en la partida para [1002]' in v['dbg_curves']


def test_diagnostico_de_batalla(attach):
    g = build_ffrs(party=(1001,))
    v = attach(g).read(g.mem)
    assert v['dbg_battle'] == 'sin CPP_BtlManager entre 1 subsistemas'
    g = build_ffrs(party=(1001,), battle=[(1001, STATS[1001])])
    v = attach(g).read(g.mem)
    assert v['dbg_battle'] == '1 unidades, 1 CPP_BtlUnit, 1 con parámetros, 1 aliados; IDs [1001]'


def test_diagnostico_gestor_de_unidades_nulo(attach, capsys):
    g = build_ffrs(party=(1001,), battle=[(1001, STATS[1001])])
    bm = next(o for o in g.objects if g.mem.u32(o + 0x18) == g.fname_index('CPP_BtlManager_0'))
    g.mem.put('u64', bm + 0x48, 0)
    v = attach(g).read(g.mem)
    assert v['dbg_battle'] == 'CPP_BtlManager +0x48 = nulo, no es CPP_BtlUnitManager'
    assert 'gestor de batalla' in capsys.readouterr().out


def test_censo_en_el_log(attach, capsys):
    g = build_ffrs(party=(1001,), field=[(1001, STATS[1001])])
    attach(g).read(g.mem)
    out = capsys.readouterr().out
    assert '       1  CPP_UnitParameter' in out
    assert '       1  UNIT_LEVEL_PARAMETER_LIST' in out and '       8  UNIT_LEVEL_PARAMETER' in out


def test_limit(attach):
    g = build_ffrs(party=(1001, 1002), battle=[(1001, dict(STATS[1001], lb=37, lb_max=100)),
                                              (1002, dict(STATS[1002], lb=150, lb_max=100))])
    v = attach(g).read(g.mem)
    assert (v['p1_lb'], v['p1_lb_max']) == (37, 100)
    assert 'p2_lb' not in v                           # actual > tope: no cuadra, no se muestra
