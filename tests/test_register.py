"""The `register` action.

Reference: MessengerServer/src/Network/Session.cpp lines 105-135 (wire
handling), src/Services/AuthService.cpp lines 17-97 (logic),
src/Repositories/PostgresUserRepository.cpp lines 24-67 (INSERT).
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.usefixtures("server")

TOO_LONG_USERNAME = 51 * "u"   # users.username is VARCHAR(50)
TOO_LONG_FIRST_NAME = 101 * "f"  # users.first_name is VARCHAR(100)


def test_register_returns_ok_and_a_user_id(register):
    _, response = register()

    assert response["type"] == "register_response"
    assert response["status"] == "ok"
    assert uuid.UUID(response["user_id"])  # parses as a real uuid


@pytest.mark.db
def test_registered_user_is_persisted_with_the_returned_id(register, db):
    name, response = register()

    row = db.execute(
        "SELECT user_id, first_name, settings, is_deleted FROM users WHERE username = %s",
        (name,),
    ).fetchone()
    assert row is not None, "register replied ok but no row reached the database"
    assert str(row[0]) == response["user_id"]
    assert row[1] == "Test"
    assert row[2] == {}
    assert row[3] is False


def test_duplicate_username_is_rejected(register):
    name, first = register()
    assert first["status"] == "ok"

    _, second = register(name=name)

    assert second["status"] == "error"
    assert second["message"] == "Username already taken"
    assert "user_id" not in second


@pytest.mark.db
def test_duplicate_registration_does_not_create_a_second_row(register, db):
    name, _ = register()
    register(name=name)

    count = db.execute("SELECT count(*) FROM users WHERE username = %s", (name,)).fetchone()[0]
    assert count == 1


def test_username_of_maximum_length_is_accepted(register, username):
    name = (username + 50 * "u")[:50]  # exactly the VARCHAR(50) limit

    _, response = register(name=name)

    assert response["status"] == "ok"


@pytest.mark.characterization
def test_over_long_username_surfaces_as_a_generic_database_error(register):
    """No length validation exists; the constraint violation leaks out as-is."""
    _, response = register(name=TOO_LONG_USERNAME)

    assert response["status"] == "error"
    assert response["message"] == "Failed to save user to database."


@pytest.mark.characterization
def test_over_long_first_name_surfaces_as_a_generic_database_error(register):
    _, response = register(first_name=TOO_LONG_FIRST_NAME)

    assert response["status"] == "error"
    assert response["message"] == "Failed to save user to database."


@pytest.mark.xfail(
    reason="F-06: input is never validated, so a too-long username is reported "
           "as an internal database failure instead of a field error",
)
def test_over_long_username_should_be_reported_as_a_validation_error(register):
    _, response = register(name=TOO_LONG_USERNAME)

    assert response["status"] == "error"
    assert response["message"] != "Failed to save user to database."


@pytest.mark.characterization
def test_empty_username_is_accepted(client):
    """The empty string is a legal username; only the first caller gets it."""
    response = client.request(
        {"type": "register", "username": "", "password": "pw", "first_name": "x"}
    )

    assert response["status"] == "ok" or response["message"] == "Username already taken"


@pytest.mark.characterization
def test_request_without_username_or_password_registers_the_empty_user(client):
    """Missing fields default to "" (json .value()), they are not an error."""
    response = client.request({"type": "register"})

    assert response["status"] == "ok" or response["message"] == "Username already taken"


@pytest.mark.xfail(
    reason="F-06: an empty username is stored instead of being rejected",
)
def test_empty_username_should_be_rejected(client):
    response = client.request(
        {"type": "register", "username": "", "password": "pw", "first_name": "x"}
    )

    assert response["status"] == "error"
    # Once the empty user exists, uniqueness rejects the second attempt; that is
    # not the validation error this test is about.
    assert response["message"] != "Username already taken"


@pytest.mark.characterization
def test_empty_password_is_accepted(register):
    _, response = register(password="")

    assert response["status"] == "ok"


@pytest.mark.xfail(
    reason="F-06: an empty password is hashed and stored instead of being rejected",
)
def test_empty_password_should_be_rejected(register):
    _, response = register(password="")

    assert response["status"] == "error"


@pytest.mark.characterization
def test_non_string_username_gets_no_response_at_all(client):
    """json .value() throws type_error, which is swallowed by the catch block."""
    client.send_json(
        {"type": "register", "username": 12345, "password": "pw", "first_name": "x"}
    )

    client.assert_silent(within=1.5)


@pytest.mark.xfail(
    reason="F-04: a wrongly typed field silently drops the request instead of "
           "producing an error response",
)
def test_non_string_username_should_be_answered_with_an_error(client):
    client.send_json(
        {"type": "register", "username": 12345, "password": "pw", "first_name": "x"}
    )

    assert client.read_json()["status"] == "error"


def test_connection_still_works_after_a_wrongly_typed_request(client, register):
    client.send_json({"type": "register", "username": [], "password": "pw"})

    _, response = register()
    assert response["status"] == "ok"


@pytest.mark.db
def test_username_is_stored_literally_and_sql_is_not_interpreted(client, db, username):
    payload_name = username + "'); DROP TABLE users;--"

    response = client.request(
        {"type": "register", "username": payload_name, "password": "pw", "first_name": "x"}
    )

    assert response["status"] == "ok"
    stored = db.execute(
        "SELECT username FROM users WHERE user_id = %s", (response["user_id"],)
    ).fetchone()[0]
    assert stored == payload_name
    # the table is obviously still there if the query above worked, but be explicit
    assert db.execute("SELECT to_regclass('public.users')").fetchone()[0] == "users"


@pytest.mark.db
def test_non_ascii_username_and_first_name_survive_the_round_trip(client, db, username):
    name = username + "_Ярослав"

    response = client.request(
        {"type": "register", "username": name, "password": "пароль", "first_name": "Ярослав"}
    )

    assert response["status"] == "ok"
    row = db.execute(
        "SELECT username, first_name FROM users WHERE user_id = %s", (response["user_id"],)
    ).fetchone()
    assert row == (name, "Ярослав")


@pytest.mark.db
@pytest.mark.characterization
def test_nul_byte_truncates_the_username(client, db, username):
    """std::string -> libpq passes a C string, so everything after \\0 is lost."""
    response = client.request(
        {
            "type": "register",
            "username": username + "\x00ignored-tail",
            "password": "pw",
            "first_name": "x",
        }
    )

    assert response["status"] == "ok"
    stored = db.execute(
        "SELECT username FROM users WHERE user_id = %s", (response["user_id"],)
    ).fetchone()[0]
    assert stored == username


@pytest.mark.xfail(
    reason="F-08: a NUL byte truncates the value instead of being rejected, so "
           "'name\\0anything' and 'name' are the same account name",
)
def test_username_with_a_nul_byte_should_be_rejected(client, username):
    response = client.request(
        {"type": "register", "username": username + "\x00tail", "password": "pw", "first_name": "x"}
    )

    assert response["status"] == "error"


@pytest.mark.characterization
def test_usernames_differing_only_in_case_are_two_accounts(client, username):
    upper = username.upper()

    first = client.request(
        {"type": "register", "username": upper, "password": "pw", "first_name": "x"}
    )
    second = client.request(
        {"type": "register", "username": upper.lower(), "password": "pw", "first_name": "x"}
    )

    assert first["status"] == "ok"
    assert second["status"] == "ok"
    assert first["user_id"] != second["user_id"]
