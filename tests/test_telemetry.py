"""Log de MangoHud: lectura de frames y silencio al cerrar el juego."""
from server import telemetry


def test_sin_aviso_al_cerrar_el_juego_y_suelta_el_log(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(telemetry.time, 'monotonic', lambda: clock[0])
    log = tmp_path / 'sora_2nd_2026-10-30_12-00-00.csv'
    log.write_text('os,cpu\nLinux,Zen2\nfps,frametime,cpu_load\n60,16.6,10\n60,16.7,10\n')
    tail = telemetry.MangoHudTail(tmp_path)
    out = tail.poll()
    assert out['fps'] and out['ftNew'] == [16.6, 16.7] and out['mh'].startswith('ok')
    clock[0] += 10                                   # el juego se cerró: no llegan filas
    out = tail.poll()
    assert out['fps'] is None and out['mh'] == ''
    log.unlink()                                     # el lanzador borra el log
    clock[0] += 2
    assert tail.poll()['mh'] == '' and tail.fh is None


def test_sin_logs_no_es_un_error(tmp_path):
    assert telemetry.MangoHudTail(tmp_path).poll()['mh'] == ''
