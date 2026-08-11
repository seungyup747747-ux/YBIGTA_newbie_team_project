from __future__ import annotations

from urllib.parse import unquote_plus

import pytest

from mcp_server.database import build_mcp_db_url


def test_mcp_database_url_uses_only_read_only_account(monkeypatch) -> None:
    monkeypatch.setenv("MYSQL_HOST", "private-rds.example")
    monkeypatch.setenv("MYSQL_PORT", "3306")
    monkeypatch.setenv("MYSQL_DATABASE", "weather_db")
    monkeypatch.setenv("MYSQL_MCP_USER", "mcp_user")
    monkeypatch.setenv("MYSQL_MCP_PASSWORD", "read-only password")
    monkeypatch.setenv("MYSQL_COLLECTOR_USER", "collector_user")
    monkeypatch.setenv("MYSQL_COLLECTOR_PASSWORD", "write-password")

    url = unquote_plus(build_mcp_db_url())

    assert "mcp_user:read-only password" in url
    assert "collector_user" not in url
    assert "write-password" not in url


def test_missing_mcp_password_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("MYSQL_HOST", "private-rds.example")
    monkeypatch.setenv("MYSQL_PORT", "3306")
    monkeypatch.setenv("MYSQL_DATABASE", "weather_db")
    monkeypatch.setenv("MYSQL_MCP_USER", "mcp_user")
    monkeypatch.delenv("MYSQL_MCP_PASSWORD", raising=False)

    with pytest.raises(RuntimeError, match="MYSQL_MCP_PASSWORD"):
        build_mcp_db_url()
