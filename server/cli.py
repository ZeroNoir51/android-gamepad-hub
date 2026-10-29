"""Punto de entrada: `ps5gamepad serve` (servicio) y `ps5gamepad run %command%` (lanzador)."""
import sys
from pathlib import Path

USAGE = '''Uso:
  ps5gamepad serve [opciones]     servicio permanente: mando, telemetría y web (sin root)
  ps5gamepad run %command%        opción de lanzamiento de Steam: lanza el juego y lee sus datos
'''


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # plugins importan server.*
    args = sys.argv[1:]
    if not args or args[0] in ('-h', '--help'):
        print(USAGE)
        return 0
    if args[0] == 'serve':
        from .main import main as serve   # importa aiohttp/evdev solo aquí
        return serve(args[1:])
    if args[0] == 'run':
        from .launcher import main as run  # solo biblioteca estándar
        return run(args[1:])
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main())
