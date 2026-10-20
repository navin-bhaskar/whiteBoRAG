import json

from query.response import respond


def test_respond_has_cors_on_errors_too():
    out = respond(500, {"error": "boom"}, "http://localhost:8000")
    assert out["statusCode"] == 500
    assert out["headers"]["Access-Control-Allow-Origin"] == "http://localhost:8000"
    assert out["headers"]["Content-Type"] == "application/json"
    assert json.loads(out["body"]) == {"error": "boom"}
