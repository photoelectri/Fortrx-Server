import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import asynccontextmanager

from app.main import app
from app.database import Base, ensure_key_bundle_schema, ensure_server_changes_schema, get_db
from app.services.storage_service import ensure_bucket_exists
from app.crypto.keys import (
    generate_identity_keypair,
    generate_signed_prekey,
    generate_one_time_prekeys,
    encode_public_key,
)
from limits.storage import storage_from_string

@pytest.fixture(autouse=True)
def control_rate_limit(request):
    from app.main import app

    if "rate_limit" in request.node.name:
        storage = storage_from_string("memory://")
        app.state.limiter._storage = storage
        app.state.limiter.limiter.storage = storage
        app.state.limiter.enabled = True   # enable ONLY for this test
    else:
        app.state.limiter.enabled = False
# ---------------------------------------------------------------------------
# Login helper — OAuth2PasswordRequestForm requires form data, not JSON
# ---------------------------------------------------------------------------

def _login(client, username: str, password: str) -> dict:
    resp = client.post(
        "/auth/login",
        data={"username": username, "password": password},
    )
    assert resp.status_code == 200, (
        f"Login failed for {username}: {resp.status_code} {resp.text}"
    )
    return resp.json()

# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def db_engine(tmp_path_factory):
    db_dir = tmp_path_factory.mktemp("fortrx-server-tests")
    db_path = db_dir / "test_fortress.db"
    test_database_url = f"sqlite:///{db_path.as_posix()}"
    engine = create_engine(
        test_database_url,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    db_path.unlink(missing_ok=True)


@pytest.fixture(scope="session")
def db_session(db_engine):
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )
    import app.database as app_database
    app_database.engine = db_engine
    app_database.SessionLocal = TestingSessionLocal
    ensure_key_bundle_schema()
    ensure_server_changes_schema()
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="session")
def client(db_session):
    @asynccontextmanager
    async def test_lifespan(_app):
        yield

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    app.router.lifespan_context = test_lifespan
    ensure_bucket_exists()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Key fixtures  (raw bytes kept for local crypto tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def alice_keys():
    identity = generate_identity_keypair()
    spk = generate_signed_prekey(identity["signing_private"])
    otpks = generate_one_time_prekeys(5)
    return {
        "identity": identity,
        "spk": spk,
        "otpks": otpks,
    }


@pytest.fixture(scope="session")
def bob_keys():
    identity = generate_identity_keypair()
    spk = generate_signed_prekey(identity["signing_private"])
    otpks = generate_one_time_prekeys(5)
    return {
        "identity": identity,
        "spk": spk,
        "otpks": otpks,
    }


# ---------------------------------------------------------------------------
# Auth fixtures — register + login, return token + user id
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def alice_auth(client):
    client.post(
        "/auth/register",
        json={
            "username": "alice",
            "email": "alice@fortress.test",
            "password": "alice_secret_123",
        },
    )
    data = _login(client, "alice", "alice_secret_123")
    return {
        "token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "device_id": data.get("device_id"),
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


@pytest.fixture(scope="session")
def bob_auth(client):
    reg = client.post(
        "/auth/register",
        json={
            "username": "bob",
            "email": "bob@fortress.test",
            "password": "bob_secret_456",
        },
    )
    data = _login(client, "bob", "bob_secret_456")
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me.status_code == 200, f"Unable to resolve bob profile: {me.status_code} {me.text}"
    bob_id = me.json()["id"]
    return {
        "token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "device_id": data.get("device_id"),
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
        "id": bob_id,
    }


@pytest.fixture(autouse=True)
def mock_storage(monkeypatch):
    storage = {}

    def fake_upload_blob(key: str, data: bytes):   # ✅ FIXED SIGNATURE
        storage[key] = data
        return key

    def fake_download_blob(key: str):
        return storage.get(key, b"test-data")

    # patch original
    monkeypatch.setattr(
        "app.services.storage_service.upload_blob",
        fake_upload_blob
    )
    monkeypatch.setattr(
        "app.services.storage_service.download_blob",
        fake_download_blob
    )

    # patch where used
    monkeypatch.setattr(
        "app.services.message_service.upload_blob",
        fake_upload_blob
    )
    monkeypatch.setattr(
        "app.services.message_service.download_blob",
        fake_download_blob
    )
    
@pytest.fixture
def alice_id(client, alice_auth):
    resp = client.get("/auth/me", headers=alice_auth["headers"])
    assert resp.status_code == 200
    return resp.json()["id"]
