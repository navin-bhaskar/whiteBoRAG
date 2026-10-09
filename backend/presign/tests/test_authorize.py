from handler import authorize

KEYS = {"key-1": "wb-cam-01", "key-2": "wb-cam-02"}


def ev(key_id):
    return {"requestContext": {"identity": {"apiKeyId": key_id}}}


def test_matching_key():
    assert authorize(ev("key-1"), "wb-cam-01", KEYS)


def test_key_for_other_device():
    assert not authorize(ev("key-2"), "wb-cam-01", KEYS)


def test_unknown_key():
    assert not authorize(ev("key-9"), "wb-cam-01", KEYS)


def test_null_key():
    assert not authorize(ev(None), "wb-cam-01", KEYS)


def test_missing_request_context():
    assert not authorize({}, "wb-cam-01", KEYS)
    assert not authorize({"requestContext": {}}, "wb-cam-01", KEYS)
    assert not authorize({"requestContext": {"identity": None}}, "wb-cam-01", KEYS)
