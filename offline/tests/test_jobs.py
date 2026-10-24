from whiteborag_offline.jobs import JobQueue


def test_fifo_claim_finish_fail(tmp_path):
    q = JobQueue(tmp_path / "wb.db")
    a, b = q.enqueue("k1"), q.enqueue("k2")
    assert q.claim() == (a, "k1")
    assert q.claim() == (b, "k2")
    assert q.claim() is None
    q.finish(a, {"status": "ingested"})
    q.fail(b, "LlmError('down')")
    by_id = {j["id"]: j for j in q.recent()}
    assert by_id[a]["status"] == "done"
    assert by_id[a]["outcome"] == {"status": "ingested"}
    assert (by_id[b]["status"], by_id[b]["error"]) == ("failed", "LlmError('down')")


def test_recent_newest_first(tmp_path):
    q = JobQueue(tmp_path / "wb.db")
    q.enqueue("k1")
    q.enqueue("k2")
    assert [j["s3_key"] for j in q.recent()] == ["k2", "k1"]


def test_requeue_running(tmp_path):
    q = JobQueue(tmp_path / "wb.db")
    job_id = q.enqueue("k1")
    q.claim()
    assert q.requeue_running() == 1
    assert q.claim() == (job_id, "k1")
