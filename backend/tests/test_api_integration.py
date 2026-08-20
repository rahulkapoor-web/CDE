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


async def _await_generation(client, headers, plan_id, timeout: float = 10.0) -> dict:
    """Poll a plan until background generation leaves the 'generating' state.

    Generation runs in a background task, so the POST returns a pending plan
    immediately. Tests wait here for the terminal state (generated or
    generation_failed) before asserting on the result.
    """
    import asyncio

    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        r = await client.get(f"/api/planning/plans/{plan_id}", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        if body["status"] != "generating":
            return body
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError(
                f"Plan {plan_id} stuck in 'generating' after {timeout}s"
            )
        await asyncio.sleep(0.05)


async def _await_refinement(client, headers, plan_id, timeout: float = 10.0) -> dict:
    """Poll a plan until background refinement leaves the 'refining' state."""
    import asyncio

    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        r = await client.get(f"/api/planning/plans/{plan_id}", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        if body["status"] != "refining":
            return body
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError(
                f"Plan {plan_id} stuck in 'refining' after {timeout}s"
            )
        await asyncio.sleep(0.05)


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
    # Generation is async: the POST returns a pending plan immediately.
    assert plan["status"] == "generating"
    plan_id = plan["id"]

    # Wait for background generation to finish, then assert on the result.
    plan = await _await_generation(client, headers, plan_id)
    assert plan["status"] == "generated"
    assert plan["jira_ticket"] == "LSC-1"
    assert plan["plan_json"]["deployment_risk"] == "Low"

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
    # The POST accepts the request; the invalid LLM output surfaces later as a
    # generation_failed status with the error recorded on the plan.
    assert r.status_code == 200, r.text
    plan_id = r.json()["id"]
    plan = await _await_generation(client, headers, plan_id)
    assert plan["status"] == "generation_failed"
    assert plan["generation_error"]


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
    assert r.json()["status"] == "generating"
    plan = await _await_generation(client, headers, r.json()["id"])
    assert plan["status"] == "generated"
    assert plan["jira_ticket"] == "LSC-1"

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
    assert r.json()["status"] == "generating"
    plan = await _await_generation(client, headers, r.json()["id"])
    assert plan["status"] == "generated"
    # No images -> provider receives images=None and no design block.
    assert fake.received_images is None
    assert "DESIGN REFERENCE" not in fake.received_prompt


def _plan_dict_with_artifact(base: dict) -> dict:
    """Return a copy of the plan whose first step carries deployable metadata."""
    import copy

    data = copy.deepcopy(base)
    data["steps"][0]["metadata_artifact"] = {
        "files": [
            {"path": "objects/Account/fields/ACV__c.field-meta.xml", "body": "<CustomField/>"}
        ],
        "members": [{"type": "CustomField", "name": "Account.ACV__c"}],
        "api_version": "60.0",
    }
    return data


async def _register(client) -> dict:
    import uuid

    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(
        "/api/auth/register", json={"email": email, "password": "secret123"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _create_sf_connection(client, headers) -> int:
    r = await client.post(
        "/api/connections",
        headers=headers,
        json={
            "name": "Prod SF",
            "conn_type": "salesforce",
            "config": {
                "auth_flow": "client_credentials",
                "instance_url": "https://example.my.salesforce.com",
                "is_sandbox": False,
            },
            "secrets": {"client_id": "cid", "client_secret": "csecret"},
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _generate_plan(client, headers) -> int:
    r = await client.post(
        "/api/planning/generate",
        headers=headers,
        json={"context": {"jira_ticket_id": "LSC-1"}},
    )
    assert r.status_code == 200, r.text
    plan_id = r.json()["id"]
    # Generation is async; wait for it to finish so callers get a ready plan.
    body = await _await_generation(client, headers, plan_id)
    assert body["status"] == "generated", body
    return plan_id


@pytest.mark.asyncio
async def test_approve_then_deploy_success(client, valid_plan_dict, monkeypatch):
    headers = await _register(client)

    from app.api.routes import planning as planning_route

    plan_dict = _plan_dict_with_artifact(valid_plan_dict)
    monkeypatch.setattr(
        planning_route, "get_llm_provider", lambda: FakeProvider(plan_dict)
    )
    plan_id = await _generate_plan(client, headers)
    conn_id = await _create_sf_connection(client, headers)

    # Deploy before approval is rejected.
    r = await client.post(
        f"/api/planning/plans/{plan_id}/deploy",
        headers=headers,
        json={"salesforce_connection_id": conn_id},
    )
    assert r.status_code == 409

    # Approve (the "Go ahead" gate).
    r = await client.post(f"/api/planning/plans/{plan_id}/approve", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"
    assert r.json()["approved_at"] is not None

    # Stub the connector + deploy so no real org is contacted.
    class _Connector:
        is_sandbox = False

        def connect(self):
            return object()

    monkeypatch.setattr(
        planning_route, "salesforce_from_connection", lambda conn: _Connector()
    )

    def _fake_deploy(sf, plan, *, is_sandbox, check_only=False, **kw):
        return "0AfXYZ", {
            "state": "Succeeded",
            "succeeded": True,
            "component_errors": [],
            "async_id": "0AfXYZ",
            "package_files": ["objects/Account/fields/ACV__c.field-meta.xml"],
            "steps_included": [1],
        }

    monkeypatch.setattr(planning_route, "deploy_plan", _fake_deploy)

    r = await client.post(
        f"/api/planning/plans/{plan_id}/deploy",
        headers=headers,
        json={"salesforce_connection_id": conn_id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "deployed"
    assert body["deploy_async_id"] == "0AfXYZ"
    assert body["deploy_result"]["succeeded"] is True


@pytest.mark.asyncio
async def test_deploy_failure_marks_plan_failed(client, valid_plan_dict, monkeypatch):
    headers = await _register(client)
    from app.api.routes import planning as planning_route

    plan_dict = _plan_dict_with_artifact(valid_plan_dict)
    monkeypatch.setattr(
        planning_route, "get_llm_provider", lambda: FakeProvider(plan_dict)
    )
    plan_id = await _generate_plan(client, headers)
    conn_id = await _create_sf_connection(client, headers)

    await client.post(f"/api/planning/plans/{plan_id}/approve", headers=headers)

    class _Connector:
        is_sandbox = True

        def connect(self):
            return object()

    monkeypatch.setattr(
        planning_route, "salesforce_from_connection", lambda conn: _Connector()
    )

    def _boom(*a, **k):
        raise RuntimeError("org unreachable")

    monkeypatch.setattr(planning_route, "deploy_plan", _boom)

    r = await client.post(
        f"/api/planning/plans/{plan_id}/deploy",
        headers=headers,
        json={"salesforce_connection_id": conn_id},
    )
    assert r.status_code == 502

    # The plan is now marked deploy_failed and can be retried.
    r = await client.get(f"/api/planning/plans/{plan_id}", headers=headers)
    assert r.json()["status"] == "deploy_failed"
    assert r.json()["deploy_result"]["succeeded"] is False


@pytest.mark.asyncio
async def test_deploy_without_metadata_returns_422(client, valid_plan_dict, monkeypatch):
    headers = await _register(client)
    from app.api.routes import planning as planning_route

    # Plan has NO metadata_artifact on any step.
    monkeypatch.setattr(
        planning_route, "get_llm_provider", lambda: FakeProvider(valid_plan_dict)
    )
    plan_id = await _generate_plan(client, headers)
    conn_id = await _create_sf_connection(client, headers)
    await client.post(f"/api/planning/plans/{plan_id}/approve", headers=headers)

    r = await client.post(
        f"/api/planning/plans/{plan_id}/deploy",
        headers=headers,
        json={"salesforce_connection_id": conn_id},
    )
    assert r.status_code == 422
    assert "no deployable metadata" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_check_only_deploy_does_not_change_status(
    client, valid_plan_dict, monkeypatch
):
    headers = await _register(client)
    from app.api.routes import planning as planning_route

    plan_dict = _plan_dict_with_artifact(valid_plan_dict)
    monkeypatch.setattr(
        planning_route, "get_llm_provider", lambda: FakeProvider(plan_dict)
    )
    plan_id = await _generate_plan(client, headers)
    conn_id = await _create_sf_connection(client, headers)
    await client.post(f"/api/planning/plans/{plan_id}/approve", headers=headers)

    class _Connector:
        is_sandbox = True

        def connect(self):
            return object()

    monkeypatch.setattr(
        planning_route, "salesforce_from_connection", lambda conn: _Connector()
    )
    monkeypatch.setattr(
        planning_route,
        "deploy_plan",
        lambda *a, **k: ("0AfDRY", {"state": "Succeeded", "succeeded": True}),
    )

    r = await client.post(
        f"/api/planning/plans/{plan_id}/deploy",
        headers=headers,
        json={"salesforce_connection_id": conn_id, "check_only": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Dry run reports a result but leaves the plan approved (not deployed).
    assert body["status"] == "approved"
    assert body["deploy_result"]["check_only"] is True


class RefiningProvider(FakeProvider):
    """Returns the base plan first, then a modified plan on the refine call."""

    def __init__(self, first: dict, second: dict):
        super().__init__(first)
        self._second = second
        self._calls = 0
        self.last_refine_prompt = None

    async def complete(self, system_prompt, user_prompt, **kwargs):
        self._calls += 1
        if self._calls == 1:
            return LLMResult(
                text=json.dumps(self._plan), model="m", provider=self.name
            )
        self.last_refine_prompt = user_prompt
        return LLMResult(
            text=json.dumps(self._second), model="m", provider=self.name
        )

    async def embed(self, texts):
        raise NotImplementedError


@pytest.mark.asyncio
async def test_refine_of_generated_plan_stays_generated(
    client, valid_plan_dict, monkeypatch
):
    import copy

    headers = await _register(client)
    from app.api.routes import planning as planning_route

    first = _plan_dict_with_artifact(valid_plan_dict)
    second = copy.deepcopy(first)
    second["summary"] = "Refined: only the field, no extra rule."

    provider = RefiningProvider(first, second)
    monkeypatch.setattr(planning_route, "get_llm_provider", lambda: provider)

    plan_id = await _generate_plan(client, headers)

    # Empty feedback is rejected.
    r = await client.post(
        f"/api/planning/plans/{plan_id}/refine",
        headers=headers,
        json={"feedback": "   "},
    )
    assert r.status_code == 422

    # Refining a never-approved plan keeps it in `generated` for review.
    # Refinement is async: the POST returns the plan in `refining` immediately.
    r = await client.post(
        f"/api/planning/plans/{plan_id}/refine",
        headers=headers,
        json={"feedback": "Drop the validation rule; keep only the field."},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "refining"
    body = await _await_refinement(client, headers, plan_id)
    assert body["status"] == "generated"
    assert body["approved_at"] is None
    assert body["plan_json"]["summary"].startswith("Refined:")
    assert "Drop the validation rule" in provider.last_refine_prompt
    assert "CURRENT PLAN JSON" in provider.last_refine_prompt


@pytest.mark.asyncio
async def test_refine_of_approved_plan_stays_approved(
    client, valid_plan_dict, monkeypatch
):
    """Refining an already-approved plan (e.g. to fix a failed deploy) must keep
    it approved so the reviewer can redeploy without re-approving."""
    import copy

    headers = await _register(client)
    from app.api.routes import planning as planning_route

    first = _plan_dict_with_artifact(valid_plan_dict)
    second = copy.deepcopy(first)
    second["summary"] = "Refined: fixed the failing component."

    provider = RefiningProvider(first, second)
    monkeypatch.setattr(planning_route, "get_llm_provider", lambda: provider)

    plan_id = await _generate_plan(client, headers)

    r = await client.post(f"/api/planning/plans/{plan_id}/approve", headers=headers)
    assert r.json()["status"] == "approved"

    r = await client.post(
        f"/api/planning/plans/{plan_id}/refine",
        headers=headers,
        json={"feedback": "Fix the LWC bundle so it deploys."},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "refining"
    body = await _await_refinement(client, headers, plan_id)
    assert body["status"] == "approved"  # stays approved for redeploy
    assert body["approved_at"] is not None
    assert body["plan_json"]["summary"].startswith("Refined:")
    # Prior deploy execution state is cleared so the refined content redeploys.
    assert body["deploy_result"] is None


@pytest.mark.asyncio
async def test_refine_failure_restores_prior_status(
    client, valid_plan_dict, monkeypatch
):
    """A failed refinement leaves the plan on its prior status with the content
    unchanged and the error recorded, rather than stuck in 'refining'."""
    import copy

    headers = await _register(client)
    from app.api.routes import planning as planning_route

    first = _plan_dict_with_artifact(valid_plan_dict)

    class RefineThenFail(FakeProvider):
        def __init__(self, plan_dict):
            super().__init__(plan_dict)
            self._calls = 0

        async def complete(self, system_prompt, user_prompt, **kwargs):
            self._calls += 1
            if self._calls == 1:
                return LLMResult(
                    text=json.dumps(self._plan), model="m", provider=self.name
                )
            # Refinement produces unparseable output -> generation error.
            return LLMResult(text="not json", model="m", provider=self.name)

    provider = RefineThenFail(first)
    monkeypatch.setattr(planning_route, "get_llm_provider", lambda: provider)
    monkeypatch.setattr("app.services.planner.settings.PLAN_MAX_RETRIES", 0)

    plan_id = await _generate_plan(client, headers)
    prev = copy.deepcopy(
        (await client.get(f"/api/planning/plans/{plan_id}", headers=headers)).json()
    )

    r = await client.post(
        f"/api/planning/plans/{plan_id}/refine",
        headers=headers,
        json={"feedback": "make it better"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "refining"

    body = await _await_refinement(client, headers, plan_id)
    # Restored to the pre-refine status with the original content intact.
    assert body["status"] == prev["status"] == "generated"
    assert body["plan_json"] == prev["plan_json"]
    assert body["generation_error"]


async def _create_gh_connection(client, headers) -> int:
    r = await client.post(
        "/api/connections",
        headers=headers,
        json={
            "name": "GH",
            "conn_type": "github",
            "config": {"repo": "o/r", "metadata_format": "sfdx"},
            "secrets": {"token": "ghtoken"},
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_commit_to_github_requires_approval(
    client, valid_plan_dict, monkeypatch
):
    headers = await _register(client)
    from app.api.routes import planning as planning_route

    plan_dict = _plan_dict_with_artifact(valid_plan_dict)
    monkeypatch.setattr(
        planning_route, "get_llm_provider", lambda: FakeProvider(plan_dict)
    )
    plan_id = await _generate_plan(client, headers)
    gh_id = await _create_gh_connection(client, headers)

    # Not approved yet -> 409.
    r = await client.post(
        f"/api/planning/plans/{plan_id}/commit-github",
        headers=headers,
        json={"github_connection_id": gh_id},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_commit_to_github_success(client, valid_plan_dict, monkeypatch):
    headers = await _register(client)
    from app.api.routes import planning as planning_route
    from app.connectors.github import CommitResult

    plan_dict = _plan_dict_with_artifact(valid_plan_dict)
    monkeypatch.setattr(
        planning_route, "get_llm_provider", lambda: FakeProvider(plan_dict)
    )
    plan_id = await _generate_plan(client, headers)
    gh_id = await _create_gh_connection(client, headers)
    await client.post(f"/api/planning/plans/{plan_id}/approve", headers=headers)

    captured = {}

    class _GH:
        async def detect_format(self, base):
            return "mdapi"

        async def commit_files(self, files, *, branch, message, base_branch=None):
            captured["files"] = files
            captured["branch"] = branch
            return CommitResult(
                branch=branch,
                commit_sha="abc1234def",
                commit_url="https://github.com/o/r/commit/abc1234def",
                branch_url=f"https://github.com/o/r/tree/{branch}",
                files=[p for p, _ in files],
                created_branch=True,
            )

    monkeypatch.setattr(
        planning_route, "github_from_connection", lambda conn, repo=None: _GH()
    )

    # Explicit format overrides the connection/detection.
    r = await client.post(
        f"/api/planning/plans/{plan_id}/commit-github",
        headers=headers,
        json={"github_connection_id": gh_id, "metadata_format": "sfdx"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["metadata_format"] == "sfdx"
    assert body["created_branch"] is True
    assert body["commit_sha"] == "abc1234def"
    assert body["files"]
    # The fixture already uses a source-format (-meta.xml) path, which is
    # preserved on commit.
    assert any("ACV__c.field-meta.xml" in f for f in body["files"])
    assert captured["branch"].startswith("ona/")


@pytest.mark.asyncio
async def test_commit_to_github_rejects_non_github_connection(
    client, valid_plan_dict, monkeypatch
):
    headers = await _register(client)
    from app.api.routes import planning as planning_route

    plan_dict = _plan_dict_with_artifact(valid_plan_dict)
    monkeypatch.setattr(
        planning_route, "get_llm_provider", lambda: FakeProvider(plan_dict)
    )
    plan_id = await _generate_plan(client, headers)
    sf_id = await _create_sf_connection(client, headers)
    await client.post(f"/api/planning/plans/{plan_id}/approve", headers=headers)

    r = await client.post(
        f"/api/planning/plans/{plan_id}/commit-github",
        headers=headers,
        json={"github_connection_id": sf_id},
    )
    assert r.status_code == 400


async def _create_jira_connection(client, headers) -> int:
    r = await client.post(
        "/api/connections",
        headers=headers,
        json={
            "name": "JIRA",
            "conn_type": "jira",
            "config": {"base_url": "https://x.atlassian.net", "email": "e@x.com"},
            "secrets": {"api_token": "tok"},
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _create_checklist_connection(client, headers, content) -> int:
    r = await client.post(
        "/api/connections",
        headers=headers,
        json={
            "name": "LSC checklist",
            "conn_type": "checklist",
            "config": {"content": content},
            "secrets": {},
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_post_test_plan_to_jira(client, valid_plan_dict, monkeypatch):
    headers = await _register(client)
    from app.api.routes import planning as planning_route

    monkeypatch.setattr(
        planning_route, "get_llm_provider", lambda: FakeProvider(valid_plan_dict)
    )
    plan_id = await _generate_plan(client, headers)
    jira_id = await _create_jira_connection(client, headers)

    captured = {}

    class _FakeJira:
        async def add_comment(self, ticket_id, body):
            captured["ticket_id"] = ticket_id
            captured["body"] = body
            return {"id": "999", "url": f"https://x/browse/{ticket_id}"}

    monkeypatch.setattr(
        planning_route, "jira_from_connection", lambda conn: _FakeJira()
    )

    r = await client.post(
        f"/api/planning/plans/{plan_id}/post-test-plan-jira",
        headers=headers,
        json={"jira_connection_id": jira_id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["comment_id"] == "999"
    # The posted body contains the plan's unit test content.
    assert "Unit Test Plan" in captured["body"]


@pytest.mark.asyncio
async def test_post_test_plan_rejects_non_jira_connection(
    client, valid_plan_dict, monkeypatch
):
    headers = await _register(client)
    from app.api.routes import planning as planning_route

    monkeypatch.setattr(
        planning_route, "get_llm_provider", lambda: FakeProvider(valid_plan_dict)
    )
    plan_id = await _generate_plan(client, headers)
    sf_id = await _create_sf_connection(client, headers)

    r = await client.post(
        f"/api/planning/plans/{plan_id}/post-test-plan-jira",
        headers=headers,
        json={"jira_connection_id": sf_id},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_review_against_checklist(client, valid_plan_dict, monkeypatch):
    headers = await _register(client)
    from app.api.routes import planning as planning_route

    monkeypatch.setattr(
        planning_route, "get_llm_provider", lambda: FakeProvider(valid_plan_dict)
    )
    plan_id = await _generate_plan(client, headers)
    checklist_id = await _create_checklist_connection(
        client, headers, "- All fields have FLS\n- No hardcoded IDs"
    )

    async def _fake_review(provider, plan_json, checklist_text):
        return {
            "overall": "partial",
            "summary": "one gap",
            "results": [
                {"item": "All fields have FLS", "status": "pass", "finding": "ok"},
                {"item": "No hardcoded IDs", "status": "fail", "finding": "found"},
            ],
        }

    monkeypatch.setattr(
        planning_route, "review_plan_against_checklist", _fake_review
    )

    r = await client.post(
        f"/api/planning/plans/{plan_id}/review-checklist",
        headers=headers,
        json={"checklist_connection_id": checklist_id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["overall"] == "partial"
    assert body["checklist_name"] == "LSC checklist"
    assert len(body["results"]) == 2


@pytest.mark.asyncio
async def test_review_rejects_empty_checklist(
    client, valid_plan_dict, monkeypatch
):
    headers = await _register(client)
    from app.api.routes import planning as planning_route

    monkeypatch.setattr(
        planning_route, "get_llm_provider", lambda: FakeProvider(valid_plan_dict)
    )
    plan_id = await _generate_plan(client, headers)
    checklist_id = await _create_checklist_connection(client, headers, "   ")

    r = await client.post(
        f"/api/planning/plans/{plan_id}/review-checklist",
        headers=headers,
        json={"checklist_connection_id": checklist_id},
    )
    assert r.status_code == 422


class _FakeSfConnector:
    is_sandbox = True

    def connect(self):
        return object()

    def list_layouts(self, object_names=None):
        return []

    def fetch_layouts(self, names, api_version="60.0"):
        return {}


@pytest.mark.asyncio
async def test_deploy_with_step_subset(client, valid_plan_dict, monkeypatch):
    headers = await _register(client)
    from app.api.routes import planning as planning_route

    plan_dict = _plan_dict_with_artifact(valid_plan_dict)
    monkeypatch.setattr(
        planning_route, "get_llm_provider", lambda: FakeProvider(plan_dict)
    )
    plan_id = await _generate_plan(client, headers)
    conn_id = await _create_sf_connection(client, headers)
    await client.post(f"/api/planning/plans/{plan_id}/approve", headers=headers)

    monkeypatch.setattr(
        planning_route,
        "salesforce_from_connection",
        lambda conn: _FakeSfConnector(),
    )

    captured = {}

    def _fake_deploy(sf, plan_schema, *, is_sandbox, check_only=False, **kw):
        from app.services.deployer import build_package_zip

        pkg = build_package_zip(plan_schema)
        captured["files"] = pkg.file_paths
        return ("ASYNC1", {"succeeded": True, "state": "Succeeded"})

    monkeypatch.setattr(planning_route, "deploy_plan", _fake_deploy)

    # Select only step 1 + its file.
    r = await client.post(
        f"/api/planning/plans/{plan_id}/deploy",
        headers=headers,
        json={
            "salesforce_connection_id": conn_id,
            "check_only": True,
            "step_numbers": [1],
            "artifact_paths": [
                "objects/Account/fields/ACV__c.field-meta.xml"
            ],
        },
    )
    assert r.status_code == 200, r.text
    assert captured["files"] == [
        "objects/Account/fields/ACV__c.field-meta.xml"
    ]


@pytest.mark.asyncio
async def test_deploy_empty_selection_returns_422(
    client, valid_plan_dict, monkeypatch
):
    headers = await _register(client)
    from app.api.routes import planning as planning_route

    plan_dict = _plan_dict_with_artifact(valid_plan_dict)
    monkeypatch.setattr(
        planning_route, "get_llm_provider", lambda: FakeProvider(plan_dict)
    )
    plan_id = await _generate_plan(client, headers)
    conn_id = await _create_sf_connection(client, headers)
    await client.post(f"/api/planning/plans/{plan_id}/approve", headers=headers)

    monkeypatch.setattr(
        planning_route,
        "salesforce_from_connection",
        lambda conn: _FakeSfConnector(),
    )

    r = await client.post(
        f"/api/planning/plans/{plan_id}/deploy",
        headers=headers,
        json={
            "salesforce_connection_id": conn_id,
            "check_only": True,
            "step_numbers": [],
            "artifact_paths": [],
        },
    )
    assert r.status_code == 422
