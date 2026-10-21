"""Pair codes (SPEC 6): 6 characters, no look-alikes (0/O, 1/I), case-insensitive, expire after the TTL."""

from __future__ import annotations

import secrets
from collections.abc import Callable

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
LENGTH = 6


class PairCodeExpired(Exception):
    pass


class PairingRegistry:
    def __init__(self, ttl_ms: float, clock: Callable[[], float]) -> None:
        self._ttl_ms = ttl_ms
        self._clock = clock
        self._codes: dict[str, tuple[str, float]] = {}  # code -> (session id, expires at)

    def issue(self, session_id: str) -> str:
        self._sweep()
        while True:
            code = "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
            if code not in self._codes:
                self._codes[code] = (session_id, self._clock() + self._ttl_ms)
                return code

    def resolve(self, code: str) -> str:
        """Session id for a code. KeyError when unknown, PairCodeExpired after the TTL."""
        session_id, expires = self._codes[code.strip().upper()]
        if self._clock() > expires:
            raise PairCodeExpired(code)
        return session_id

    def _sweep(self) -> None:
        """Forget codes long past their TTL, so an expired code stays a 410 for a while and then a 404."""
        cutoff = self._clock() - 6 * self._ttl_ms
        self._codes = {c: v for c, v in self._codes.items() if v[1] > cutoff}
