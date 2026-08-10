from __future__ import annotations

import os
from typing import Literal
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv(".env")

DatabaseRole = Literal["collector", "mcp"]


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"필수 환경변수가 없습니다: {name}")
    return value


def build_db_url(role: DatabaseRole = "collector") -> str:
    if role == "collector":
        user = _required_env("MYSQL_COLLECTOR_USER")
        password = _required_env("MYSQL_COLLECTOR_PASSWORD")
    elif role == "mcp":
        user = _required_env("MYSQL_MCP_USER")
        password = _required_env("MYSQL_MCP_PASSWORD")
    else:
        raise ValueError(f"지원하지 않는 DB 역할입니다: {role}")

    host = _required_env("MYSQL_HOST")
    port = _required_env("MYSQL_PORT")
    database = _required_env("MYSQL_DATABASE")

    return (
        "mysql+pymysql://"
        f"{quote_plus(user)}:{quote_plus(password)}"
        f"@{host}:{port}/{database}?charset=utf8mb4"
    )


def create_db_engine(
    role: DatabaseRole = "collector",
    *,
    echo: bool = False,
) -> Engine:
    return create_engine(
        build_db_url(role),
        echo=echo,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


engine = create_db_engine("collector")
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)
Base = declarative_base()
