import re

import pytest

from ulid import encode, new_ulid

CROCKFORD = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def test_encode_zero():
    assert encode(0, bytes(10)) == "0" * 26


def test_encode_spec_timestamp():
    # Example from the ULID spec: 1469918176385 -> 01ARYZ6S41
    assert encode(1469918176385, bytes(10))[:10] == "01ARYZ6S41"


def test_encode_max_random():
    assert encode(0, b"\xff" * 10)[10:] == "Z" * 16


def test_encode_rejects_bad_input():
    with pytest.raises(ValueError):
        encode(0, bytes(9))
    with pytest.raises(ValueError):
        encode(-1, bytes(10))
    with pytest.raises(ValueError):
        encode(2**48, bytes(10))


def test_new_ulid_format():
    assert CROCKFORD.match(new_ulid())


def test_new_ulid_is_unique():
    assert len({new_ulid(1000) for _ in range(100)}) == 100


def test_new_ulid_orders_by_time():
    earlier = new_ulid(1_700_000_000_000)
    later = new_ulid(1_700_000_000_001)
    assert earlier < later
