"""EXP total por nivel, con la fórmula del propio juego (solo lectura).

La función "EXP que falta" del juego (script "Selected Character" de la tabla) llama a
la de EXP total de un nivel. Su código (volcado de la 1.03.1, exe+0xF9B30) hace:

    nivel = min(nivel, tope)            ; tope 200 (175 para algunos personajes)
    lea  eax, [rbx+ADD]   ; imul eax, ebx ; imul ebx, eax, MUL    -> base = MUL*N*(N+ADD)
    movss xmm2, [personaje+0xE8]  o, si no hay dato, [rip+disp]   -> multiplicador
    total = base + trunc(float(base)*mult - float(base))          (en float32)

ADD, MUL y el multiplicador por defecto se leen del código; si un parche los cambia, se
siguen. La función de "siguiente nivel" devuelve total(nivel+1) - EXP actual.
"""
import re
import struct

from server.plugin_api import MemoryReadError

FUNC_SIZE = 0x100
BASE_RE = re.compile(rb'\x8D\x43(.)\x0F\xAF\xC3\x6B\xD8(.)', re.DOTALL)   # lea/imul/imul
DEFAULT_RE = re.compile(rb'\xF3\x0F\x10\x15(....)', re.DOTALL)            # movss xmm2,[rip+disp]
CAP = 200


def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


class Curve:
    def __init__(self, add, mul, mult=1.0, cap=CAP):
        self.add, self.mul, self.mult, self.cap = add, mul, mult, cap

    def total(self, level):
        """EXP acumulada necesaria para tener `level` (como el juego, en float32)."""
        n = min(level, self.cap)
        base = self.mul * n * (n + self.add)
        b = f32(float(base))
        return base + int(f32(f32(b * self.mult) - b))

    def next(self, level, exp):
        """EXP que falta para el siguiente nivel; 0 en el tope."""
        if level >= self.cap:
            return 0
        return max(0, self.total(level + 1) - exp)

    def near(self, level, exp, slack=0.15):
        """¿Cuadra la EXP con el nivel, admitiendo multiplicadores propios de hasta ±15 %?"""
        if level >= self.cap:
            return exp >= self.total(self.cap) * (1 - slack)
        if level == 1 and exp < self.total(2):
            return True
        return self.total(level) * (1 - slack) <= exp < self.total(level + 1) * (1 + slack)

    def consistent(self, level, exp):
        return level >= self.cap or self.total(level) <= exp < self.total(level + 1)


def from_code(mem, func):
    """Curve leída del código de la función de EXP total, o MemoryReadError si no cuadra."""
    code = mem.read(func, FUNC_SIZE)
    m = BASE_RE.search(code)
    if not m:
        raise MemoryReadError('fórmula de EXP no reconocida (¿otra versión del juego?)')
    add, mul = struct.unpack('<bb', m.group(1) + m.group(2))
    mult = 1.0
    d = DEFAULT_RE.search(code)
    if d:
        mult = mem.f32(func + d.end() + struct.unpack('<i', d.group(1))[0])
        if not 0.1 <= mult <= 10:
            raise MemoryReadError(f'multiplicador de EXP extraño ({mult})')
    return Curve(add, mul, mult)
