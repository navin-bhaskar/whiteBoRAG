from whiteborag_offline.jobs import JobQueue
from whiteborag_offline.requeue import main

KEY = "captures/cam-01/2026/10/15/20261015T084632Z_01M4Z7KFZ5KHCYV4BWHM8RH7BF.jpg"


def test_requeue_keys_and_failed(tmp_path, capsys):
    db = tmp_path / "wb.db"
    q = JobQueue(db)
    q.fail(q.enqueue("captures/old.jpg"), "down")
    assert main(["--failed", KEY], db) == 0
    assert [(j["s3_key"], j["status"]) for j in q.recent()] == [(KEY, "queued"), ("captures/old.jpg", "queued")]
    assert "1 failed job" in capsys.readouterr().out


def test_requeue_rejects_a_non_capture_key(tmp_path):
    assert main(["transcripts/x.md"], tmp_path / "wb.db") == 2
    assert JobQueue(tmp_path / "wb.db").recent() == []
