import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import app.modules  # noqa: F401 — register all models
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app as fastapi_app

engine = create_engine(settings.test_database_url, pool_pre_ping=True)
TestSession = sessionmaker(autoflush=False, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db():
    """Each test runs inside one outer transaction that is rolled back at the end.
    Session-level commit() only releases a savepoint, so tests stay isolated."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestSession(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def fake_ai(monkeypatch):
    """Scripted anthropic client; shared by test_ai.py and test_ingestion.py."""
    from app.modules.ai import client as ai_client
    from tests.ai_fakes import FakeAnthropic

    fake = FakeAnthropic()
    original_get_client = ai_client.get_client
    original_get_client.cache_clear()
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(ai_client, "get_client", lambda: fake)
    # ai.service imported get_client by name — patch there too
    from app.modules.ai import service as ai_service

    monkeypatch.setattr(ai_service, "get_client", lambda: fake)
    yield fake
    original_get_client.cache_clear()


@pytest.fixture
def no_ai(monkeypatch):
    from app.modules.ai import client as ai_client

    original_get_client = ai_client.get_client
    monkeypatch.setattr(settings, "anthropic_api_key", None)
    original_get_client.cache_clear()
    yield
    original_get_client.cache_clear()


@pytest.fixture(autouse=True)
def media_root(tmp_path, monkeypatch):
    """Ingestion uploads land in a per-test temp dir, never the repo tree."""
    monkeypatch.setattr(settings, "media_root", str(tmp_path / "media"))
    return tmp_path / "media"


@pytest.fixture
def client(db: Session):
    def _get_db():
        # Checkpoint fixture/factory state into the outer transaction so a
        # request-level rollback (on error responses) can't wipe it: rollback
        # then only undoes work done inside the failing request itself.
        db.commit()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise

    fastapi_app.dependency_overrides[get_db] = _get_db
    with TestClient(fastapi_app) as c:
        yield c
    fastapi_app.dependency_overrides.clear()
