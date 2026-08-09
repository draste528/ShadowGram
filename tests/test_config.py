"""Configuration handling.

These tests only run when SHADOWGRAM_SERVER_CONFIG points at the config.json
the server under test was started with.

Reference: MessengerServer/src/main.cpp lines 17-27 and
include/Services/ConfigManager.h.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("server")


def test_config_provides_a_database_connection_string(server_config):
    assert server_config["database"]["connection_string"]


@pytest.mark.characterization
def test_the_configured_port_is_ignored(server_config, sg_port):
    """main.cpp hardcodes 54321 next to a `TODO: add getPort()` comment, so the
    `server.port` value in config.json has no effect."""
    configured = server_config.get("server", {}).get("port")
    if configured is None:
        pytest.skip("config.json has no server.port entry")
    if configured == sg_port:
        pytest.skip("config.json happens to match the hardcoded port")

    assert sg_port == 54321


@pytest.mark.xfail(
    reason="F-12: the listening port is hardcoded in main.cpp, config.json's "
           "server.port is never read",
)
def test_the_server_should_listen_on_the_configured_port(server_config, sg_port):
    configured = server_config.get("server", {}).get("port")
    if configured is None:
        pytest.skip("config.json has no server.port entry")

    assert sg_port == configured
