"""
VM Provider factory と /vm/status・replay エンドポイントのテスト
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app
from app.services.vm_factory import get_vm_provider, is_real_provider
from app.services.vm_provider import MockVMProvider
from app.services.virtualbox_provider import VirtualBoxProvider


@pytest.fixture
async def client(tmp_path):
    """独立した SQLite を使うテストクライアント。"""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_db():
        async with session_factory() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_db] = override_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
    await engine.dispose()


# ------------------------------------------------------------------ factory

def test_factory_は既定でMockを返す(monkeypatch):
    monkeypatch.setattr("app.services.vm_factory.settings.VM_PROVIDER", "mock")
    assert isinstance(get_vm_provider(), MockVMProvider)
    assert is_real_provider() is False


def test_factory_はvirtualboxで実機を返す(monkeypatch):
    monkeypatch.setattr("app.services.vm_factory.settings.VM_PROVIDER", "virtualbox")
    assert isinstance(get_vm_provider(), VirtualBoxProvider)
    assert is_real_provider() is True


def test_factory_は不明な値ならMockへフォールバック(monkeypatch):
    monkeypatch.setattr("app.services.vm_factory.settings.VM_PROVIDER", "docker")
    assert isinstance(get_vm_provider(), MockVMProvider)
    assert is_real_provider() is False


# ------------------------------------------------------------------ /vm/status

@pytest.mark.asyncio
async def test_status_はモックモードでavailable(client, monkeypatch):
    monkeypatch.setattr("app.services.vm_factory.settings.VM_PROVIDER", "mock")
    r = await client.get("/api/v1/vm/status")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "MockVMProvider"
    assert body["simulated"] is True
    assert body["available"] is True


@pytest.mark.asyncio
async def test_status_はVBoxManageが無ければ理由を返す(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.vm_factory.settings.VM_PROVIDER", "virtualbox")
    monkeypatch.setattr(
        "app.services.virtualbox_provider._CANDIDATE_PATHS", ["/nope/vboxmanage"]
    )
    monkeypatch.setattr("app.services.virtualbox_provider.shutil.which", lambda n: None)
    monkeypatch.setattr(
        "app.services.vm_factory.settings.VBOXMANAGE_PATH", ""
    )
    r = await client.get("/api/v1/vm/status")
    body = r.json()
    assert body["available"] is False
    assert "VBoxManage" in body["detail"]


@pytest.mark.asyncio
async def test_status_は基準VMが無くても判定できる(client, monkeypatch, vboxmanage_path):
    monkeypatch.setattr("app.services.vm_factory.settings.VM_PROVIDER", "virtualbox")
    monkeypatch.setenv("FAKE_VBOX_VMS", "SomeOtherVM,AnotherVM")
    wrapper = vboxmanage_path
    monkeypatch.setattr("app.services.virtualbox_provider.settings.VBOXMANAGE_PATH", wrapper)
    monkeypatch.setattr("app.services.virtualbox_provider.settings.VBOX_BASE_VM", "GhostBase")
    monkeypatch.setattr("app.services.virtualbox_provider.settings.VBOX_GUEST_USERNAME", "u")
    monkeypatch.setattr("app.services.virtualbox_provider.settings.VBOX_PROJECT_PATH", r"C:\game")

    r = await client.get("/api/v1/vm/status")
    body = r.json()
    assert body["available"] is False
    assert "基準 VM" in body["detail"]
    assert body["base_vm_found"] is False
    assert "SomeOtherVM" in body["registered_vms"]


@pytest.mark.asyncio
async def test_status_は基準VMがあればavailableになる(client, monkeypatch, vboxmanage_path):
    monkeypatch.setattr("app.services.vm_factory.settings.VM_PROVIDER", "virtualbox")
    monkeypatch.setenv("FAKE_VBOX_VMS", "DevMirror-Base,DevMirror-envA")
    wrapper = vboxmanage_path
    monkeypatch.setattr("app.services.virtualbox_provider.settings.VBOXMANAGE_PATH", wrapper)
    monkeypatch.setattr("app.services.virtualbox_provider.settings.VBOX_BASE_VM", "DevMirror-Base")
    monkeypatch.setattr("app.services.virtualbox_provider.settings.VBOX_GUEST_USERNAME", "u")
    monkeypatch.setattr("app.services.virtualbox_provider.settings.VBOX_PROJECT_PATH", r"C:\game")

    r = await client.get("/api/v1/vm/status")
    body = r.json()
    assert body["base_vm_found"] is True
    assert body["available"] is True, body["detail"]


# ------------------------------------------------------------------- replay

@pytest.mark.asyncio
async def test_replay_はモックならsimulatedと検証不可になる(client, monkeypatch):
    monkeypatch.setattr("app.services.vm_factory.settings.VM_PROVIDER", "mock")
    seed = await client.post("/api/v1/demo/dx-library")
    assert seed.status_code == 200
    incident_id = seed.json()["incident_id"]

    r = await client.post(f"/api/v1/incidents/{incident_id}/replay")
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "MockVMProvider"
    assert body["simulated"] is True
    assert body["reproduction_verified"] is False
    assert "再現は未検証" in body["incident"]["timeline"][-1]["detail"]


@pytest.mark.asyncio
async def test_replay_はVM作成失敗を503で返す(client, monkeypatch, tmp_path):
    """VirtualBox が無ければ 500 ではなく分かりやすい 503 を返す"""
    monkeypatch.setattr("app.services.vm_factory.settings.VM_PROVIDER", "virtualbox")
    monkeypatch.setattr(
        "app.services.virtualbox_provider._CANDIDATE_PATHS", ["/nope/vboxmanage"]
    )
    monkeypatch.setattr("app.services.virtualbox_provider.shutil.which", lambda n: None)
    monkeypatch.setattr("app.services.virtualbox_provider.settings.VBOXMANAGE_PATH", "")

    seed = await client.post("/api/v1/demo/dx-library")
    incident_id = seed.json()["incident_id"]

    r = await client.post(f"/api/v1/incidents/{incident_id}/replay")
    assert r.status_code == 503
    assert "VM を作成できません" in r.json()["detail"]
