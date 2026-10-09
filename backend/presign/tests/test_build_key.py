from datetime import datetime, timedelta, timezone

import pytest

from handler import build_key

CID = "01JA2B3C4D5E6F7G8H9J0K1M2N"


def test_key_layout():
    now = datetime(2026, 10, 8, 13, 34, 54, 999000, tzinfo=timezone.utc)
    assert build_key("captures/", "wb-cam-01", now, CID) == (
        f"captures/wb-cam-01/2026/10/08/20261008T133454Z_{CID}.jpg"
    )


def test_non_utc_input_is_converted():
    ist = timezone(timedelta(hours=5, minutes=30))
    now = datetime(2026, 10, 9, 2, 0, 0, tzinfo=ist)  # = 2026-10-08 20:30:00Z
    assert build_key("captures/", "d", now, CID) == (
        f"captures/d/2026/10/08/20261008T203000Z_{CID}.jpg"
    )


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        build_key("captures/", "d", datetime(2026, 1, 1), CID)
