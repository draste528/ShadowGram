# Testing the ShadowGram server

The suite in `tests/` is a **black-box integration suite**: it speaks the real
TCP protocol to a running `MessengerServer` and, optionally, checks what reached
PostgreSQL. Nothing is compiled, linked or mocked, so no build system changes
are needed and the server sources are untouched.

What it deliberately does *not* do: unit-test C++ classes. That would need a
test target in CMake and seams that do not exist yet (`AuthService` takes an
`IUserRepository`, which is a good seam; `Session` constructs its own
`pqxx::connection`, which is not). Until then, everything observable is
observable from the outside.

---

## 1. Prerequisites

* Python 3.10+
* PostgreSQL reachable, with the schema from `ShadowGram/db_init.sql` applied
* A built server: `ShadowGram/out/build/<preset>/MessengerServer/MessengerServer.exe`

Install the test dependencies into a virtualenv:

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r tests/requirements.txt
```

`psycopg` is optional. Without it (or without a DSN) the tests marked `db` skip
and the protocol-level tests still run.

## 2. Use a throwaway database

The tests create users, insert a chat row and never delete anything by default.
Point the server at a scratch database, not your development one:

```bash
createdb shadowgram_test
psql -d shadowgram_test -f ShadowGram/db_init.sql
```

Then copy `MessengerServer/src/config.example.json` to a directory of your own,
set `database.connection_string` to that scratch database, and start the server
from that directory (it reads `./config.json` from its working directory):

```bash
cd /path/to/scratch-dir && /path/to/MessengerServer.exe
```

## 3. Run

```bash
SHADOWGRAM_TEST_DSN=postgresql://user:pass@localhost:5432/shadowgram_test python -m pytest tests -q
```

On Windows PowerShell:

```powershell
$env:SHADOWGRAM_TEST_DSN = "postgresql://user:pass@localhost:5432/shadowgram_test"; python -m pytest tests -q
```

Useful selections:

```bash
python -m pytest tests -q -m "not slow"      # skip the ~15 s of timeout tests
python -m pytest tests -q -m db              # only the database assertions
python -m pytest tests -q -rx                # explain every xfail
```

### Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `SHADOWGRAM_HOST` | `127.0.0.1` | server address |
| `SHADOWGRAM_PORT` | `54321` | server port (hardcoded in `main.cpp`, see F-12) |
| `SHADOWGRAM_TEST_DSN` | unset | libpq DSN of the database the server uses; `db` tests skip without it |
| `SHADOWGRAM_SERVER_EXE` | unset | if the port is closed, start this executable for the session |
| `SHADOWGRAM_SERVER_CWD` | exe's directory | working directory for that executable (where its `config.json` lives) |
| `SHADOWGRAM_SERVER_CONFIG` | unset | path to the server's `config.json`; `test_config.py` skips without it |
| `SHADOWGRAM_CLEANUP` | unset | `1` deletes the rows the suite created (usernames starting with `sgtest_`) |

If no server is listening and `SHADOWGRAM_SERVER_EXE` is not set, every test
skips with a message saying so — the suite never fails because of a missing
environment.

## 4. Layout

| File | Covers |
|------|--------|
| `tests/shadowgram_client.py` | the wire protocol: framing, reads, negative assertions |
| `tests/conftest.py` | server discovery/startup, connections, database handle, name generation |
| `tests/test_framing.py` | length prefix, split and coalesced frames, the 1 MiB limit, malformed bodies |
| `tests/test_register.py` | the `register` action, validation, encoding, SQL-injection payloads |
| `tests/test_password_hashing.py` | what lands in `users.password_hash` |
| `tests/test_send_message.py` | the `send_message` action and what it fails to persist |
| `tests/test_session.py` | connection lifetime, unknown actions, concurrency, timeouts |
| `tests/test_timestamps.py` | `created_at` / `last_seen` correctness |
| `tests/test_resources.py` | database backends per connection |
| `tests/test_config.py` | configuration that is (not) honoured |

## 5. The protocol, as implemented

Both directions use the same framing:

```
uint32 big-endian body length | body length bytes of UTF-8 JSON
```

* bodies larger than 1 MiB make the server close the connection without reading
  them; exactly 1 MiB is accepted
* there is no request id, so responses are matched to requests by order
* requests: `{"type":"register","username","password","first_name"}`,
  `{"type":"login","username","password"}` (F-02) and
  `{"type":"send_message","chat_id","content","nonce"}`
* responses: `{"type":"register_response","status":"ok","user_id"}`,
  `{"type":"register_response","status":"error","message"}`,
  `{"type":"login_response","status":"ok","user_id"}`,
  `{"type":"login_response","status":"error","message"}`,
  `{"type":"response","status":"ok"|"error","message_id"}`
* `send_message` requires a prior `login` on the same connection; without one it
  is refused before it reaches the database (F-01/F-02)
* anything else produces exactly one error frame,
  `{"type":"error_response","status":"error","code","message"}` (F-04). `code`
  is stable and is one of `invalid_json` (body is not JSON), `invalid_request`
  (body is JSON but not an object), `invalid_field` (a field has the wrong JSON
  type), `unknown_action` (unknown or missing `type`) or `invalid_chat_id`.
  `message` is prose for humans and nothing asserts it

## 6. Conventions

`pytest.ini` sets `xfail_strict = true`. Two markers carry the intent:

* `@pytest.mark.characterization` — asserts today's behaviour, including
  behaviour that is wrong. If a fix changes it, the test fails and points at the
  finding to re-check. Do not "fix" such a test without reading
  [FINDINGS.md](FINDINGS.md).
* `@pytest.mark.xfail(reason="F-NN: …")` — asserts the behaviour the server
  *should* have. It fails today, on purpose. When the finding is fixed, the test
  starts passing and, because of `xfail_strict`, the run fails with
  `XPASS(strict)` — that is the signal to delete the marker and (if there is
  one) the matching characterization test.

Most findings therefore have a pair of tests: one describing the present, one
describing the intent.

### Collapsing a pair when a finding is fixed

When the two members of a pair describe the *same* request, fixing the finding
makes them redundant and they are merged into one test named after the intended
behaviour. The richer member survives — usually the parameterized one — and the
other's case is folded in as an extra parameter rather than deleted.

That happened to four xfail tests when **F-04** was fixed. Each was a
single-case duplicate of a characterization test covering the identical
request, so each became one parameter of the test that replaced the pair:

| Deleted xfail test | Its case | Absorbed into | As parameter |
|---|---|---|---|
| `test_framing.py::test_malformed_body_should_be_answered_with_an_error_frame` | `{not json` | `test_malformed_body_is_answered_with_an_error_frame` | `broken-object` |
| `test_session.py::test_unknown_action_should_be_answered_with_an_error` | `definitely_not_an_action` | `test_unsupported_action_is_answered_with_an_error` | `nonsense` |
| `test_register.py::test_non_string_username_should_be_answered_with_an_error` | `username: 12345` | `test_wrongly_typed_field_is_answered_with_an_error` | `username-number` |
| `test_send_message.py::test_unparseable_chat_id_should_be_answered_with_an_error` | `not-a-uuid` | `test_unparseable_chat_id_is_answered_with_an_error` | `garbage` |

The characterization tests those four paired with were not deleted either: they
are the tests listed in the third column, rewritten to assert the error frame
and its `code` instead of the silence they used to pin. No scenario asserted
before F-04 is unasserted after it.

Everything the suite writes uses the `sgtest_` username prefix, which is what
makes the optional `SHADOWGRAM_CLEANUP=1` step safe.

## 7. Manual measurements

F-09 (hashing blocks the single I/O thread) is measured rather than asserted,
because a wall-clock threshold would be flaky. To reproduce:

```python
import json, socket, struct, time, uuid

def rt(sock, obj):
    body = json.dumps(obj).encode()
    sock.sendall(struct.pack(">I", len(body)) + body)
    n = struct.unpack(">I", sock.recv(4))[0]
    return json.loads(sock.recv(n))

def reg():
    return {"type": "register", "username": "perf_" + uuid.uuid4().hex[:8],
            "password": "p", "first_name": "x"}

socks = [socket.create_connection(("127.0.0.1", 54321), 30) for _ in range(8)]
start = time.perf_counter()
for s in socks:
    body = json.dumps(reg()).encode()
    s.sendall(struct.pack(">I", len(body)) + body)
for s in socks:
    n = struct.unpack(">I", s.recv(4))[0]
    s.recv(n)
print("8 parallel registrations:", round(time.perf_counter() - start, 2), "s")
```

Measured on the Debug build: ~0.49 s for one registration, ~4.4 s for eight
issued at once — i.e. fully serialised.
