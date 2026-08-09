"""The `send_message` action.

Reference: MessengerServer/src/Network/Session.cpp lines 57-104 and
src/Repositories/PostgresMessageRepository.cpp lines 50-93.

Every message the server accepts is rejected by PostgreSQL, because the
sender_id it inserts is a UUID invented for the connection which never exists in
`users` (docs/FINDINGS.md, F-01/F-02).  The tests below pin that reality and,
next to it, state what the action is supposed to do.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.usefixtures("server")


def _send(chat_id: str, content: str = "hello world", **extra) -> dict:
    payload = {"type": "send_message", "chat_id": chat_id, "content": content, "nonce": "n0nce"}
    payload.update(extra)
    return payload


@pytest.mark.characterization
def test_send_message_to_an_unknown_chat_answers_error(client):
    response = client.request(_send(str(uuid.uuid4())))

    assert response["type"] == "response"
    assert response["status"] == "error"


@pytest.mark.db
@pytest.mark.characterization
def test_send_message_to_an_existing_chat_also_answers_error(client, existing_chat):
    response = client.request(_send(existing_chat))

    assert response["status"] == "error"


@pytest.mark.db
@pytest.mark.characterization
def test_nothing_is_written_to_the_messages_table(client, db, existing_chat):
    before = db.execute("SELECT count(*) FROM messages").fetchone()[0]

    assert client.request(_send(existing_chat))["status"] == "error"

    after = db.execute("SELECT count(*) FROM messages").fetchone()[0]
    assert after == before


@pytest.mark.characterization
def test_error_response_still_carries_a_message_id_that_exists_nowhere(client):
    response = client.request(_send(str(uuid.uuid4())))

    assert response["status"] == "error"
    assert uuid.UUID(response["message_id"])


@pytest.mark.db
@pytest.mark.xfail(
    reason="F-01: sender_id is a per-connection random UUID that is not a real "
           "user, so the INSERT always violates messages_sender_id_fkey",
)
def test_message_should_be_persisted(client, db, existing_chat):
    response = client.request(_send(existing_chat, content="persist me"))

    assert response["status"] == "ok"
    row = db.execute(
        "SELECT chat_id, content FROM messages WHERE message_id = %s",
        (response["message_id"],),
    ).fetchone()
    assert row is not None
    assert str(row[0]) == existing_chat
    assert bytes(row[1]) == b"persist me"


@pytest.mark.db
@pytest.mark.xfail(
    reason="F-02: the connection has no identity; registering on it does not "
           "make the caller the sender of its messages",
)
def test_registering_first_should_make_that_user_the_sender(client, db, register, existing_chat):
    _, registration = register()
    assert registration["status"] == "ok"

    response = client.request(_send(existing_chat, content="from a real user"))

    assert response["status"] == "ok"
    sender = db.execute(
        "SELECT sender_id FROM messages WHERE message_id = %s", (response["message_id"],)
    ).fetchone()[0]
    assert str(sender) == registration["user_id"]


@pytest.mark.db
@pytest.mark.characterization
def test_registering_on_the_connection_changes_nothing_about_sending(
    client, register, existing_chat
):
    """Same scenario as above, stated as it behaves today."""
    _, registration = register()
    assert registration["status"] == "ok"

    assert client.request(_send(existing_chat))["status"] == "error"


def test_message_ids_are_unique_per_request(client):
    chat_id = str(uuid.uuid4())

    first = client.request(_send(chat_id, content="a"))
    second = client.request(_send(chat_id, content="b"))

    assert first["message_id"] != second["message_id"]


@pytest.mark.characterization
@pytest.mark.parametrize(
    "chat_id",
    [
        pytest.param("not-a-uuid", id="garbage"),
        pytest.param("", id="empty"),
        pytest.param("123e4567-e89b-12d3-a456", id="truncated-uuid"),
    ],
)
def test_unparseable_chat_id_gets_no_response(connect, chat_id):
    client = connect()
    client.send_json(_send(chat_id))

    client.assert_silent(within=1.5)


@pytest.mark.characterization
def test_missing_chat_id_gets_no_response(client):
    client.send_json({"type": "send_message", "content": "hi"})

    client.assert_silent(within=1.5)


@pytest.mark.xfail(
    reason="F-04: an unparseable chat_id is skipped with `continue`, leaving the "
           "client waiting for a reply that never comes",
)
def test_unparseable_chat_id_should_be_answered_with_an_error(client):
    response = client.request(_send("not-a-uuid"))

    assert response["status"] == "error"


@pytest.mark.characterization
def test_wrongly_typed_content_gets_no_response(client):
    client.send_json(_send(str(uuid.uuid4()), content=42))

    client.assert_silent(within=1.5)


@pytest.mark.db
@pytest.mark.xfail(
    reason="F-03: chat membership is a TODO in Session.cpp, so any connection "
           "may post into any chat id",
)
def test_posting_into_a_chat_you_are_not_a_member_of_should_be_refused(client, existing_chat):
    response = client.request(_send(existing_chat))

    assert response["status"] == "error"
    assert "member" in response.get("message", "").lower()


def test_connection_survives_a_rejected_message(client, register):
    assert client.request(_send(str(uuid.uuid4())))["status"] == "error"

    _, response = register()
    assert response["status"] == "ok"
