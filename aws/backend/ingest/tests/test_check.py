from ingest.check import unusable_reason


def test_unusable_with_reason():
    assert unusable_reason("UNUSABLE: finger covers part of the board") == "finger covers part of the board"
    assert unusable_reason("`UNUSABLE: too blurry`\n") == "too blurry"
    assert unusable_reason("unusable - no whiteboard in the photo") == "no whiteboard in the photo"
    assert unusable_reason("UNUSABLE") == ""


def test_anything_else_counts_as_usable():
    assert unusable_reason("USABLE") is None
    assert unusable_reason("USABLE: all lines fully visible") is None
    assert unusable_reason("The photo is not UNUSABLE") is None
    assert unusable_reason("") is None
    assert unusable_reason(None) is None
