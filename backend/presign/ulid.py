"""Minimal ULID generator (https://github.com/ulid/spec), stdlib only."""

import os
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def encode(ts_ms: int, rand: bytes) -> str:
    """Encode a 48-bit millisecond timestamp and 80 random bits as 26 chars."""
    if not 0 <= ts_ms < 2**48:
        raise ValueError("timestamp out of range")
    if len(rand) != 10:
        raise ValueError("rand must be 10 bytes")
    value = (ts_ms << 80) | int.from_bytes(rand, "big")
    chars = []
    for _ in range(26):
        chars.append(_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def new_ulid(ts_ms: int | None = None) -> str:
    if ts_ms is None:
        ts_ms = time.time_ns() // 1_000_000
    return encode(ts_ms, os.urandom(10))
