"""Shared fixtures for the ShadowGram integration test suite.

The suite talks to a *running* MessengerServer over TCP; nothing in the C++
project is compiled, linked or mocked here.  Configuration comes from the
environment (see tests/README.md):

    SHADOWGRAM_HOST         default 127.0.0.1
    SHADOWGRAM_PORT         default 54321 (hardcoded in src/main.cpp)
    SHADOWGRAM_TEST_DSN     libpq DSN of the database the server is using.
                            Tests marked ``db`` are skipped when it is unset.
    SHADOWGRAM_SERVER_EXE   optional: start this executable if the port is closed
    SHADOWGRAM_SERVER_CWD   optional: working directory for that executable
                            (the server reads ./config.json from its cwd)
    SHADOWGRAM_SERVER_CONFIG optional: path to the config.json the server uses
    SHADOWGRAM_CLEANUP      set to 1 to delete rows created by the tests
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from shadowgram_client import Client

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 54321

#: Every username the suite creates starts with this, which keeps the optional
#: cleanup step from ever touching rows it did not create.
USERNAME_PREFIX = "sgtest_"


# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def sg_host() -> str:
    return os.environ.get("SHADOWGRAM_HOST", DEFAULT_HOST)


@pytest.fixture(scope="session")
def sg_port() -> int:
    return int(os.environ.get("SHADOWGRAM_PORT", DEFAULT_PORT))


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def server(sg_host, sg_port):
    """Make sure a server is listening, optionally starting one.

    A server started by the suite is stopped again at the end of the session;
    a server that was already running is left alone.
    """
    if _port_open(sg_host, sg_port):
        yield (sg_host, sg_port)
        return

    exe = os.environ.get("SHADOWGRAM_SERVER_EXE")
    if not exe:
        pytest.skip(
            f"no ShadowGram server on {sg_host}:{sg_port}; start one or set "
            "SHADOWGRAM_SERVER_EXE"
        )

    cwd = os.environ.get("SHADOWGRAM_SERVER_CWD") or str(Path(exe).parent)
    proc = subprocess.Popen(
        [exe],
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            pytest.fail(f"server exited immediately with code {proc.returncode}")
        if _port_open(sg_host, sg_port):
            break
        time.sleep(0.2)
    else:
        proc.terminate()
        pytest.fail(f"server did not start listening on {sg_host}:{sg_port}")

    try:
        yield (sg_host, sg_port)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="session")
def server_config(server) -> dict:
    """Contents of the server's config.json, when its path was provided."""
    path = os.environ.get("SHADOWGRAM_SERVER_CONFIG")
    if not path:
        pytest.skip("SHADOWGRAM_SERVER_CONFIG is not set")
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# network clients
# --------------------------------------------------------------------------
@pytest.fixture
def connect(server):
    """Factory that opens tracked connections, all closed after the test."""
    host, port = server
    opened: list[Client] = []

    def _connect(timeout: float = 5.0) -> Client:
        client = Client(host, port, timeout).connect()
        opened.append(client)
        return client

    yield _connect

    for client in opened:
        client.close()


@pytest.fixture
def client(connect) -> Client:
    """A single connected client, the common case."""
    return connect()


# --------------------------------------------------------------------------
# database access (optional)
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def dsn() -> str:
    value = os.environ.get("SHADOWGRAM_TEST_DSN")
    if not value:
        pytest.skip("SHADOWGRAM_TEST_DSN is not set")
    return value


@pytest.fixture(scope="session")
def db(dsn):
    """Autocommit psycopg connection to the database the server writes to."""
    psycopg = pytest.importorskip("psycopg", reason="pip install 'psycopg[binary]'")
    conn = psycopg.connect(dsn, autocommit=True)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="session", autouse=True)
def _cleanup(request):
    """Optionally remove rows created by the suite (opt-in, off by default)."""
    yield
    if os.environ.get("SHADOWGRAM_CLEANUP") != "1":
        return
    dsn_value = os.environ.get("SHADOWGRAM_TEST_DSN")
    if not dsn_value:
        return
    try:
        import psycopg
    except ImportError:
        return
    with psycopg.connect(dsn_value, autocommit=True) as conn:
        conn.execute(
            "DELETE FROM messages WHERE chat_id IN "
            "(SELECT chat_id FROM chats WHERE chat_name LIKE %s)",
            (USERNAME_PREFIX + "%",),
        )
        conn.execute("DELETE FROM chats WHERE chat_name LIKE %s", (USERNAME_PREFIX + "%",))
        conn.execute("DELETE FROM users WHERE username LIKE %s", (USERNAME_PREFIX + "%",))


# --------------------------------------------------------------------------
# data helpers
# --------------------------------------------------------------------------
@pytest.fixture
def username() -> str:
    """A fresh username that cannot collide with earlier runs."""
    return USERNAME_PREFIX + uuid.uuid4().hex[:12]


@pytest.fixture
def make_username():
    """Factory version of :func:`username` for tests that need several."""

    def _make(suffix: str = "") -> str:
        return USERNAME_PREFIX + uuid.uuid4().hex[:12] + suffix

    return _make


@pytest.fixture
def register(client, username):
    """Register one user on the shared client and return (username, response)."""

    def _register(name: str | None = None, password: str = "correct horse", **extra):
        payload = {
            "type": "register",
            "username": username if name is None else name,
            "password": password,
            "first_name": "Test",
        }
        payload.update(extra)
        return payload["username"], client.request(payload)

    return _register


@pytest.fixture
def account(connect, make_username):
    """Factory creating a real account, returning (username, password, user_id).

    Registration runs on its own connection because `register` does not
    authenticate anything (see docs/FINDINGS.md, F-02): a caller that wants an
    identity has to send `login`, which is exactly what these tests exercise.
    """

    def _make(password: str = "correct horse") -> tuple[str, str, str]:
        name = make_username()
        registrar = connect()
        response = registrar.request(
            {
                "type": "register",
                "username": name,
                "password": password,
                "first_name": "Test",
            }
        )
        assert response["status"] == "ok", f"could not create the account: {response}"
        return name, password, response["user_id"]

    return _make


@pytest.fixture
def existing_chat(db):
    """Insert a chat row directly and return its uuid.

    The server has no 'create chat' action, so a chat can only be produced by
    writing to the database (see docs/FINDINGS.md, F-16).
    """
    chat_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO chats (chat_id, type, chat_name) VALUES (%s, 'group', %s)",
        (chat_id, USERNAME_PREFIX + "chat"),
    )
    return chat_id
