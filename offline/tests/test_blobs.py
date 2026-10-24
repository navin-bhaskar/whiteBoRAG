import pytest

from whiteborag_offline.blobs import FileBlobs

KEY = "captures/cam-01/2026/10/24/20261024T100000Z_01M4Z7KFZ5KHCYV4BWHM8RH7BF.jpg"
REST = "cam-01/2026/10/24/20261024T100000Z_01M4Z7KFZ5KHCYV4BWHM8RH7BF.jpg"


def test_capture_key_lands_in_uploads(tmp_path):
    blobs = FileBlobs(tmp_path)
    blobs.put_bytes(KEY, b"\xff\xd8jpeg")
    assert (tmp_path / "uploads" / REST).read_bytes() == b"\xff\xd8jpeg"
    assert blobs.get_bytes(KEY) == b"\xff\xd8jpeg"
    assert blobs.path_for(KEY) == tmp_path / "uploads" / REST


def test_other_keys_land_in_derived(tmp_path):
    blobs = FileBlobs(tmp_path)
    blobs.put_text("transcripts/cam-01/x.md", "# Board")
    assert (tmp_path / "derived" / "transcripts" / "cam-01" / "x.md").read_text(encoding="utf-8") == "# Board"
    assert blobs.get_text("transcripts/cam-01/x.md") == "# Board"


def test_delete_capture_moves_to_rejected(tmp_path):
    blobs = FileBlobs(tmp_path)
    blobs.put_bytes(KEY, b"\xff\xd8jpeg")
    blobs.delete(KEY)
    assert blobs.get_bytes(KEY) is None
    assert (tmp_path / "rejected" / REST).read_bytes() == b"\xff\xd8jpeg"


def test_delete_transcript_unlinks(tmp_path):
    blobs = FileBlobs(tmp_path)
    blobs.put_text("transcripts/x.md", "text")
    blobs.delete("transcripts/x.md")
    assert blobs.get_text("transcripts/x.md") is None
    assert not (tmp_path / "rejected").exists()


def test_missing_returns_none_and_delete_is_noop(tmp_path):
    blobs = FileBlobs(tmp_path)
    assert blobs.get_bytes(KEY) is None
    assert blobs.get_text("transcripts/none.md") is None
    blobs.delete(KEY)
    blobs.delete("transcripts/none.md")


@pytest.mark.parametrize("key", ["../escape.txt", "/abs/path", "captures/../../x.jpg", "transcripts/a\\..\\..\\b"])
def test_rejects_path_traversal(tmp_path, key):
    with pytest.raises(ValueError):
        FileBlobs(tmp_path).path_for(key)
