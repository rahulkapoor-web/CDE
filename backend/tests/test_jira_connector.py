"""Tests for the JIRA connector: acceptance-criteria resolution + attachments.

Uses an httpx MockTransport so no network calls are made. The key regression:
never treat the Development/devstatus field as acceptance criteria, and resolve
the real AC custom field by name (or config override) since its id varies per
instance.
"""

import base64

import httpx
import pytest

from app.connectors.jira import (
    JiraConnector,
    _coerce_field_value,
    _flatten_adf,
    _sanitize_text,
)

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

# A realistic field catalogue: AC lives in customfield_10101, and there is a
# Development field (the devstatus junk source) that must be ignored.
_FIELDS = [
    {"id": "summary", "name": "Summary"},
    {"id": "development", "name": "Development"},
    {"id": "customfield_10000", "name": "Development"},  # devstatus alias
    {"id": "customfield_10101", "name": "Acceptance Criteria"},
]


def _make_handler(
    *,
    fields=_FIELDS,
    issue_fields=None,
    attachments=None,
    attachment_bytes=_PNG,
):
    issue_fields = issue_fields or {}
    attachments = attachments or []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/rest/api/2/field"):
            return httpx.Response(
                200, json=fields, headers={"content-type": "application/json"}
            )
        if "/rest/api/2/issue/" in path:
            body = {
                "key": "LSC-1",
                "fields": {
                    "summary": "Add fields",
                    "description": "desc",
                    "issuetype": {"name": "Story"},
                    "priority": {"name": "High"},
                    "attachment": attachments,
                    **issue_fields,
                },
            }
            return httpx.Response(
                200, json=body, headers={"content-type": "application/json"}
            )
        # Attachment content download.
        if "/attachment/content/" in path or path.endswith(".png"):
            return httpx.Response(
                200,
                content=attachment_bytes,
                headers={"content-type": "image/png"},
            )
        return httpx.Response(404, json={}, headers={"content-type": "application/json"})

    return handler


