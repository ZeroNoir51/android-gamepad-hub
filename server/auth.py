"""Token de arranque + sesiones por cookie (24 h) que sobreviven a reinicios."""
import hashlib
import json
import os
import secrets
import time

COOKIE = 'ps5gp_session'
SESSION_TTL = 24 * 3600


class AuthGuard:
    """Comprueba el token de 4 letras y bloquea una IP tras varios fallos."""

    def __init__(self, token, max_failures=5, block_seconds=60):
        self.token = token
        self.max_failures = max_failures
        self.block_seconds = block_seconds
        self.failures = {}   # ip -> (fallos, bloqueado_hasta)

    def check(self, ip, given):
        count, until = self.failures.get(ip, (0, 0.0))
        now = time.monotonic()
        if until > now:
            return 'blocked'
        if secrets.compare_digest(given.upper().encode(), self.token.encode()):
            self.failures.pop(ip, None)
            return 'ok'
        count += 1
        until = now + self.block_seconds if count >= self.max_failures else 0.0
        self.failures[ip] = (0 if until else count, until)
        return 'bad'


class SessionStore:
    """Guarda solo el hash SHA-256 de cada sesión, con su caducidad (tiempo Unix)."""

    def __init__(self, path):
        self.path = path
        self.sessions = {}
        try:
            with open(path) as f:
                self.sessions = {k: float(v) for k, v in json.load(f).items()}
        except (OSError, ValueError):
            pass
        self._purge()

    @staticmethod
    def _h(sid):
        return hashlib.sha256(sid.encode()).hexdigest()

    def _purge(self):
        now = time.time()
        self.sessions = {k: v for k, v in self.sessions.items() if v > now}

    def _save(self):
        tmp = f'{self.path}.tmp'
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(self.sessions, f)
        os.replace(tmp, self.path)

    def create(self):
        self._purge()
        sid = secrets.token_urlsafe(32)
        self.sessions[self._h(sid)] = time.time() + SESSION_TTL
        self._save()
        return sid

    def valid(self, sid):
        if not sid:
            return False
        exp = self.sessions.get(self._h(sid))
        return exp is not None and exp > time.time()

    def revoke(self, sid):
        if sid and self.sessions.pop(self._h(sid), None) is not None:
            self._save()
