import pytest

from fakes import InMemoryStore
from ingest.board import Todo
from ingest.events import parse_key
from ingest.pipeline import apply_todos, remove_sightings
from ingest.store import Conflict

P = "whiteborag"
A = parse_key("captures/wb-cam-01/2026/10/15/20261015T070000Z_01M4Z7KFZ5KHCYV4BWHM8RH7BA.jpg")
B = parse_key("captures/wb-cam-01/2026/10/16/20261016T080000Z_01M4Z7KFZ5KHCYV4BWHM8RH7BB.jpg")
IR_OPEN = [Todo("Finalize IR sensor", False)]
IR_DONE = [Todo("Finalize IR sensor", True)]


def test_first_board_creates_todos():
    store = InMemoryStore()
    board = [Todo("Test terraform code", True), Todo("Deploy lambda", True), Todo("Finalize IR sensor", False)]
    ids = apply_todos(store, P, A, board)
    items = {t.todo_id: t for t in store.list_todos(P)}
    assert len(ids) == 3 and set(ids) == set(items)
    assert all(list(t.sightings) == [A.capture_id] for t in items.values())
    assert [items[i].text for i in ids] == [t.text for t in board]


def test_ticked_later_same_todo():
    store = InMemoryStore()
    apply_todos(store, P, A, IR_OPEN)
    apply_todos(store, P, B, IR_DONE)
    [item] = store.list_todos(P)
    assert item.state == "done"
    assert item.completed_on == B.date


def test_backfill_order_irrelevant():
    store = InMemoryStore()
    apply_todos(store, P, B, IR_DONE)
    apply_todos(store, P, A, IR_OPEN)
    [item] = store.list_todos(P)
    assert item.state == "done"
    assert item.completed_on == B.date


def test_reapply_same_capture_idempotent():
    store = InMemoryStore()
    first = apply_todos(store, P, A, IR_OPEN)
    assert apply_todos(store, P, A, IR_OPEN) == first
    [item] = store.list_todos(P)
    assert list(item.sightings) == [A.capture_id]


def test_remove_sightings_deletes_empty():
    store = InMemoryStore()
    [only] = apply_todos(store, P, A, IR_OPEN)
    remove_sightings(store, P, A.capture_id, [only])
    assert store.list_todos(P) == []

    apply_todos(store, P, A, IR_OPEN)
    [shared] = apply_todos(store, P, B, IR_DONE)
    remove_sightings(store, P, B.capture_id, [shared])
    [item] = store.list_todos(P)
    assert list(item.sightings) == [A.capture_id]
    assert item.state == "open"
    assert item.completed_on is None


def test_conflict_retried():
    store = InMemoryStore()
    apply_todos(store, P, A, IR_OPEN)
    store.fail_next_save_todo = True
    apply_todos(store, P, B, IR_DONE)
    [item] = store.list_todos(P)
    assert set(item.sightings) == {A.capture_id, B.capture_id}
    assert item.state == "done"


def test_delete_todo_loses_to_concurrent_sighting():
    store = InMemoryStore()
    [todo_id] = apply_todos(store, P, A, IR_OPEN)
    [stale] = store.list_todos(P)
    apply_todos(store, P, B, IR_DONE)
    with pytest.raises(Conflict):
        store.delete_todo(P, todo_id, stale.version)
    assert len(store.list_todos(P)) == 1
