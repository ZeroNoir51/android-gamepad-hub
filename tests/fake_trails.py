"""Memoria sintética de Trails in the Sky 2nd Chapter (sora_2nd.exe).

Imagen PE con las firmas de la tabla sora_2nd-v2.CT, el puntero global al bloque de estado
(Mira/sepith/tiempo de juego) y el código y la cadena de punteros de la Brave Gauge.
"""
import struct

from server.memory import LinuxProcessMemory, MemoryReadError, ProcInfo

MODULE = 'sora_2nd.exe'
BASE = 0x140000000
TEXT_RVA, TEXT_SIZE = 0x1000, 0x40000
DATA_RVA = 0x50000
GLOBAL = BASE + DATA_RVA + 0x10        # puntero al bloque de estado
HEAP = 0x20000000
BLOCK_SIZE = 0x700000
PLAYTIME = 0x20B650


class FakeMemory(LinuxProcessMemory):
    def __init__(self, pid=5151):
        self.pid = pid
        self.ptr_size = 8
        self._fd = None
        self._modules = {MODULE: BASE}
        self.regions = []
        self.alive_flag = True

    def map(self, start, size):
        buf = bytearray(size)
        self.regions.append((start, buf))
        return buf

    def _region(self, addr, size):
        for start, buf in self.regions:
            if start <= addr and addr + size <= start + len(buf):
                return start, buf
        raise MemoryReadError(f'no mapeado 0x{addr:x}+{size}')

    def read(self, addr, size):
        start, buf = self._region(addr, size)
        return bytes(buf[addr - start:addr - start + size])

    def write(self, addr, data):
        start, buf = self._region(addr, len(data))
        buf[addr - start:addr - start + len(data)] = data

    def put(self, kind, addr, value):
        self.write(addr, struct.pack('<' + self._FMT[kind], value))

    def alive(self):
        return self.alive_flag

    def close(self):
        pass


def state_insn(at):
    """mov rax,[rip+disp] ... con la forma de la firma "Mira + Sepith and Play time"."""
    disp = GLOBAL - (at + 7)
    return (b'\x48\x8B\x05' + struct.pack('<i', disp) + b'\x0F\xB6\x05' + bytes(4)
            + b'\x48\x8B\x0D' + bytes(4) + b'\x48\x8B\x4C\x24' + b'\xF3')


def playtime_insn(off):
    """addsd xmm0,[rbx+off]; movsd [rbx+off],xmm0; xorps xmm0,xmm0; F3..."""
    return (b'\xF2\x0F\x58\x83' + struct.pack('<I', off) + b'\xF2\x0F\x11\x83'
            + struct.pack('<I', off) + b'\x0F\x57\xC0\xF3')


class FakeTrails:
    def __init__(self, playtime_off=PLAYTIME, state_sig=True, playtime_sig=True, block=True):
        self.mem = FakeMemory()
        self.playtime_off = playtime_off
        self._pe()
        text = BASE + TEXT_RVA
        if state_sig:
            self.mem.write(text + 0x1234, state_insn(text + 0x1234))
        if playtime_sig:
            self.mem.write(text + 0x3000, playtime_insn(playtime_off))
        self.block = None
        if block:
            self.new_block(HEAP)

    def _pe(self):
        m = self.mem
        m.map(BASE, 0x1000)
        m.write(BASE, b'MZ')
        m.put('u32', BASE + 0x3C, 0x80)
        nt = BASE + 0x80
        m.write(nt, b'PE\0\0')
        m.put('u16', nt + 6, 2)                    # NumberOfSections
        m.put('u16', nt + 0x14, 0xF0)              # SizeOfOptionalHeader
        m.put('u32', nt + 0x08, 0x68A1B2C3)        # TimeDateStamp
        m.put('u32', nt + 0x50, 0x60000)           # SizeOfImage
        table = nt + 0x18 + 0xF0
        for i, (name, rva, size, flags) in enumerate([(b'.text', TEXT_RVA, TEXT_SIZE, 0x60000020),
                                                      (b'.data', DATA_RVA, 0x1000, 0xC0000040)]):
            m.write(table + i * 40, name.ljust(8, b'\0'))
            m.put('u32', table + i * 40 + 8, size)
            m.put('u32', table + i * 40 + 12, rva)
            m.put('u32', table + i * 40 + 36, flags)
        m.map(BASE + TEXT_RVA, TEXT_SIZE)
        m.map(BASE + DATA_RVA, 0x1000)

    def new_block(self, addr):
        """El juego (re)crea su bloque de estado en addr (vacío, como en la pantalla de título)."""
        self.mem.map(addr, BLOCK_SIZE)
        self.block = addr
        self.mem.put('u64', GLOBAL, addr)

    def money(self, mira, sepith, playtime):
        b = self.block + self.playtime_off
        for i, n in enumerate(sepith):
            self.mem.put('u32', b - 0x28 + i * 4, n)
        self.mem.put('u32', b - 8, mira)
        self.mem.put('f64', b, playtime)

    def brave(self, value, flags=0, code=True):
        """Brave Gauge: el código de la firma "max Brave Rush on hit" y su cadena de punteros
        [[[exe+G1]+0x2C50]+0x260]+0x48; tope según byte [[exe+G2]+0x10D] (bit 4: 700, 2: 600)."""
        m = self.mem
        heap = 0x31000000
        if not any(start == heap for start, _ in m.regions):
            m.map(heap, 0x4000)
        g1, g2 = BASE + DATA_RVA + 0x300, BASE + DATA_RVA + 0x308
        obj, rcx, rdx, flg = heap, heap + 0x1000, heap + 0x2000, heap + 0x3000
        m.put('u64', g1, obj), m.put('u64', obj + 0x2C50, rcx), m.put('u64', rcx + 0x260, rdx)
        m.put('u32', rdx + 0x48, value)
        m.put('u64', g2, flg), m.put('u8', flg + 0x10D, flags)
        if code:
            at = BASE + TEXT_RVA + 0x7000
            m.write(at, b'\x48\x8B\x05' + struct.pack('<i', g1 - (at + 7))
                    + b'\x48\x8B\x88' + struct.pack('<I', 0x2C50)
                    + b'\x48\x8B\x05' + struct.pack('<i', g2 - (at + 21))
                    + b'\x48\x8B\x91' + struct.pack('<I', 0x260)
                    + b'\x44\x0F\xB6\x80' + struct.pack('<I', 0x10D)
                    + b'\x44\x8B\x4A\x48' + b'\x41\x8D\x0C\x19')

    def proc(self):
        return ProcInfo(self.mem.pid, MODULE, MODULE, f'Z:\\game\\{MODULE}')
