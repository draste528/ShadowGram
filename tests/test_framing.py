"""Length-prefixed framing: headers, boundaries and malformed bodies.

Reference: MessengerServer/src/Network/Session.cpp lines 27-56 (header read,
1 MiB guard, body read) and 88-103 (response framing).
"""

from __future__ import annotations

import json
import struct
import time

import pytest

from shadowgram_client import HEADER, MAX_BODY, assert_error_frame

pytestmark = pytest.mark.usefixtures("server")


def _register_payload(username: str) -> dict:
    return {
        "type": "register",
        "username": username,
        "password": "correct horse",
        "first_name": "Test",
    }


def test_response_header_is_big_endian_and_matches_body(client, username):
    client.send_json(_register_payload(username))

    raw_header = client.read_exactly(4)
    body = client.read_exactly(HEADER.unpack(raw_header)[0])

    assert HEADER.unpack(raw_header)[0] == len(body)
    # A little-endian reading of the same header would be absurdly large, which
    # is what pins the byte order.
    assert struct.unpack("<I", raw_header)[0] > MAX_BODY
    assert json.loads(body)["type"] == "register_response"


def test_two_requests_in_one_tcp_write_get_two_responses(client, make_username):
    first = json.dumps(_register_payload(make_username())).encode()
    second = json.dumps(_register_payload(make_username())).encode()

    client.send_raw(HEADER.pack(len(first)) + first + HEADER.pack(len(second)) + second)

    assert client.read_json()["status"] == "ok"
    assert client.read_json()["status"] == "ok"


def test_request_split_across_several_tcp_writes(client, username):
    body = json.dumps(_register_payload(username)).encode()

    client.send_raw(HEADER.pack(len(body))[:2])
    time.sleep(0.05)
    client.send_raw(HEADER.pack(len(body))[2:])
    time.sleep(0.05)
    client.send_raw(body[:10])
    time.sleep(0.05)
    client.send_raw(body[10:])

    assert client.read_json()["status"] == "ok"


def test_body_of_exactly_one_mebibyte_is_accepted(connect, username):
    """1 MiB is the documented limit and must still be processed."""
    client = connect(timeout=20.0)
    payload = _register_payload(username)
    payload["pad"] = ""
    body = json.dumps(payload).encode()
    assert len(body) < MAX_BODY
    body = body[:-1] + b" " * (MAX_BODY - len(body)) + b"}"
    assert len(body) == MAX_BODY

    client.send_frame(body)

    assert client.read_json()["status"] == "ok"


def test_body_larger_than_one_mebibyte_closes_the_connection(client):
    """The header alone is enough: the server never reads the body."""
    client.send_frame(b"", declared_len=MAX_BODY + 1)

    client.assert_closed()


def test_oversized_frame_drops_a_previously_healthy_connection(client, username):
    assert client.request(_register_payload(username))["status"] == "ok"

    client.send_frame(b"", declared_len=MAX_BODY + 1)

    client.assert_closed()


def test_zero_length_body_is_rejected_and_the_connection_survives(client, username):
    """An empty body fails JSON parsing, which is now reported rather than
    swallowed; the connection stays usable afterwards."""
    client.send_frame(b"")

    assert_error_frame(client.read_json(), "invalid_json")
    assert client.request(_register_payload(username))["status"] == "ok"


@pytest.mark.parametrize(
    "body, code",
    [
        pytest.param(b"{not json", "invalid_json", id="broken-object"),
        pytest.param(b"[1, 2, 3]", "invalid_request", id="array-instead-of-object"),
        pytest.param(b"null", "invalid_request", id="json-null"),
        pytest.param(b'"a string"', "invalid_request", id="json-string"),
        pytest.param(b"42", "invalid_request", id="json-number"),
        pytest.param(b"\xff\xfe\x00", "invalid_json", id="not-utf8"),
    ],
)
def test_malformed_body_is_answered_with_an_error_frame(connect, body, code):
    """Replaces the pair that pinned F-04 from both sides: the characterization
    test asserting silence and the xfail asserting an error.  Both scenarios are
    the same request, so they collapse into this one, which additionally pins
    which code each kind of malformed body produces."""
    client = connect()
    client.send_frame(body)

    assert_error_frame(client.read_json(), code)


def test_client_may_half_close_and_still_read_the_response(client, username):
    client.send_json(_register_payload(username))
    client.half_close()

    assert client.read_json()["status"] == "ok"
