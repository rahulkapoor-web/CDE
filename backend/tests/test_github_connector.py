"""Tests for the GitHub connector's write path (branch create + commit files).

Uses an httpx MockTransport so no network calls are made. Asserts the Git Data
API call sequence: resolve base, create blobs + tree + commit, then create the
branch ref.
"""

import httpx
import pytest

from app.connectors.github import GitHubConnector


class _FakeGitHub:
    """Minimal in-memory GitHub Git Data API for one repo/branch."""

    def __init__(self, *, branch_exists: bool):
        self.branch_exists = branch_exists
        self.created_ref = None
        self.patched_ref = None
        self.blobs: list[str] = []
        self.tree_base = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = request.url
        path = url.path
        method = request.method

        if path == "/repos/o/r" and method == "GET":
            return httpx.Response(200, json={"default_branch": "main"})

        if path == "/repos/o/r/git/ref/heads/feature" and method == "GET":
            if self.branch_exists:
                return httpx.Response(
                    200, json={"object": {"sha": "branchsha"}}
                )
            return httpx.Response(404, json={"message": "Not Found"})

        if path == "/repos/o/r/git/ref/heads/main" and method == "GET":
            return httpx.Response(200, json={"object": {"sha": "mainsha"}})

        if path.startswith("/repos/o/r/git/commits/") and method == "GET":
            return httpx.Response(200, json={"tree": {"sha": "basetree"}})

        if path == "/repos/o/r/git/blobs" and method == "POST":
            self.blobs.append(request.content.decode())
            return httpx.Response(201, json={"sha": f"blob{len(self.blobs)}"})

        if path == "/repos/o/r/git/trees" and method == "POST":
            import json as _json

            self.tree_base = _json.loads(request.content)["base_tree"]
            return httpx.Response(201, json={"sha": "newtree"})

        if path == "/repos/o/r/git/commits" and method == "POST":
            return httpx.Response(
                201,
                json={
                    "sha": "newcommit",
                    "html_url": "https://github.com/o/r/commit/newcommit",
                },
            )

        if path == "/repos/o/r/git/refs" and method == "POST":
            import json as _json

            self.created_ref = _json.loads(request.content)
            return httpx.Response(201, json={})

        if path == "/repos/o/r/git/refs/heads/feature" and method == "PATCH":
            import json as _json

            self.patched_ref = _json.loads(request.content)
            return httpx.Response(200, json={})

        return httpx.Response(500, json={"path": path, "method": method})


@pytest.mark.asyncio
async def test_commit_files_creates_new_branch(monkeypatch):
    fake = _FakeGitHub(branch_exists=False)
    transport = httpx.MockTransport(fake.handler)

    orig_client = httpx.AsyncClient

    def _client(*args, **kwargs):
        kwargs["transport"] = transport
        return orig_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _client)

    conn = GitHubConnector(token="t", repo="o/r")
    result = await conn.commit_files(
        [("force-app/main/default/objects/Account/fields/X__c.field-meta.xml", "<x/>")],
        branch="feature",
        message="add field",
    )

    assert result.created_branch is True
    assert result.commit_sha == "newcommit"
    assert result.branch == "feature"
    assert fake.created_ref == {"ref": "refs/heads/feature", "sha": "newcommit"}
    # New tree was based on the base branch's tree.
    assert fake.tree_base == "basetree"
    assert len(fake.blobs) == 1


@pytest.mark.asyncio
async def test_commit_files_updates_existing_branch(monkeypatch):
    fake = _FakeGitHub(branch_exists=True)
    transport = httpx.MockTransport(fake.handler)

    orig_client = httpx.AsyncClient

    def _client(*args, **kwargs):
        kwargs["transport"] = transport
        return orig_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _client)

    conn = GitHubConnector(token="t", repo="o/r")
    result = await conn.commit_files(
        [("src/package.xml", "<Package/>")],
        branch="feature",
        message="update",
    )

    assert result.created_branch is False
    assert fake.patched_ref == {"sha": "newcommit", "force": False}


@pytest.mark.asyncio
async def test_commit_files_empty_raises():
    conn = GitHubConnector(token="t", repo="o/r")
    with pytest.raises(ValueError):
        await conn.commit_files([], branch="feature", message="x")
