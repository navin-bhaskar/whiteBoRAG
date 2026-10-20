"""API Gateway proxy responses. Every one carries the CORS header, errors included, so the page can read them."""

import json


def respond(status: int, body: dict, origin: str) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": origin,
        },
        "body": json.dumps(body),
    }
