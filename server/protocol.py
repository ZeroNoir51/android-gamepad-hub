"""Validación del estado del mando que envía el cliente (sin dependencias)."""

BUTTONS = ('a', 'b', 'x', 'y', 'lb', 'rb', 'back', 'start', 'guide', 'ls', 'rs')
ANALOG = ('lx', 'ly', 'rx', 'ry')
TRIGGERS = ('lt', 'rt')
DPAD = ('dx', 'dy')
ALL_KEYS = frozenset(BUTTONS + ANALOG + TRIGGERS + DPAD)


def neutral():
    return dict.fromkeys(ALL_KEYS, 0)


def _clamp(v, lo, hi):
    return max(lo, min(hi, int(v)))


def parse_input(data):
    """Devuelve un estado completo y saneado, o lanza ValueError."""
    if not isinstance(data, dict):
        raise ValueError('input state must be an object')
    unknown = set(data) - ALL_KEYS
    if unknown:
        raise ValueError(f'unknown keys: {sorted(unknown)}')
    state = neutral()
    for key, raw in data.items():
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or raw != raw:
            raise ValueError(f'invalid value for {key}')
        if key in BUTTONS:
            state[key] = int(raw != 0)
        elif key in ANALOG:
            state[key] = _clamp(raw, -32768, 32767)
        elif key in TRIGGERS:
            state[key] = _clamp(raw, 0, 255)
        else:
            state[key] = _clamp(raw, -1, 1)
    return state
