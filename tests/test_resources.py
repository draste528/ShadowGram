"""How server resources scale with the number of clients.

Reference: MessengerServer/src/Network/Session.cpp lines 23-25 - every accepted
socket opens its own `pqxx::connection`, before the client has sent anything.
"""

from __future__ import annotations

import time

import pytest

pytestmark = [pytest.mark.usefixtures("server"), pytest.mark.db]

CLIENTS = 8


def _backends(db) -> int:
    return db.execute(
        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
    ).fetchone()[0]


@pytest.mark.characterization
def test_each_idle_client_socket_holds_its_own_database_backend(connect, db):
    """No pooling: connecting is enough to consume a PostgreSQL backend, so
    max_connections is the real limit on concurrent clients."""
    before = _backends(db)

    clients = [connect() for _ in range(CLIENTS)]
    time.sleep(1.0)
    during = _backends(db)

    for client in clients:
        client.close()
    time.sleep(1.0)
    after = _backends(db)

    assert during - before == CLIENTS
    assert after <= before + 1  # released again on disconnect


@pytest.mark.characterization
def test_the_database_connection_is_opened_before_any_request_is_sent(connect, db):
    before = _backends(db)

    connect()
    time.sleep(1.0)

    assert _backends(db) == before + 1
