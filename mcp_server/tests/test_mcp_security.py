from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.applications import Starlette

from mcp_server.security import MCPRequestSecurity

TOKEN = "test-token-which-is-at-least-32-characters"


async def endpoint(request):
    return JSONResponse({"accepted": True})


def make_client(max_request_bytes: int = 1024) -> TestClient:
    inner = Starlette(routes=[Route("/mcp", endpoint, methods=["POST"])])
    app = MCPRequestSecurity(
        inner,
        auth_token=TOKEN,
        max_request_bytes=max_request_bytes,
    )
    return TestClient(app)


def test_missing_bearer_token_is_rejected() -> None:
    with make_client() as client:
        response = client.post("/mcp", json={"method": "tools/list"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["cache-control"] == "no-store"


def test_invalid_bearer_token_is_rejected() -> None:
    with make_client() as client:
        response = client.post(
            "/mcp",
            headers={"Authorization": "Bearer wrong-token"},
            json={"method": "tools/list"},
        )

    assert response.status_code == 401


def test_valid_bearer_token_is_accepted() -> None:
    with make_client() as client:
        response = client.post(
            "/mcp",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"method": "tools/list"},
        )

    assert response.status_code == 200
    assert response.json() == {"accepted": True}
    assert response.headers["x-content-type-options"] == "nosniff"


def test_request_body_larger_than_limit_is_rejected() -> None:
    with make_client() as client:
        response = client.post(
            "/mcp",
            headers={"Authorization": f"Bearer {TOKEN}"},
            content=b"x" * 1025,
        )

    assert response.status_code == 413


def test_health_check_does_not_require_secret() -> None:
    with make_client() as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
