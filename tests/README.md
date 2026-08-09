# tests/

Black-box integration tests for the C++ MessengerServer. They talk to a running
server over TCP; no C++ is built or modified.

Quick start (from the repository root, with a server running against a
**throwaway** database):

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r tests/requirements.txt
.venv/Scripts/python -m pytest tests -q
```

Add database assertions by pointing the suite at the same database the server
uses:

```bash
SHADOWGRAM_TEST_DSN=postgresql://user:pass@localhost:5432/shadowgram_test python -m pytest tests -q
```

Without a running server (and without `SHADOWGRAM_SERVER_EXE`) every test skips
with an explanation; without `SHADOWGRAM_TEST_DSN` only the `db` tests skip.

The suite creates users and one chat row and does not delete them unless you set
`SHADOWGRAM_CLEANUP=1`. Everything it creates is prefixed `sgtest_`.

Two markers matter:

* `characterization` — pins current behaviour, including known-wrong behaviour
* `xfail` — states the intended behaviour of a known defect; the `reason` names
  the finding (`F-NN`) in [../docs/FINDINGS.md](../docs/FINDINGS.md)

Full guide: [../docs/TESTING.md](../docs/TESTING.md).
Defects the suite documents: [../docs/FINDINGS.md](../docs/FINDINGS.md).
