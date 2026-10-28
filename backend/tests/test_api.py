from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint_is_public() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_trip_routes_require_a_bearer_token() -> None:
    response = client.get("/api/trips")
    assert response.status_code == 401
    assert response.json()["detail"] == "Sign in to continue."


def test_image_proxy_requires_a_bearer_token() -> None:
    response = client.get("/api/images", params={"q": "Kyoto"})
    assert response.status_code == 401


def test_localhost_and_loopback_origins_are_allowed_on_vite_ports() -> None:
    for origin in (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ):
        response = client.options(
            "/api/auth/signup",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
