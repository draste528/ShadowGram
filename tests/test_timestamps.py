"""created_at / last_seen as they arrive in PostgreSQL.

Reference: MessengerServer/src/Utils/TimeUtils.cpp lines 9-18 (formats UTC
without any offset) and src/Repositories/PostgresUserRepository.cpp lines 32-50
(binds that string to a TIMESTAMP WITH TIME ZONE column).
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.usefixtures("server"), pytest.mark.db]


def _utc_offset_seconds(db) -> float:
    """UTC offset of the session PostgreSQL uses to interpret naive strings."""
    return float(db.execute("SELECT EXTRACT(TIMEZONE FROM now())").fetchone()[0])


def _drift_seconds(db, user_id: str) -> float:
    row = db.execute(
        "SELECT EXTRACT(EPOCH FROM (now() - created_at)) FROM users WHERE user_id = %s",
        (user_id,),
    ).fetchone()
    return float(row[0])


def test_created_at_and_last_seen_are_both_written(register, db):
    _, response = register()

    row = db.execute(
        "SELECT created_at, last_seen FROM users WHERE user_id = %s", (response["user_id"],)
    ).fetchone()
    assert row[0] is not None and row[1] is not None
    assert abs((row[1] - row[0]).total_seconds()) < 5


@pytest.mark.characterization
def test_created_at_is_shifted_by_the_database_utc_offset(register, db):
    """The server sends UTC wall-clock text with no offset, so PostgreSQL reads
    it as local time and the stored instant is wrong by exactly the offset."""
    offset = _utc_offset_seconds(db)
    if offset == 0:
        pytest.skip("database session runs in UTC, the bug is not observable here")

    _, response = register()

    assert abs(_drift_seconds(db, response["user_id"]) - offset) < 10


@pytest.mark.xfail(
    reason="F-07: naive UTC text is stored into TIMESTAMPTZ, so created_at is "
           "off by the database session's UTC offset",
    strict=False,  # a UTC database hides the defect and the test passes
)
def test_created_at_should_be_the_current_time(register, db):
    _, response = register()

    assert abs(_drift_seconds(db, response["user_id"])) < 10
