"""Lector UE5 (server/ue.py) contra la memoria sintética."""
import pytest

from fake_ue import BASE, RF_BEGIN_DESTROYED, RF_CLASS_DEFAULT, RVA, FakeGame, build_ffrs
from server.memory import MemoryReadError
from server.ue import UEReader, pe_info


def reader(game):
    return UEReader(game.mem, BASE, **RVA)


def test_pe_info():
    g = FakeGame()
    assert pe_info(g.mem, BASE) == {'timestamp': 0x6A586B2F, 'image_size': 503013376}


def test_nombres_y_numero():
    g = FakeGame()
    obj = g.obj('Thing', 'Object')
    g.write_fname(obj + 0x18, 'Thing', number=3)
    ue = reader(g)
    assert ue.name(0) == 'None'
    assert ue.object_name(obj) == 'Thing_2'
    assert ue.class_name(obj) == 'Object'


def test_tabla_de_nombres_incorrecta():
    g = FakeGame()
    g.mem.put('u16', g.name_block, len('Nope') << 6)
    g.mem.write(g.name_block + 2, b'Nope')
    with pytest.raises(MemoryReadError):
        reader(g)


def test_live_descarta_cdo_destruidos_y_no_registrados():
    g = FakeGame()
    ok = g.obj('A', 'Object')
    cdo = g.obj('Default__A', 'Object', flags=RF_CLASS_DEFAULT)
    dead = g.obj('B', 'Object', flags=RF_BEGIN_DESTROYED)
    ghost = g.obj('C', 'Object', registered=False)
    ue = reader(g)
    assert ue.live(ok)
    assert not ue.live(cdo)
    assert ue.live(cdo, allow_default=True)
    assert not ue.live(dead)
    assert not ue.live(ghost)
    assert not ue.live(0)


def test_scan_e_isa():
    g = FakeGame()
    g.cls('Child', 'Parent')
    a = g.obj('a', 'Child')
    g.obj('Default__Child', 'Child', flags=RF_CLASS_DEFAULT)
    b = g.obj('b', 'Parent')
    ue = reader(g)
    found = ue.scan({'Child', 'Parent', 'Missing'})
    assert found == {'Child': [a], 'Parent': [b], 'Missing': []}
    assert ue.isa(a, 'Parent') and ue.isa(a, 'Child')
    assert not ue.isa(b, 'Child')


def test_sparse_entries_respeta_huecos():
    g = FakeGame()
    holder = g.alloc(0x40)
    entries = g.sparse(holder, ['x', 'y', 'z'], holes=(1,))
    assert reader(g).sparse_entries(holder, 24) == [e for e, _ in entries]


def test_sparse_entries_bits_en_heap():
    g = FakeGame()
    holder = g.alloc(0x40)
    entries = g.sparse(holder, list(range(200)), holes=(0, 150))
    assert reader(g).sparse_entries(holder, 24, 4096) == [e for e, _ in entries]


def test_table_rows_y_struct_cambiado():
    g = FakeGame()
    t = g.data_table('UNIT_PARAMETER', [('U1', {8: ('i32', 1001)})])
    ue = reader(g)
    rows = ue.table_rows(t, 'UNIT_PARAMETER')
    assert [k for k, _ in rows] == ['U1'] and g.mem.i32(rows[0][1] + 8) == 1001
    with pytest.raises(MemoryReadError):
        ue.table_rows(t, 'OTRA_COSA')


def test_world_comprueba_clase():
    assert reader(build_ffrs()).world()
    with pytest.raises(MemoryReadError, match='no a un World'):
        reader(build_ffrs(world_class='GameInstance')).world()


def test_properties_recorre_herencia():
    g = build_ffrs()
    ue = reader(g)
    props = ue.properties(g.cls('CPP_BtlUnitParameter'))
    assert ('m_pOwnerBtlUnit', 'ObjectProperty', 0x360, 'CPP_BtlUnitParameter') in props
    assert ('UnitName', 'TextProperty', 0x288, 'CPP_UnitParameter') in props   # heredada
