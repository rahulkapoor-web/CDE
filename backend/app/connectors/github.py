"""GitHub connector for repo state (read) and committing plan artifacts (write).

Reads report branch/commit/PR state for planning context. Writes create a branch
and commit a set of files to it in a single commit via the Git Data API, so a
developer can review a diff and deploy from their own repo.
"""

from dataclasses import dataclass

import httpx

API = "https://api.github.com"


@dataclass
class CommitResult:
    """Outcome of committing plan artifacts to a branch."""

    branch: str
    commit_sha: str
    commit_url: str
    branch_url: str
    files: list[str]
    created_branch: bool


class GitHubConnector:
    def __init__(self, token: str, repo: str) -> None:
        self.token = token
        self.repo = repo  # owner/repo

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def test(self) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{API}/repos/{self.repo}", headers=self._headers())
            r.raise_for_status()
            data = r.json()
            return {"repo": data.get("full_name"), "default_branch": data.get("default_branch")}

    async def fetch_state(self, branch: str | None = None) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            repo_resp = await client.get(
                f"{API}/repos/{self.repo}", headers=self._headers()
            )
            repo_resp.raise_for_status()
            default_branch = repo_resp.json().get("default_branch", "main")
            ref = branch or default_branch

            commits_resp = await client.get(
                f"{API}/repos/{self.repo}/commits",
                params={"sha": ref, "per_page": 10},
                headers=self._headers(),
            )
            commits_resp.raise_for_status()
            commits = [
                f"{c['sha'][:7]} {c['commit']['message'].splitlines()[0]}"
                for c in commits_resp.json()
            ]

            prs_resp = await client.get(
                f"{API}/repos/{self.repo}/pulls",
                params={"state": "open", "per_page": 20},
                headers=self._headers(),
            )
            prs_resp.raise_for_status()
            prs = [f"#{p['number']} {p['title']}" for p in prs_resp.json()]

        return {
            "github_branch": ref,
            "github_recent_commits": commits,
            "github_open_prs": prs,
        }

    async def detect_format(self, branch: str | None = None) -> str:
        """Best-effort detection of the repo's Salesforce metadata layout.

        Returns ``"sdx"`` if the repo looks like an SFDX source-format project
        (a ``force-app`` / ``sfdx-project.json`` layout), ``"mdapi"`` if it looks
        like a classic Metadata API package (a top-level ``src/`` with a
        ``package.xml``), or ``"unknown"`` when neither is evident. Callers use
        this only as a default; the connection setting takes precedence.
        """
        async with httpx.AsyncClient(timeout=15) as client:
            repo_resp = await client.get(
                f"{API}/repos/{self.repo}", headers=self._headers()
            )
            repo_resp.raise_for_status()
            default_branch = repo_resp.json().get("default_branch", "main")
            ref = branch or default_branch

            tree_resp = await client.get(
                f"{API}/repos/{self.repo}/git/trees/{ref}",
                params={"recursive": "1"},
                headers=self._headers(),
            )
            if tree_resp.status_code != 200:
                return "unknown"
            paths = [
                t.get("path", "") for t in tree_resp.json().get("tree", [])
            ]

        return detect_format_from_paths(paths)

    async def commit_files(
        self,
        files: list[tuple[str, str]],
        *,
        branch: str,
        message: str,
        base_branch: str | None = None,
    ) -> CommitResult:
        """Commit ``files`` to ``branch`` in a single commit via the Git Data API.

        ``files`` is a list of ``(path, content)`` pairs. If ``branch`` does not
        exist it is created from ``base_branch`` (or the repo default). Existing
        files at the same paths are overwritten in the new commit; other files on
        the branch are preserved (the new tree uses the branch tip as its base).
        """
        if not files:
            raise ValueError("No files to commit.")

        headers = self._headers()
        async with httpx.AsyncClient(timeout=30) as client:
            repo_resp = await client.get(f"{API}/repos/{self.repo}", headers=headers)
            repo_resp.raise_for_status()
            default_branch = repo_resp.json().get("default_branch", "main")
            base = base_branch or default_branch

            # Resolve the base commit sha (from the target branch if it exists,
            # else from the base branch).
            created_branch = False
            head_resp = await client.get(
                f"{API}/repos/{self.repo}/git/ref/heads/{branch}",
                headers=headers,
            )
            if head_resp.status_code == 200:
                base_sha = head_resp.json()["object"]["sha"]
            else:
                base_ref_resp = await client.get(
                    f"{API}/repos/{self.repo}/git/ref/heads/{base}",
                    headers=headers,
                )
                base_ref_resp.raise_for_status()
                base_sha = base_ref_resp.json()["object"]["sha"]
                created_branch = True

            # Base commit -> base tree.
            base_commit_resp = await client.get(
                f"{API}/repos/{self.repo}/git/commits/{base_sha}",
                headers=headers,
            )
            base_commit_resp.raise_for_status()
            base_tree_sha = base_commit_resp.json()["tree"]["sha"]

            # Create blobs and assemble a new tree.
            tree_entries = []
            for path, content in files:
                blob_resp = await client.post(
                    f"{API}/repos/{self.repo}/git/blobs",
                    headers=headers,
                    json={"content": content, "encoding": "utf-8"},
                )
                blob_resp.raise_for_status()
                tree_entries.append(
                    {
                        "path": path.lstrip("/"),
                        "mode": "100644",
                        "type": "blob",
                        "sha": blob_resp.json()["sha"],
                    }
                )

            tree_resp = await client.post(
                f"{API}/repos/{self.repo}/git/trees",
                headers=headers,
                json={"base_tree": base_tree_sha, "tree": tree_entries},
            )
            tree_resp.raise_for_status()
            new_tree_sha = tree_resp.json()["sha"]

            commit_resp = await client.post(
                f"{API}/repos/{self.repo}/git/commits",
                headers=headers,
                json={
                    "message": message,
                    "tree": new_tree_sha,
                    "parents": [base_sha],
                },
            )
            commit_resp.raise_for_status()
            commit = commit_resp.json()
            new_commit_sha = commit["sha"]

            # Point the branch at the new commit (create or fast-forward update).
            if created_branch:
                ref_resp = await client.post(
                    f"{API}/repos/{self.repo}/git/refs",
                    headers=headers,
                    json={"ref": f"refs/heads/{branch}", "sha": new_commit_sha},
                )
                ref_resp.raise_for_status()
            else:
                ref_resp = await client.patch(
                    f"{API}/repos/{self.repo}/git/refs/heads/{branch}",
                    headers=headers,
                    json={"sha": new_commit_sha, "force": False},
                )
                ref_resp.raise_for_status()

        return CommitResult(
            branch=branch,
            commit_sha=new_commit_sha,
            commit_url=commit.get("html_url")
            or f"https://github.com/{self.repo}/commit/{new_commit_sha}",
            branch_url=f"https://github.com/{self.repo}/tree/{branch}",
            files=[p for p, _ in files],
            created_branch=created_branch,
        )


def detect_format_from_paths(paths: list[str]) -> str:
    """Classify a repo's Salesforce layout from a list of file paths.

    Pure helper (no I/O) so it is unit-testable. SFDX source format is detected
    by ``sfdx-project.json`` or a ``force-app/`` tree; classic MDAPI by a
    ``package.xml`` under a ``src/``-style root.
    """
    for p in paths:
        if p == "sfdx-project.json" or p.startswith("force-app/"):
            return "sfdx"
    for p in paths:
        if p.endswith("package.xml") or p.startswith("src/"):
            return "mdapi"
    return "unknown"