@pytest.fixture
def patch_httpx(monkeypatch):
    def _apply(handler):
        transport = httpx.MockTransport(handler)
        orig = httpx.AsyncClient

        def _client(*args, **kwargs):
            kwargs["transport"] = transport
            return orig(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", _client)

    return _apply


@pytest.mark.asyncio
async def test_resolves_acceptance_criteria_by_name(patch_httpx):
    handler = _make_handler(
        issue_fields={"customfield_10101": "Field visible on Account layout."}
    )
    patch_httpx(handler)

    conn = JiraConnector("https://x.atlassian.net", "e@x.com", "tok")
    data = await conn.fetch_ticket("LSC-1")

    assert data["jira_acceptance_criteria"] == "Field visible on Account layout."
    assert data["jira_summary"] == "Add fields"


@pytest.mark.asyncio
async def test_devstatus_field_never_used_as_acceptance(patch_httpx):
    # Even if the devstatus bean string leaks into the resolved field, it is
    # sanitized away rather than shown as acceptance criteria.
    junk = (
        "{summaryBean=com.atlassian.jira.plugin.devstatus.rest.SummaryBean@1"
        "[summary={pullrequest=...PullRequestOverallBean...}]}"
    )
    handler = _make_handler(issue_fields={"customfield_10101": junk})
    patch_httpx(handler)

    conn = JiraConnector("https://x.atlassian.net", "e@x.com", "tok")
    data = await conn.fetch_ticket("LSC-1")
    assert data["jira_acceptance_criteria"] == ""


@pytest.mark.asyncio
async def test_picks_populated_ac_field_when_multiple_exist(patch_httpx):
    # Instance has several acceptance-* fields; the exact "Acceptance Criteria"
    # is empty ([]), but "Acceptance Criteria (text)" holds the real value.
    fields = [
        {"id": "customfield_11131", "name": "Acceptance Criteria"},
        {"id": "customfield_11143", "name": "Acceptance Criteria (text)"},
        {"id": "customfield_12802", "name": "UAT Acceptance"},
    ]
    handler = _make_handler(
        fields=fields,
        issue_fields={
            "customfield_11131": [],  # empty exact-name match
            "customfield_11143": "The real acceptance criteria text.",
            "customfield_12802": "unrelated",
        },
    )
    patch_httpx(handler)

    conn = JiraConnector("https://x.atlassian.net", "e@x.com", "tok")
    data = await conn.fetch_ticket("LSC-1")
    assert data["jira_acceptance_criteria"] == "The real acceptance criteria text."


@pytest.mark.asyncio
async def test_config_override_field_id_used(patch_httpx):
    fields = [{"id": "customfield_99999", "name": "Custom AC"}]
    handler = _make_handler(
        fields=fields,
        issue_fields={"customfield_99999": "Override AC text."},
    )
    patch_httpx(handler)

    conn = JiraConnector(
        "https://x.atlassian.net",
        "e@x.com",
        "tok",
        acceptance_field="customfield_99999",
    )
    data = await conn.fetch_ticket("LSC-1")
    assert data["jira_acceptance_criteria"] == "Override AC text."


@pytest.mark.asyncio
async def test_no_acceptance_field_yields_empty(patch_httpx):
    handler = _make_handler(fields=[{"id": "summary", "name": "Summary"}])
    patch_httpx(handler)

    conn = JiraConnector("https://x.atlassian.net", "e@x.com", "tok")
    data = await conn.fetch_ticket("LSC-1")
    assert data["jira_acceptance_criteria"] == ""


@pytest.mark.asyncio
async def test_image_attachments_downloaded_as_base64(patch_httpx):
    attachments = [
        {
            "filename": "mock.png",
            "mimeType": "image/png",
            "size": len(_PNG),
            "content": "https://x.atlassian.net/rest/api/2/attachment/content/1",
        },
        {  # non-image, skipped
            "filename": "spec.pdf",
            "mimeType": "application/pdf",
            "size": 10,
            "content": "https://x.atlassian.net/secure/attachment/2/spec.pdf",
        },
    ]
    handler = _make_handler(
        issue_fields={"customfield_10101": "AC"}, attachments=attachments
    )
    patch_httpx(handler)

    conn = JiraConnector("https://x.atlassian.net", "e@x.com", "tok")
    data = await conn.fetch_ticket("LSC-1")

    imgs = data["jira_images"]
    assert len(imgs) == 1
    assert imgs[0]["filename"] == "mock.png"
    assert imgs[0]["media_type"] == "image/png"
    assert base64.b64decode(imgs[0]["data"]) == _PNG


@pytest.mark.asyncio
async def test_oversized_attachment_skipped(patch_httpx):
    attachments = [
        {
            "filename": "big.png",
            "mimeType": "image/png",
            "size": 6 * 1024 * 1024,  # over 5 MB
            "content": "https://x.atlassian.net/rest/api/2/attachment/content/1",
        }
    ]
    handler = _make_handler(
        issue_fields={"customfield_10101": "AC"}, attachments=attachments
    )
    patch_httpx(handler)

    conn = JiraConnector("https://x.atlassian.net", "e@x.com", "tok")
    data = await conn.fetch_ticket("LSC-1")
    assert data["jira_images"] == []


@pytest.mark.asyncio
async def test_add_comment_posts_body_and_returns_url(patch_httpx, monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/comment") and request.method == "POST":
            import json

            captured["path"] = request.url.path
            captured["body"] = json.loads(request.content.decode())
            return httpx.Response(
                201,
                json={"id": "10500"},
                headers={"content-type": "application/json"},
            )
        return httpx.Response(
            404, json={}, headers={"content-type": "application/json"}
        )

    patch_httpx(handler)
    conn = JiraConnector("https://x.atlassian.net", "e@x.com", "tok")
    result = await conn.add_comment("LSC-1", "Unit test plan here")

    assert captured["path"] == "/rest/api/2/issue/LSC-1/comment"
    assert captured["body"] == {"body": "Unit test plan here"}
    assert result["id"] == "10500"
    assert "LSC-1" in result["url"]
    assert "focusedCommentId=10500" in result["url"]


@pytest.mark.asyncio
async def test_add_comment_server_uses_bearer_auth(patch_httpx):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(
            201, json={"id": "1"}, headers={"content-type": "application/json"}
        )

    patch_httpx(handler)
    # email=None -> Server/DC PAT bearer auth.
    conn = JiraConnector("https://jira.example.com", None, "PAT123")
    await conn.add_comment("LSC-2", "hi")
    assert seen["auth"] == "Bearer PAT123"


def test_sanitize_text_drops_bean_junk():
    assert _sanitize_text("normal text") == "normal text"
    assert _sanitize_text("x SummaryBean devstatus y") == ""
    assert _sanitize_text(None) == ""


def test_coerce_field_value_shapes():
    assert _coerce_field_value("  text  ") == "text"
    assert _coerce_field_value([]) == ""
    assert _coerce_field_value(None) == ""
    assert _coerce_field_value({"value": "High"}) == "High"
    assert _coerce_field_value(["a", "b"]) == "a\nb"
    adf = {"type": "doc", "content": [{"type": "text", "text": "Hi"}]}
    assert _coerce_field_value(adf) == "Hi"


def test_flatten_adf():
    adf = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "World"}]},
        ],
    }
    assert _flatten_adf(adf) == "Hello World"
