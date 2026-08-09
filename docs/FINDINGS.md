# ShadowGram server — findings

Everything below was observed against a **running** server, not read out of the
source alone; the source references explain *why* the observed behaviour
happens. No server code was changed. Each finding lists the test that pins it.

Verified on 2026-08-08 against `out/build/x64-debug/MessengerServer.exe`
(Debug build), PostgreSQL 18 on `localhost:5432`, schema from `db_init.sql`,
database session timezone `Europe/Minsk` (UTC+03).

Test names refer to files under `tests/`. Two kinds of tests appear:

* `@pytest.mark.characterization` — asserts what the server does **today**, so
  a change in behaviour is noticed.
* `@pytest.mark.xfail` — asserts what the server **should** do. `xfail_strict`
  is on, so the day a finding is fixed the corresponding test turns into a
  failure that says "this now passes, remove the marker".

| ID | Severity | Summary |
|----|----------|---------|
| [F-01](#f-01) | Critical | `send_message` can never store a message |
| [F-02](#f-02) | Critical | No authentication exists; every connection invents an identity |
| [F-03](#f-03) | High | No chat access control (`TODO` in the handler) |
| [F-04](#f-04) | High | Invalid requests get no reply at all; the client hangs |
| [F-05](#f-05) | High | One hardcoded password salt for every account |
| [F-06](#f-06) | Medium | No input validation on `register` |
| [F-07](#f-07) | Medium | `created_at` / `last_seen` are stored with the wrong instant |
| [F-08](#f-08) | Medium | A NUL byte silently truncates string fields |
| [F-09](#f-09) | Medium | Password hashing blocks the single I/O thread (~2 registrations/s) |
| [F-10](#f-10) | Medium | No read timeouts anywhere, despite the "Slowloris protection" note |
| [F-11](#f-11) | Medium | One PostgreSQL backend per TCP connection, opened eagerly |
| [F-12](#f-12) | Medium | `server.port` in `config.json` is ignored |
| [F-13](#f-13) | Low | Username uniqueness is check-then-insert and case-sensitive |
| [F-14](#f-14) | Low | Failed sends still return a `message_id` for a message that does not exist |
| [F-15](#f-15) | Low | Message metadata is invented or dropped (`content_type`, nonce) |
| [F-16](#f-16) | Info | Missing protocol surface: no login, chat creation, or history |
| [F-17](#f-17) | Info | Plaintext transport, and registration reveals whether a username exists |

---

<a id="f-01"></a>
## F-01 (Critical) — `send_message` can never store a message

**Observed.** Every `send_message` request is answered with
`{"type":"response","status":"error","message_id":"<uuid>"}` and the `messages`
table stays empty — including when the target chat really exists.

**Why.** `Session.cpp:21` mints a random UUID per connection and
`Session.cpp:75` uses it as `msg.sender_id`. That UUID is never inserted into
`users`, so the `INSERT` in `PostgresMessageRepository.cpp:70-80` violates the
`messages.sender_id → users(user_id)` foreign key from `db_init.sql:59`, and
`SaveMessage` returns `false`.

**Impact.** The messaging half of the server is non-functional end to end; the
failure is reported to the client only as a bare `"error"`.

**Tests.** `test_send_message.py::test_nothing_is_written_to_the_messages_table`
(characterization), `::test_message_should_be_persisted` (xfail).

**Direction.** The sender must be a real, authenticated user id, which means
F-02 has to be solved first; until then a `send_message` from an
unauthenticated connection should be refused before it reaches the database.

---

<a id="f-02"></a>
## F-02 (Critical) — No authentication exists

**Observed.** A client that has never registered can issue `send_message`
straight away. Registering on a connection does not bind that identity to it:
messages sent afterwards behave exactly the same. There is no `login` action on
the wire — sending one produces silence.

**Why.** `Session.cpp:18-21` is explicit that the identity is temporary
(`// +++ TEMPORARY +++ (then will call AuthService::VerifyToken)`).
`AuthService::LoginUser` (`AuthService.cpp:101-145`) is fully implemented but no
code path reaches it: `Session.cpp` only dispatches `send_message` and
`register`. The `devices.auth_token` column exists in the schema but is never
used.

**Impact.** No client can log in, and nothing on the connection is authorised.

**Tests.** `test_session.py::test_login_is_supported` (xfail),
`test_send_message.py::test_registering_first_should_make_that_user_the_sender`
(xfail) and `::test_registering_on_the_connection_changes_nothing_about_sending`
(characterization).

---

<a id="f-03"></a>
## F-03 (High) — No chat access control

**Observed.** Any connection may address any `chat_id`, including chats it is
not a member of. Nothing is persisted today only because of F-01.

**Why.** `Session.cpp:66-67`:

```
// *** (Checking Access Rights)
// TODO
```

`chat_members` is never consulted.

**Impact.** Once F-01 is fixed, this becomes "any authenticated user can post
into any chat", so the two must be fixed together.

**Test.**
`test_send_message.py::test_posting_into_a_chat_you_are_not_a_member_of_should_be_refused`
(xfail).

---

<a id="f-04"></a>
## F-04 (High) — Invalid requests get no reply at all

**Observed.** The server answers nothing, and keeps the connection open, for:

* an unknown `type` (`login`, `get_messages`, …) or a missing `type`
* a body that is not JSON, is empty, or is not a JSON **object** (`[1,2,3]`, `null`)
* a field of the wrong JSON type (`"username": 12345`)
* a `chat_id` that is not a parseable UUID (including a missing one)

**Why.** The `if/else if` chain in `Session.cpp:57-136` has no `else`; JSON type
errors are swallowed by the `catch` at `Session.cpp:138-141`; a bad chat UUID
hits `continue` at `Session.cpp:61-64`.

**Impact.** A client cannot distinguish "rejected" from "still working" and will
wait for its own timeout. It also makes debugging a client extremely awkward,
since the only trace is on the server's stderr.

**Tests.** `test_framing.py::test_malformed_body_is_dropped_without_any_reply`,
`test_session.py::test_unsupported_action_is_answered_with_silence`,
`test_send_message.py::test_unparseable_chat_id_gets_no_response`
(characterization) plus the matching `*_should_be_answered_with_an_error`
xfail tests.

**Direction.** One error frame per rejected request, with a stable code, and a
default branch for unknown `type` values.

---

<a id="f-05"></a>
## F-05 (High) — One hardcoded salt for every account

**Observed.** Two accounts registered with the same password have byte-identical
`password_hash` values. Every stored hash carries the same salt segment
`c3RvbGV0bnlheWFfc2FsdA` (base64 of `stoletnyaya_salt`).

**Why.** `AuthService.cpp:41`: `std::string salt = "stoletnyaya_salt";` with a
`// TODO: create unique salt for every user` next to it.

**Impact.** One precomputation attacks the whole user table at once, and equal
hashes disclose which users share a password. The Argon2 cost parameters
(`m=65536,t=2,p=1`, `AuthService.cpp:43-51`) are otherwise reasonable.

**Tests.** `test_password_hashing.py::test_every_account_shares_one_hardcoded_salt`
and `::test_two_users_with_the_same_password_get_identical_hashes`
(characterization), `::test_two_users_with_the_same_password_should_get_different_hashes`
(xfail).

**Direction.** Generate a per-user random salt (16 bytes from a CSPRNG) and let
`argon2id_hash_encoded` store it in the encoded string, which
`argon2id_verify` already reads back — no schema change needed.

---

<a id="f-06"></a>
## F-06 (Medium) — No input validation on `register`

**Observed.**

| Input | Result |
|-------|--------|
| `username: ""` | account created |
| no `username` / `password` field at all | account created (fields default to `""`) |
| `password: ""` | account created |
| username of 51 characters | `"Failed to save user to database."` |
| `first_name` of 101 characters | `"Failed to save user to database."` |

**Why.** `Session.cpp:106-108` reads the fields with defaults and passes them
through; `AuthService::RegisterUser` only checks for an existing username. The
length limits that do fire are the `VARCHAR(50)` / `VARCHAR(100)` constraints in
`db_init.sql:17,21`, surfacing as the generic message from
`AuthService.cpp:92`.

**Impact.** Unusable accounts are created, and a plain validation problem is
reported to the user as an internal database failure.

**Tests.** `test_register.py` — `test_empty_username_is_accepted`,
`test_request_without_username_or_password_registers_the_empty_user`,
`test_empty_password_is_accepted`,
`test_over_long_username_surfaces_as_a_generic_database_error`,
`test_over_long_first_name_surfaces_as_a_generic_database_error`
(characterization) plus three xfail counterparts.

---

<a id="f-07"></a>
## F-07 (Medium) — Timestamps are stored with the wrong instant

**Observed.** Immediately after a registration, `now() - created_at` is
**+3 hours**, exactly the UTC offset of the database session (`Europe/Minsk`).

**Why.** `TimeUtils::to_pg_timestamp` (`TimeUtils.cpp:9-18`) formats the time in
UTC with `gmtime_s` but emits no offset. That naive string is bound to
`created_at`/`last_seen`, which are `TIMESTAMP WITH TIME ZONE`
(`db_init.sql:26-27`), so PostgreSQL interprets it in the session timezone. A
server whose database session runs in UTC hides the defect entirely.

**Impact.** Every account's timestamps are wrong by the server's offset; ordering
against `NOW()`-generated values (`messages.sent_at`,
`PostgresMessageRepository.cpp:59`) is inconsistent.

**Tests.** `test_timestamps.py::test_created_at_is_shifted_by_the_database_utc_offset`
(characterization, skipped on a UTC database),
`::test_created_at_should_be_the_current_time` (xfail, non-strict for the same
reason).

**Direction.** Append `Z`/`+00` to the formatted string, or bind the parameter
as a timestamptz rather than text.

---

<a id="f-08"></a>
## F-08 (Medium) — A NUL byte truncates string fields

**Observed.** Registering `"<name>\0ignored-tail"` succeeds and stores
`<name>` — the tail is gone. The pre-existence check truncates the same way, so
`"admin\0x"` collides with `admin` rather than creating a second account.

**Why.** JSON strings may contain `\0`; `std::string` keeps it, but libpq
takes text parameters as C strings, so everything from the NUL on is dropped
(`PostgresUserRepository.cpp:42-50`). Binary columns are unaffected — the
message content path uses `pqxx::binarystring` with an explicit size.

**Impact.** Input that reaches the database is not the input that was validated;
that is a classic building block for impersonation once more identity checks
exist.

**Tests.** `test_register.py::test_nul_byte_truncates_the_username`
(characterization), `::test_username_with_a_nul_byte_should_be_rejected` (xfail).

---

<a id="f-09"></a>
## F-09 (Medium) — Password hashing blocks the single I/O thread

**Observed.** One registration takes ~485 ms; **eight** registrations issued
simultaneously on eight connections take ~4.4 s in total — they are served one
after another, not concurrently. (Debug build; a Release build is faster, but
the serialisation is structural, not a build artefact.)

**Why.** `main.cpp:51` runs `io_context.run()` on one thread, and
`AuthService::RegisterUser` performs Argon2id (`m=65536` → 64 MiB, `t=2`)
synchronously inside the coroutine, as do all libpqxx calls.

**Impact.** Whole-server throughput is ~2 registrations/second and one client
can stall every other client. There is no rate limiting, so this is a cheap DoS:
each request costs the server 64 MiB and ~0.5 s of CPU.

**Test.** Not asserted — a wall-clock threshold would be flaky in CI. The
measurement above is reproducible with the snippet in
[docs/TESTING.md](TESTING.md#manual-measurements).

**Direction.** Run hashing and database work on a thread pool
(`asio::thread_pool` + `co_await asio::post`), or run `io_context.run()` on
several threads and keep per-session state on a strand.

---

<a id="f-10"></a>
## F-10 (Medium) — No read timeouts

**Observed.** A connection that sends a 4-byte header promising 4096 bytes and
then one byte is kept open indefinitely; an idle connection is never closed.

**Why.** `Session.cpp:31-34` carries the comment
`// Reading TIMEOUT *** (Slowloris Protection)` but no timer is ever installed.

**Impact.** Together with F-11, each stalled connection also pins a PostgreSQL
backend, so a few dozen idle sockets can exhaust `max_connections`.

**Tests.** `test_session.py::test_an_idle_connection_is_never_timed_out` and
`::test_a_connection_that_announces_a_body_and_never_sends_it_is_kept_open`
(characterization, both `slow`),
`::test_a_stalled_connection_should_eventually_be_dropped` (xfail).

**Direction.** `asio::steady_timer` raced against the read
(`async_read(...) || timer.async_wait(...)`); the awaitable operators are
already included in `Server.cpp:7`.

---

<a id="f-11"></a>
## F-11 (Medium) — One database backend per connection, opened eagerly

**Observed.** Opening 8 client sockets that send **nothing** raises the backend
count for the database by exactly 8; closing them releases the backends.

**Why.** `Session.cpp:23-25` constructs a fresh `pqxx::connection` at the top of
every session, before the first request is read.

**Impact.** The practical client limit is PostgreSQL's `max_connections`
(100 by default), not anything the server controls, and every idle client costs
a backend. If the database is unavailable, the constructor throws and the
session is dropped with no reply to the client.

**Tests.** `test_resources.py::test_each_idle_client_socket_holds_its_own_database_backend`,
`::test_the_database_connection_is_opened_before_any_request_is_sent`
(characterization).

**Direction.** A shared pool handed to the session, acquired per request.

---

<a id="f-12"></a>
## F-12 (Medium) — `server.port` in the configuration is ignored

**Observed.** With `"server": {"port": 8080}` in `config.json` the server listens
on **54321**.

**Why.** `main.cpp:26-27`: `// TODO : add getPort() to ConfigManager` followed by
`const unsigned short port = 54321;`. `ConfigManager` only exposes
`getDBConnectionString()`.

**Impact.** Deployment cannot move the port; `config.example.json` documents a
setting that does nothing.

**Tests.** `test_config.py::test_the_configured_port_is_ignored`
(characterization), `::test_the_server_should_listen_on_the_configured_port`
(xfail). Both need `SHADOWGRAM_SERVER_CONFIG`.

**Also.** `ConfigManager::getDBConnectionString()` uses `.at()`, so a config file
missing `database.connection_string` throws a `nlohmann` exception that reaches
`main`'s generic handler instead of the "couldn't load config" path.

---

<a id="f-13"></a>
## F-13 (Low) — Username uniqueness is check-then-insert and case-sensitive

**Observed.** `"NAME"` and `"name"` are two separate accounts.

**Why.** `AuthService.cpp:25-31` does a `SELECT` and then an `INSERT` in a later
transaction. Correctness rests entirely on the `UNIQUE` constraint
(`db_init.sql:17`), and when that constraint is the thing that fires, the client
gets `"Failed to save user to database."` instead of `"Username already taken"`.
Two simultaneous registrations of the same name therefore produce two different
error messages depending on timing.

**Impact.** Confusable account names (`Admin` vs `admin`) and a
timing-dependent error message.

**Test.** `test_register.py::test_usernames_differing_only_in_case_are_two_accounts`
(characterization). The race itself is not asserted — reproducing it reliably
would need a fault injection point in the server.

---

<a id="f-14"></a>
## F-14 (Low) — Failed sends still return a `message_id`

**Observed.** A rejected `send_message` replies with `status: "error"` **and** a
`message_id` that exists nowhere.

**Why.** `Session.cpp:89-93` always fills `message_id` from the locally
generated UUID, independent of `isSaved`.

**Impact.** A client that keys local state on the returned id ends up with a
message that the server has no record of.

**Test.** `test_send_message.py::test_error_response_still_carries_a_message_id_that_exists_nowhere`
(characterization).

---

<a id="f-15"></a>
## F-15 (Low) — Message metadata is invented or dropped

* `msg.content_type` is never assigned in `Session.cpp`, so every message would
  be stored as `'unknown'` (`Message.h:31`, `PostgresMessageRepository.cpp:75`).
* When the client sends no `nonce`, the **server** fabricates one
  (`GenerateDummyNonce`, `PostgresMessageRepository.cpp:28-33`) and stores it as
  if it were a real encryption nonce. For a project that plans end-to-end
  encryption this is worth removing early: server-generated crypto material in a
  column named `encryption_nonce` invites a false sense of security.
* `nonce` and `content` are taken as raw JSON text (`Session.cpp:78-83`), so
  binary content cannot be transmitted; the code comment already notes Base64 is
  the intent.

Not separately asserted, because F-01 prevents any row from being written.

---

<a id="f-16"></a>
## F-16 (Info) — Missing protocol surface

Only `register` and `send_message` exist. There is no login, no chat creation or
membership management, no message history, no delivery/read status, and no push
of an incoming message to the recipient's connection — a message that *was*
stored could never be read back by anyone. `IChatRepository.h` and
`IMessageRepository.h` are declared but there is no chat repository
implementation, and `ChatManager.cpp`, `MessageManager.cpp` and
`UserManager.cpp` are empty files that are not part of the build
(`MessengerServer/CMakeLists.txt:15-25`).

The tests reflect this: chats have to be inserted straight into the database
(`conftest.py::existing_chat`) because the protocol offers no way to create one.

---

<a id="f-17"></a>
## F-17 (Info) — Transport and disclosure

* The protocol is plain TCP. Credentials in `register` cross the wire in clear
  text, so the Argon2 hashing protects the database but not the login itself.
  The README lists TLS/E2E as planned.
* `register` answers `"Username already taken"`, which lets anyone enumerate
  accounts. That is a normal trade-off for a registration form; worth a
  conscious decision rather than an accident.
* The database password lives in plain text in
  `MessengerServer/src/config.json`. That file is correctly listed in
  `.gitignore`, so it is not in the repository — keep it that way.
