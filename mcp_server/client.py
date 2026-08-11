from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List Weather MCP tools and make a real tool call.",
    )
    parser.add_argument(
        "--action",
        choices=("list", "call", "all"),
        default="all",
    )
    parser.add_argument(
        "--tool",
        default="get_latest_weather",
    )
    parser.add_argument(
        "--arguments",
        default='{"location": "신촌"}',
        help="Tool arguments as a JSON object.",
    )
    return parser.parse_args()


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    return value


async def run(args: argparse.Namespace) -> None:
    url = os.getenv("MCP_SERVER_URL", "http://127.0.0.1/mcp")
    token = required_env("MCP_AUTH_TOKEN")
    headers = {"Authorization": f"Bearer {token}"}

    async with streamablehttp_client(url, headers=headers) as streams:
        read_stream, write_stream, _ = streams
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            if args.action in {"list", "all"}:
                tools = await session.list_tools()
                print("=== MCP TOOL LIST ===")
                print(
                    json.dumps(
                        [
                            {
                                "name": tool.name,
                                "description": tool.description,
                                "inputSchema": tool.inputSchema,
                            }
                            for tool in tools.tools
                        ],
                        ensure_ascii=False,
                        indent=2,
                    )
                )

            if args.action in {"call", "all"}:
                arguments = json.loads(args.arguments)
                if not isinstance(arguments, dict):
                    raise ValueError("--arguments must be a JSON object")
                result = await session.call_tool(args.tool, arguments)
                print("=== MCP TOOL CALL ===")
                print(f"tool={args.tool}")
                print(f"arguments={json.dumps(arguments, ensure_ascii=False)}")
                print(
                    json.dumps(
                        jsonable(result),
                        ensure_ascii=False,
                        indent=2,
                    )
                )


def main() -> None:
    load_dotenv(".env")
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()
