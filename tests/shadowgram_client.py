"""Minimal wire-protocol client for the ShadowGram server.

Framing (as implemented in MessengerServer/src/Network/Session.cpp):

    +----------------------------+-------------------------+
    | uint32 big-endian body_len | body_len bytes of JSON  |
    +----------------------------+-------------------------+

The same framing is used in both directions.  There is no request id and no
correlation field, so responses are matched to requests purely by order.
"""

from __future__ import annotations

import json
import socket
import struct

HEADER = struct.Struct(">I")

#: Bodies larger than this are rejected by the server, which closes the socket.
MAX_BODY = 1024 * 1024


class ProtocolError(AssertionError):
    """Raised when the peer does not follow the length-prefixed framing."""


def assert_error_frame(response: dict, code: str | None = None) -> dict:
    """Assert ``response`` is the server's rejection frame, optionally its code.

    Since F-04 every rejected request is answered with exactly one of these
    instead of silence.  ``code`` is the stable part a client may branch on;
    ``message`` is prose for a human and is not asserted anywhere.
    """
    assert response["type"] == "error_response", response
    assert response["status"] == "error", response
    assert "code" in response, response
    if code is not None:
        assert response["code"] == code, response
    return response


class Client:
    """A single TCP connection to the server.

    Used as a context manager so that sockets are always released even when a
    test fails mid-way.
    """

    def __init__(self, host: str, port: int, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None

    # -- lifecycle ---------------------------------------------------------
    def connect(self) -> "Client":
        self._sock = socket.create_connection((self.host, self.port), self.timeout)
        self._sock.settimeout(self.timeout)
        return self

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def __enter__(self) -> "Client":
        return self.connect()

    def __exit__(self, *exc_info) -> None:
        self.close()

    @property
    def sock(self) -> socket.socket:
        if self._sock is None:
            raise ProtocolError("client is not connected")
        return self._sock

    # -- sending -----------------------------------------------------------
    def send_raw(self, data: bytes) -> None:
        """Write bytes straight to the socket, no framing added."""
        self.sock.sendall(data)

    def send_frame(self, body: bytes, declared_len: int | None = None) -> None:
        """Send one frame.

        ``declared_len`` overrides the header value, which is what the framing
        tests need in order to lie about the body size.
        """
        length = len(body) if declared_len is None else declared_len
        self.sock.sendall(HEADER.pack(length) + body)

    def send_json(self, payload: dict) -> None:
        self.send_frame(json.dumps(payload).encode("utf-8"))

    def request(self, payload: dict) -> dict:
        """Send a JSON request and read exactly one JSON response."""
        self.send_json(payload)
        return self.read_json()

    def half_close(self) -> None:
        """Shut down the writing half of the connection (client sent EOF)."""
        self.sock.shutdown(socket.SHUT_WR)

    # -- receiving ---------------------------------------------------------
    def read_exactly(self, count: int) -> bytes:
        """Read exactly ``count`` bytes or raise :class:`ProtocolError`."""
        buf = b""
        while len(buf) < count:
            chunk = self.sock.recv(count - len(buf))
            if not chunk:
                raise ProtocolError(
                    f"connection closed after {len(buf)} of {count} expected bytes"
                )
            buf += chunk
        return buf

    def read_frame(self) -> bytes:
        length = HEADER.unpack(self.read_exactly(4))[0]
        if length > MAX_BODY:
            raise ProtocolError(f"server announced an implausible body of {length} bytes")
        return self.read_exactly(length)

    def read_json(self) -> dict:
        return json.loads(self.read_frame().decode("utf-8"))

    # -- negative assertions ----------------------------------------------
    def assert_silent(self, within: float = 1.0) -> None:
        """Assert the server neither answers nor hangs up within ``within``.

        Several malformed requests are dropped by the server without any reply
        while the connection stays open; that behaviour is pinned here.
        """
        self.sock.settimeout(within)
        try:
            data = self.sock.recv(4096)
        except (socket.timeout, TimeoutError):
            return
        finally:
            self.sock.settimeout(self.timeout)
        if data == b"":
            raise AssertionError("expected silence, but the server closed the connection")
        raise AssertionError(f"expected silence, but the server replied with {data!r}")

    def assert_closed(self, within: float = 3.0) -> None:
        """Assert the server hangs up (clean FIN) within ``within`` seconds."""
        self.sock.settimeout(within)
        try:
            data = self.sock.recv(4096)
        except (socket.timeout, TimeoutError):
            raise AssertionError("expected the server to close the connection, it stayed open")
        finally:
            self.sock.settimeout(self.timeout)
        if data != b"":
            raise AssertionError(f"expected a close, got data instead: {data!r}")
