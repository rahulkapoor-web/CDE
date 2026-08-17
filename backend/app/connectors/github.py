"""GitHub connector for repo state (branch, recent commits, open PRs)."""

import httpx

API = "https://api.github.com"


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
