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
        # `login` used to belong here; it is a real action since F-02.
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


def test_login_is_supported(client, register):
    name, registration = register(password="s3cret")
    assert registration["status"] == "ok"

    response = client.request({"type": "login", "username": name, "password": "s3cret"})

    assert response["status"] == "ok"


def test_login_returns_the_id_of_the_account_that_was_registered(client, account):
    name, password, user_id = account()

    response = client.request({"type": "login", "username": name, "password": password})

    assert response["type"] == "login_response"
    assert response["status"] == "ok"
    assert response["user_id"] == user_id


@pytest.mark.parametrize(
    "scenario",
    [
        pytest.param("wrong-password", id="wrong-password"),
        pytest.param("unknown-user", id="unknown-user"),
    ],
)
def test_login_is_refused_without_valid_credentials(client, account, make_username, scenario):
    """Both refusals carry the same message, so login cannot be used to find out
    which usernames exist (`register` still can — see F-17)."""
    name, password, _ = account()
    if scenario == "wrong-password":
        username, attempt = name, password + "-wrong"
    else:
        username, attempt = make_username(), password

    response = client.request({"type": "login", "username": username, "password": attempt})

    assert response["type"] == "login_response"
    assert response["status"] == "error"
    assert response["message"] == "Invalid username or password"
    assert "user_id" not in response


def test_logging_in_twice_on_one_connection_rebinds_the_identity(client, account):
    first_name, first_password, _ = account()
    second_name, second_password, second_id = account()

    first = client.request(
        {"type": "login", "username": first_name, "password": first_password}
    )
    second = client.request(
        {"type": "login", "username": second_name, "password": second_password}
    )

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert second["user_id"] == second_id


def test_logging_in_as_the_same_user_twice_is_accepted(client, account):
    name, password, user_id = account()

    first = client.request({"type": "login", "username": name, "password": password})
    second = client.request({"type": "login", "username": name, "password": password})

    assert [first["status"], second["status"]] == ["ok", "ok"]
    assert first["user_id"] == second["user_id"] == user_id


def test_registering_does_not_log_the_connection_in(client, make_username):
    """`register` creates the account and nothing else; the caller still has to
    send `login` to get an identity on the connection."""
    name = make_username()
    registration = client.request(
        {"type": "register", "username": name, "password": "pw", "first_name": "Test"}
    )

    assert registration["status"] == "ok"
    assert registration["type"] == "register_response"
    # a register_response carries no session state, only the created id
    assert set(registration) == {"type", "status", "user_id"}


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
