"""Volumen del PC desde el cliente (botones de volumen del Android), sin root.

Usa la salida de audio por defecto del usuario: wpctl (PipeWire) o, si no está, pactl.
Los comandos y sus argumentos son fijos: del cliente solo llega la dirección (+1 / -1).
"""
import asyncio
import re
import shutil
import time

STEP = 5                 # % por pulsación
MIN_INTERVAL = 0.05      # s entre cambios (mantener pulsado repite muy rápido)
TIMEOUT = 2.0

_WPCTL_VOL = re.compile(r'Volume:\s*([0-9.]+)')
_PACTL_VOL = re.compile(r'(\d+)%')


class Volume:
    def __init__(self, which=shutil.which):
        self.tool = 'wpctl' if which('wpctl') else 'pactl' if which('pactl') else None
        self._last = 0.0

    def _commands(self, delta):
        sign = '+' if delta > 0 else '-'
        if self.tool == 'wpctl':
            return (['wpctl', 'set-volume', '-l', '1.0', '@DEFAULT_AUDIO_SINK@', f'{STEP}%{sign}'],
                    ['wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@'])
        return (['pactl', 'set-sink-volume', '@DEFAULT_SINK@', f'{sign}{STEP}%'],
                ['pactl', 'get-sink-volume', '@DEFAULT_SINK@'])

    @staticmethod
    async def _run(cmd):
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(f'{cmd[0]} no responde') from None
        if proc.returncode:
            raise RuntimeError(f'{cmd[0]}: {err.decode(errors="replace").strip() or proc.returncode}')
        return out.decode(errors='replace')

    def parse(self, text):
        """Porcentaje actual a partir de la salida de get-volume."""
        if self.tool == 'wpctl':
            m = _WPCTL_VOL.search(text)
            return round(float(m.group(1)) * 100) if m else None
        m = _PACTL_VOL.search(text)
        return int(m.group(1)) if m else None

    async def change(self, delta, now=None):
        """Sube (delta > 0) o baja el volumen un paso. Devuelve el mensaje para el cliente,
        o None si se ignora por ir demasiado rápido."""
        now = time.monotonic() if now is None else now
        if now - self._last < MIN_INTERVAL:
            return None
        self._last = now
        if self.tool is None:
            return {'t': 'vol', 'err': 'no hay wpctl ni pactl en el PC'}
        set_cmd, get_cmd = self._commands(delta)
        try:
            await self._run(set_cmd)
            return {'t': 'vol', 'v': self.parse(await self._run(get_cmd))}
        except (OSError, RuntimeError) as ex:
            return {'t': 'vol', 'err': str(ex)}
