"""Length-prefixed framing: headers, boundaries and malformed bodies.

Reference: MessengerServer/src/Network/Session.cpp lines 27-56 (header read,
1 MiB guard, body read) and 88-103 (response framing).
"""

from __future__ import annotations

import json
import struct
import time

import pytest

from shadowgram_client import HEADER, MAX_BODY

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


@pytest.mark.characterization
def test_zero_length_body_is_ignored_and_the_connection_survives(client, username):
    """An empty body fails JSON parsing; the server logs and reads on."""
    client.send_frame(b"")

    client.assert_silent(within=1.0)
    assert client.request(_register_payload(username))["status"] == "ok"


@pytest.mark.characterization
@pytest.mark.parametrize(
    "body",
    [
        pytest.param(b"{not json", id="broken-object"),
        pytest.param(b"[1, 2, 3]", id="array-instead-of-object"),
        pytest.param(b"null", id="json-null"),
        pytest.param(b"\xff\xfe\x00", id="not-utf8"),
    ],
)
def test_malformed_body_is_dropped_without_any_reply(connect, body):
    client = connect()
    client.send_frame(body)

    client.assert_silent(within=1.0)


@pytest.mark.xfail(
    reason="F-04: malformed input produces no reply at all, so a client cannot "
           "tell a rejected request from a slow one",
)
def test_malformed_body_should_be_answered_with_an_error_frame(client):
    client.send_frame(b"{not json")

    response = client.read_json()
    assert response["status"] == "error"


def test_client_may_half_close_and_still_read_the_response(client, username):
    client.send_json(_register_payload(username))
    client.half_close()

    assert client.read_json()["status"] == "ok"
