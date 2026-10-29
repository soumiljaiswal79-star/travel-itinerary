from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import main
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


def test_signup_creates_confirmed_account_and_returns_session(monkeypatch) -> None:
    created_attributes = {}
    sign_in_credentials = {}

    def create_user(attributes):
        created_attributes.update(attributes)
        return SimpleNamespace(user=SimpleNamespace(id="user-id", email="traveler@example.com"))

    session = SimpleNamespace(
        model_dump=lambda mode: {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_in": 3600,
            "token_type": "bearer",
        }
    )

    def sign_in_with_password(credentials):
        sign_in_credentials.update(credentials)
        return SimpleNamespace(
            user=SimpleNamespace(id="user-id", email="traveler@example.com"),
            session=session,
        )

    admin_client = SimpleNamespace(
        auth=SimpleNamespace(admin=SimpleNamespace(create_user=create_user))
    )
    public_client = SimpleNamespace(
        auth=SimpleNamespace(sign_in_with_password=sign_in_with_password)
    )
    monkeypatch.setattr(main, "db_client", lambda settings: admin_client)
    monkeypatch.setattr(main, "auth_client", lambda settings: public_client)

    response = client.post(
        "/api/auth/signup",
        json={"email": "traveler@example.com", "password": "secure-password"},
    )

    assert response.status_code == 201
    assert created_attributes == {
        "email": "traveler@example.com",
        "password": "secure-password",
        "email_confirm": True,
    }
    assert sign_in_credentials == {
        "email": "traveler@example.com",
        "password": "secure-password",
    }
    assert response.json()["user"]["id"] == "user-id"
    assert response.json()["session"]["access_token"] == "access"


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
