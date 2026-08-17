"""JIRA connector using the REST API (Cloud/Server basic auth or PAT)."""

import httpx


class JiraConnector:
    def __init__(self, base_url: str, email: str | None, api_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.api_token = api_token

    def _auth(self):
        # Cloud uses email + API token (basic). Server PAT can pass email=None.
        if self.email:
            return (self.email, self.api_token)
        return None

    def _headers(self) -> dict:
        headers = {"Accept": "application/json"}
        if not self.email:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    async def test(self) -> dict:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(
                f"{self.base_url}/rest/api/2/myself",
                auth=self._auth(),
                headers=self._headers(),
            )
            r.raise_for_status()
            data = _require_json(r)
            return {"account": data.get("displayName") or data.get("name", "unknown")}

    async def fetch_ticket(self, ticket_id: str) -> dict:
        fields = "summary,description,issuetype,priority,customfield_10000"
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            r = await client.get(
                f"{self.base_url}/rest/api/2/issue/{ticket_id}",
                params={"fields": fields},
                auth=self._auth(),
                headers=self._headers(),
            )
            r.raise_for_status()
            issue = _require_json(r)
        f = issue.get("fields", {})
        description = f.get("description") or ""
        if isinstance(description, dict):  # ADF (Cloud) — flatten text nodes.
            description = _flatten_adf(description)
        ac = f.get("customfield_10000") or ""
        if isinstance(ac, dict):
            ac = _flatten_adf(ac)
        return {
            "jira_ticket_id": issue.get("key", ticket_id),
            "jira_summary": f.get("summary", ""),
            "jira_description": description,
            "jira_acceptance_criteria": ac,
            "jira_type": (f.get("issuetype") or {}).get("name", ""),
            "jira_priority": (f.get("priority") or {}).get("name", ""),
        }


def _require_json(response: httpx.Response) -> dict:
    """Parse JSON, or raise a clear error when JIRA returned HTML.

    A common failure mode is an auth redirect to a login page: the request
    succeeds (200) but returns HTML, not the expected JSON. Surface that as a
    helpful message instead of a raw JSON decode error.
    """
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        raise ValueError(
            "JIRA returned a non-JSON response "
            f"(content-type: {content_type or 'unknown'}). This usually means the "
            "base URL is wrong or the credentials/token are invalid (redirected to "
            "a login page). Verify the base URL (e.g. https://your-org.atlassian.net) "
            "and the email/API token."
        )
    return response.json()


def _flatten_adf(node: dict) -> str:
    """Flatten Atlassian Document Format to plain text."""
    parts: list[str] = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("type") == "text":
                parts.append(n.get("text", ""))
            for child in n.get("content", []) or []:
                walk(child)
        elif isinstance(n, list):
            for child in n:
                walk(child)

    walk(node)
    return " ".join(p for p in parts if p).strip()
