"""What actually ends up in users.password_hash.

Reference: MessengerServer/src/Services/AuthService.cpp lines 33-61.
"""

from __future__ import annotations

import base64

import pytest

pytestmark = [pytest.mark.usefixtures("server"), pytest.mark.db]

PASSWORD = "correct horse battery staple"
#: The salt is a literal in AuthService.cpp line 41, shared by every account.
HARDCODED_SALT = b"stoletnyaya_salt"


def _hash_of(db, user_id: str) -> str:
    return db.execute(
        "SELECT password_hash FROM users WHERE user_id = %s", (user_id,)
    ).fetchone()[0]


def test_password_is_not_stored_in_clear_text(register, db):
    _, response = register(password=PASSWORD)

    stored = _hash_of(db, response["user_id"])
    assert PASSWORD not in stored


def test_hash_is_an_argon2id_encoding_with_the_configured_cost(register, db):
    _, response = register(password=PASSWORD)

    stored = _hash_of(db, response["user_id"])
    assert stored.startswith("$argon2id$v=19$m=65536,t=2,p=1$")


def test_a_long_password_is_still_hashed_successfully(register, db):
    """The encoded hash goes into a fixed 128-byte buffer; input length must not
    reach it, since the encoding only grows with the cost parameters."""
    _, response = register(password="P" * 4096)

    assert response["status"] == "ok"
    assert _hash_of(db, response["user_id"]).startswith("$argon2id$")


@pytest.mark.characterization
def test_every_account_shares_one_hardcoded_salt(register, db, make_username):
    expected = base64.b64encode(HARDCODED_SALT).decode().rstrip("=")

    _, first = register(name=make_username("a"), password="password-one")
    _, second = register(name=make_username("b"), password="password-two")

    salts = {_hash_of(db, first["user_id"]).split("$")[4],
             _hash_of(db, second["user_id"]).split("$")[4]}
    assert salts == {expected}


@pytest.mark.characterization
def test_two_users_with_the_same_password_get_identical_hashes(register, db, make_username):
    _, first = register(name=make_username("a"), password=PASSWORD)
    _, second = register(name=make_username("b"), password=PASSWORD)

    assert _hash_of(db, first["user_id"]) == _hash_of(db, second["user_id"])


@pytest.mark.xfail(
    reason="F-05: the salt is a hardcoded constant, so equal passwords hash to "
           "equal digests and one precomputation breaks every account",
)
def test_two_users_with_the_same_password_should_get_different_hashes(
    register, db, make_username
):
    _, first = register(name=make_username("a"), password=PASSWORD)
    _, second = register(name=make_username("b"), password=PASSWORD)

    assert _hash_of(db, first["user_id"]) != _hash_of(db, second["user_id"])
