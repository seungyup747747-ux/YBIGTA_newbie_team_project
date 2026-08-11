from __future__ import annotations

import os
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine

load_dotenv(".env")


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"필수 환경변수가 없습니다: {name}")
    return value


def build_mcp_db_url() -> str:
    """Build a URL using only the read-only MCP database account."""
    user = _required_env("MYSQL_MCP_USER")
    password = _required_env("MYSQL_MCP_PASSWORD")
    host = _required_env("MYSQL_HOST")
    port = _required_env("MYSQL_PORT")
    database = _required_env("MYSQL_DATABASE")

    return (
        "mysql+pymysql://"
        f"{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{database}?charset=utf8mb4"
    )


def create_mcp_engine(*, echo: bool = False) -> Engine:
    return create_engine(
        build_mcp_db_url(),
        echo=echo,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={
            "connect_timeout": 5,
            "read_timeout": 10,
            "write_timeout": 10,
        },
    )
