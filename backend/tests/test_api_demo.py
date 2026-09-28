import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app


@pytest.fixture
async def client(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with Session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_health(client):
    res = await client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_dx_demo_seed_and_diff_flow(client):
    seeded = await client.post("/api/v1/demo/dx-library")
    assert seeded.status_code == 200
    body = seeded.json()
    assert body["incident_id"] == "INC-0001"

    incident = await client.get("/api/v1/incidents/INC-0001")
    assert incident.status_code == 200
    data = incident.json()
    assert data["project_name"] == "DXGame"
    assert data["test_result"] == "FAIL"
    assert data["ai_diagnosis"]["is_mock"] is True
    assert "DxLib.dll" in data["logs"]

    diff = await client.get(f"/api/v1/diffs/{data['diff_id']}")
    assert diff.status_code == 200
    dx = next(e for e in diff.json()["entries"] if e["field"] == "DX Library")
    assert dx["status"] == "MISSING"
    assert dx["potentially_relevant"] is True
