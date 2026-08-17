"""In-process API integration test covering the full flow.

Requires a reachable Postgres (DATABASE_URL). Skipped automatically if the
database cannot be reached, so unit tests still run in isolation.
"""

import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.llm.base import LLMProvider, LLMResult


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, plan_dict: dict):
        self._plan = plan_dict
        self._model = "fake-model"
        self.received_images = None
        self.received_prompt = None

    async def complete(self, system_prompt, user_prompt, **kwargs) -> LLMResult:
        # Record inputs so tests can assert images/prompt were forwarded.
        self.received_images = kwargs.get("images")
        self.received_prompt = user_prompt
        return LLMResult(text=json.dumps(self._plan), model=self._model, provider=self.name)

    async def embed(self, texts):
        raise NotImplementedError


@pytest_asyncio.fixture
async def client():
    # asyncpg connections are bound to the loop that created them; pytest-asyncio
    # uses a fresh loop per test, so dispose the shared engine to force new
    # connections on the current loop.
    from sqlalchemy import text

    from app.core.database import engine

    await engine.dispose()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Database not reachable for integration tests: {exc}")

    from app.main import app

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_full_flow(client, valid_plan_dict, monkeypatch):
    import uuid

    email = f"user_{uuid.uuid4().hex[:8]}@example.com"

    # Register
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "secret123", "full_name": "T"},
    )
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create a JIRA connection; secret must never come back.
    r = await client.post(
        "/api/connections",
        headers=headers,
        json={
            "name": "JIRA",
            "conn_type": "jira",
            "config": {"base_url": "https://x", "email": "a@b.com"},
            "secrets": {"api_token": "TOPSECRET"},
        },
    )
    assert r.status_code == 201, r.text
    conn = r.json()
    assert conn["has_secrets"] is True
    assert "TOPSECRET" not in json.dumps(conn)

    # List connections — still no secret leakage.
    r = await client.get("/api/connections", headers=headers)
    assert r.status_code == 200
    assert "TOPSECRET" not in r.text

    # Schema endpoint.
    r = await client.get("/api/planning/schema", headers=headers)
    assert r.status_code == 200
    assert r.json()["title"] == "ONAPlan"

    # Generate a plan using a fake provider.
    from app.api.routes import planning as planning_route

    monkeypatch.setattr(
        planning_route, "get_llm_provider", lambda: FakeProvider(valid_plan_dict)
    )

    context = {
        "jira_ticket_id": "LSC-1",
        "jira_summary": "Add field",
        "jira_description": "",
        "jira_acceptance_criteria": "",
        "jira_type": "Story",
        "jira_priority": "High",
        "sf_org_edition": "Enterprise",
        "lsc_modules": ["Intelligent Sales"],
        "installed_packages": [],
        "metadata_objects": ["Account"],
        "metadata_fields": [],
        "metadata_flows": [],
        "metadata_apex_classes": [],
        "metadata_permission_sets": [],
        "github_branch": "main",
        "github_recent_commits": [],
        "github_open_prs": [],
    }
    r = await client.post(
        "/api/planning/generate", headers=headers, json={"context": context}
    )
    assert r.status_code == 200, r.text
    plan = r.json()
    assert plan["jira_ticket"] == "LSC-1"
    assert plan["plan_json"]["deployment_risk"] == "Low"
    plan_id = plan["id"]

    # History lists the plan.
    r = await client.get("/api/planning/plans", headers=headers)
    assert r.status_code == 200
    assert any(p["id"] == plan_id for p in r.json())

    # Fetch single plan.
    r = await client.get(f"/api/planning/plans/{plan_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["plan_json"]["jira_ticket"] == "LSC-1"


@pytest.mark.asyncio
async def test_generate_rejects_invalid_llm_output(client, monkeypatch):
    import uuid

    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "secret123"},
    )
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    from app.api.routes import planning as planning_route

    class BadProvider(FakeProvider):
        async def complete(self, system_prompt, user_prompt, **kwargs):
            return LLMResult(text="not json at all", model="x", provider="bad")

    monkeypatch.setattr(
        planning_route, "get_llm_provider", lambda: BadProvider({})
    )
    monkeypatch.setattr("app.services.planner.settings.PLAN_MAX_RETRIES", 1)

    context = {"jira_ticket_id": "LSC-9"}
    r = await client.post(
        "/api/planning/generate", headers=headers, json={"context": context}
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["attempts"] >= 1
    assert detail["errors"]


# A minimal valid 1x1 PNG.
_PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d4944415478da6360000002000001e221bc330000000049454e44ae"
    "426082"
)


@pytest.mark.asyncio
async def test_generate_with_images_forwards_image_to_provider(
    client, valid_plan_dict, monkeypatch
):
    import uuid

    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "secret123"},
    )
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    from app.api.routes import planning as planning_route

    fake = FakeProvider(valid_plan_dict)
    monkeypatch.setattr(planning_route, "get_llm_provider", lambda: fake)

    context = {"jira_ticket_id": "LSC-1", "jira_summary": "Build UI"}
    r = await client.post(
        "/api/planning/generate-with-images",
        headers=headers,
        data={"context": json.dumps(context)},
        files=[("files", ("design.png", _PNG_1x1, "image/png"))],
    )
    assert r.status_code == 200, r.text
    assert r.json()["jira_ticket"] == "LSC-1"

    # The image must have reached the provider, and the prompt should mention
    # the attached design.
    assert fake.received_images is not None
    assert len(fake.received_images) == 1
    assert fake.received_images[0].media_type == "image/png"
    assert fake.received_images[0].data  # base64 payload present
    assert "DESIGN REFERENCE" in fake.received_prompt


@pytest.mark.asyncio
async def test_generate_with_images_rejects_bad_type(
    client, valid_plan_dict, monkeypatch
):
    import uuid

    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "secret123"},
    )
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    from app.api.routes import planning as planning_route

    monkeypatch.setattr(
        planning_route, "get_llm_provider", lambda: FakeProvider(valid_plan_dict)
    )

    context = {"jira_ticket_id": "LSC-2"}
    r = await client.post(
        "/api/planning/generate-with-images",
        headers=headers,
        data={"context": json.dumps(context)},
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )
    assert r.status_code == 400
    assert "Unsupported image type" in r.json()["detail"]


@pytest.mark.asyncio
async def test_generate_with_images_no_files_still_works(
    client, valid_plan_dict, monkeypatch
):
    import uuid

    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "secret123"},
    )
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    from app.api.routes import planning as planning_route

    fake = FakeProvider(valid_plan_dict)
    monkeypatch.setattr(planning_route, "get_llm_provider", lambda: fake)

    context = {"jira_ticket_id": "LSC-3", "jira_summary": "No design"}
    r = await client.post(
        "/api/planning/generate-with-images",
        headers=headers,
        data={"context": json.dumps(context)},
    )
    assert r.status_code == 200, r.text
    # No images -> provider receives images=None and no design block.
    assert fake.received_images is None
    assert "DESIGN REFERENCE" not in fake.received_prompt
