"""Connection lifetime, unsupported actions and concurrency.

Reference: MessengerServer/src/Network/Session.cpp (the request loop) and
src/Network/Server.cpp lines 25-37 (accept loop).
"""

from __future__ import annotations

import time
import uuid

import pytest

pytestmark = pytest.mark.usefixtures("server")


def _register_payload(username: str) -> dict:
    return {
        "type": "register",
        "username": username,
        "password": "correct horse",
        "first_name": "Test",
    }


def test_one_connection_handles_many_sequential_requests(client, make_username):
    ids = set()

    for _ in range(5):
        response = client.request(_register_payload(make_username()))
        assert response["status"] == "ok"
        ids.add(response["user_id"])

    assert len(ids) == 5


@pytest.mark.characterization
@pytest.mark.parametrize(
    "action",
    [
        pytest.param("login", id="login"),
        pytest.param("logout", id="logout"),
        pytest.param("get_messages", id="get_messages"),
        pytest.param("create_chat", id="create_chat"),
        pytest.param("", id="empty-type"),
        pytest.param(None, id="no-type-field"),
    ],
)
def test_unsupported_action_is_answered_with_silence(connect, action, username):
    """Only `register` and `send_message` exist; everything else falls through
    the if/else chain and the loop simply waits for the next frame."""
    client = connect()
    payload = {"username": username, "password": "pw"}
    if action is not None:
        payload["type"] = action

    client.send_json(payload)

    client.assert_silent(within=1.5)


@pytest.mark.xfail(
    reason="F-02: there is no `login` action on the wire; AuthService::LoginUser "
           "is never reachable from a client",
)
def test_login_is_supported(client, register):
    name, registration = register(password="s3cret")
    assert registration["status"] == "ok"

    response = client.request({"type": "login", "username": name, "password": "s3cret"})

    assert response["status"] == "ok"


@pytest.mark.xfail(
    reason="F-04: an unknown action is ignored instead of being reported",
)
def test_unknown_action_should_be_answered_with_an_error(client):
    response = client.request({"type": "definitely_not_an_action"})

    assert response["status"] == "error"


def test_connection_survives_corrupt_json_between_valid_requests(client, make_username):
    assert client.request(_register_payload(make_username()))["status"] == "ok"

    client.send_frame(b"{ this is not json")

    assert client.request(_register_payload(make_username()))["status"] == "ok"


def test_connection_survives_a_zero_length_frame_between_valid_requests(client, make_username):
    client.send_frame(b"")

    assert client.request(_register_payload(make_username()))["status"] == "ok"


def test_many_connections_are_served_at_the_same_time(connect, make_username):
    clients = [connect(timeout=30.0) for _ in range(10)]

    for client in clients:
        client.send_json(_register_payload(make_username()))

    assert [client.read_json()["status"] for client in clients] == ["ok"] * 10


def test_a_second_connection_is_accepted_while_the_first_stays_open(connect, make_username):
    first = connect()
    assert first.request(_register_payload(make_username()))["status"] == "ok"

    second = connect()
    assert second.request(_register_payload(make_username()))["status"] == "ok"

    # the first one is still usable afterwards
    assert first.request(_register_payload(make_username()))["status"] == "ok"


def test_a_client_that_disconnects_does_not_disturb_the_others(connect, make_username):
    survivor = connect()
    doomed = connect()
    doomed.send_json({"type": "send_message", "chat_id": str(uuid.uuid4()), "content": "x"})
    doomed.close()

    assert survivor.request(_register_payload(make_username()))["status"] == "ok"


@pytest.mark.slow
@pytest.mark.characterization
def test_an_idle_connection_is_never_timed_out(client, username):
    """Session.cpp mentions a read timeout for Slowloris protection, but none is
    installed: a silent connection is kept forever."""
    time.sleep(5)

    assert client.request(_register_payload(username))["status"] == "ok"


@pytest.mark.slow
@pytest.mark.characterization
def test_a_connection_that_announces_a_body_and_never_sends_it_is_kept_open(client):
    client.send_raw(b"\x00\x00\x10\x00")  # promises 4096 bytes
    client.send_raw(b"{")

    client.assert_silent(within=5.0)


@pytest.mark.slow
@pytest.mark.xfail(
    reason="F-10: no read timeout exists, so a connection that stalls mid-frame "
           "holds a session (and a database backend) indefinitely",
)
def test_a_stalled_connection_should_eventually_be_dropped(client):
    client.send_raw(b"\x00\x00\x10\x00")
    client.send_raw(b"{")

    client.assert_closed(within=5.0)
