"""JIRA connector using the REST API (Cloud/Server basic auth or PAT)."""

import base64
import logging

import httpx

logger = logging.getLogger(__name__)

# Field names commonly used for acceptance criteria, matched case-insensitively
# against the instance's field catalogue. The AC field is a custom field whose
# id (customfield_XXXXX) differs per JIRA instance, so it must be resolved by
# name rather than hardcoded.
_AC_FIELD_NAMES = (
    "acceptance criteria",
    "acceptance criterion",
    "acceptance",
)

# Attachment limits mirror the design-image upload limits enforced by the API.
_MAX_ATTACH_IMAGES = 4
_MAX_ATTACH_BYTES = 5 * 1024 * 1024  # 5 MB
_IMAGE_MIME_PREFIX = "image/"
_ALLOWED_ATTACH_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


class JiraConnector:
    def __init__(
        self,
        base_url: str,
        email: str | None,
        api_token: str,
        acceptance_field: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.api_token = api_token
        # Optional explicit field id (e.g. "customfield_10101") or field name
        # override from the connection config; takes precedence over auto-detect.
        self.acceptance_field = (acceptance_field or "").strip() or None

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

    async def add_comment(self, ticket_id: str, body: str) -> dict:
        """Add a comment to an issue. Returns ``{"id": ..., "url": ...}``.

        Uses the v2 REST API which accepts a plain-text ``body`` on both JIRA
        Cloud and Server/Data Center, avoiding ADF construction.
        """
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            r = await client.post(
                f"{self.base_url}/rest/api/2/issue/{ticket_id}/comment",
                json={"body": body},
                auth=self._auth(),
                headers={**self._headers(), "Content-Type": "application/json"},
            )
            r.raise_for_status()
            data = _require_json(r)
            comment_id = data.get("id")
            return {
                "id": comment_id,
                "url": f"{self.base_url}/browse/{ticket_id}"
                + (f"?focusedCommentId={comment_id}" if comment_id else ""),
            }

    async def _acceptance_field_candidates(
        self, client: httpx.AsyncClient
    ) -> list[str]:
        """Return candidate field ids that may hold acceptance criteria.

        A JIRA instance can have many acceptance-related fields (e.g. "Acceptance
        Criteria", "Acceptance Criteria (text)", "UAT Acceptance", ...). We can't
        know which one a given ticket uses from the catalogue alone, so we return
        an ORDERED list of candidates and let the caller pick the one that is
        actually populated on the issue.

        An explicit config override (field id) is returned as the sole candidate.
        A config override by name is placed first. The Development/devstatus field
        is never included.
        """
        override = self.acceptance_field
        if override and override.startswith("customfield_"):
            return [override]

        try:
            r = await client.get(
                f"{self.base_url}/rest/api/2/field",
                auth=self._auth(),
                headers=self._headers(),
            )
            r.raise_for_status()
            fields = _require_json_list(r)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not list JIRA fields to resolve AC field: %s", exc)
            return []

        exact: list[str] = []
        override_matches: list[str] = []
        contains_criteria: list[str] = []
        contains_acceptance: list[str] = []
        override_cf = (override or "").casefold()

        for f in fields:
            name = str(f.get("name", "")).casefold()
            fid = str(f.get("id", ""))
            if not fid or fid == "development" or name == "development":
                continue
            if override_cf and name == override_cf:
                override_matches.append(fid)
                continue
            if name in _AC_FIELD_NAMES:
                exact.append(fid)
            elif "acceptance criteria" in name:
                contains_criteria.append(fid)
            elif "acceptance" in name:
                contains_acceptance.append(fid)

        # Order: name override -> exact "acceptance criteria" -> names containing
        # "acceptance criteria" -> names containing "acceptance". De-duplicated.
        ordered: list[str] = []
        for group in (
            override_matches,
            exact,
            contains_criteria,
            contains_acceptance,
        ):
            for fid in group:
                if fid not in ordered:
                    ordered.append(fid)
        return ordered

    async def fetch_ticket(self, ticket_id: str) -> dict:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            ac_candidates = await self._acceptance_field_candidates(client)

            # Request real issue fields plus every AC candidate and attachments,
            # then pick the candidate actually populated on this ticket.
            # Explicitly avoid the devstatus/"development" field.
            field_list = [
                "summary",
                "description",
                "issuetype",
                "priority",
                "attachment",
                *ac_candidates,
            ]

            r = await client.get(
                f"{self.base_url}/rest/api/2/issue/{ticket_id}",
                params={"fields": ",".join(field_list)},
                auth=self._auth(),
                headers=self._headers(),
            )
            r.raise_for_status()
            issue = _require_json(r)

            f = issue.get("fields", {})
            description = f.get("description") or ""
            if isinstance(description, dict):  # ADF (Cloud) — flatten text nodes.
                description = _flatten_adf(description)

            ac = _pick_acceptance_value(f, ac_candidates)

            images = await self._fetch_attachments(client, f.get("attachment") or [])

        return {
            "jira_ticket_id": issue.get("key", ticket_id),
            "jira_summary": f.get("summary", ""),
            "jira_description": _sanitize_text(description),
            "jira_acceptance_criteria": ac,
            "jira_type": (f.get("issuetype") or {}).get("name", ""),
            "jira_priority": (f.get("priority") or {}).get("name", ""),
            "jira_images": images,
        }

    async def _fetch_attachments(
        self, client: httpx.AsyncClient, attachments: list
    ) -> list[dict]:
        """Download image attachments and return them as base64 upload payloads.

        Each item: {filename, media_type, data (base64)}. Non-image attachments
        and anything over the size limit are skipped; capped at
        ``_MAX_ATTACH_IMAGES``.
        """
        out: list[dict] = []
        for att in attachments:
            if len(out) >= _MAX_ATTACH_IMAGES:
                break
            if not isinstance(att, dict):
                continue
            mime = str(att.get("mimeType", ""))
            if not mime.startswith(_IMAGE_MIME_PREFIX):
                continue
            if mime not in _ALLOWED_ATTACH_TYPES:
                continue
            size = att.get("size")
            if isinstance(size, int) and size > _MAX_ATTACH_BYTES:
                continue
            content_url = att.get("content")
            if not content_url:
                continue
            try:
                resp = await client.get(
                    content_url,
                    auth=self._auth(),
                    headers={"Accept": "*/*", **_bearer_only(self._headers())},
                    follow_redirects=True,
                )
                resp.raise_for_status()
                data = resp.content
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to download JIRA attachment %s: %s",
                    att.get("filename"),
                    exc,
                )
                continue
            if not data or len(data) > _MAX_ATTACH_BYTES:
                continue
            out.append(
                {
                    "filename": att.get("filename") or "attachment",
                    "media_type": mime,
                    "data": base64.b64encode(data).decode("ascii"),
                }
            )
        return out


def _bearer_only(headers: dict) -> dict:
    """Keep only an Authorization bearer header (for PAT auth on downloads)."""
    return {k: v for k, v in headers.items() if k == "Authorization"}


def _coerce_field_value(value) -> str:
    """Normalize a JIRA field value to plain text.

    Handles: ADF dict (Cloud), plain string (Server wiki markup), option objects
    ({"value": ...}), and lists of any of these. Empty lists/None -> "".
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        if value.get("type") == "doc" or "content" in value:
            return _flatten_adf(value)
        # Option/select-style field.
        for key in ("value", "name", "displayName"):
            if isinstance(value.get(key), str):
                return value[key].strip()
        return ""
    if isinstance(value, list):
        parts = [_coerce_field_value(v) for v in value]
        return "\n".join(p for p in parts if p).strip()
    return ""


def _pick_acceptance_value(fields: dict, candidate_ids: list[str]) -> str:
    """Return the first candidate AC field that is actually populated.

    Values are normalized and sanitized (bean/devstatus junk dropped). This is
    what fixes blank AC on instances with several acceptance-* fields where the
    catalogue-name match lands on an empty one.
    """
    for fid in candidate_ids:
        if fid not in fields:
            continue
        text = _sanitize_text(_coerce_field_value(fields.get(fid)))
        if text:
            return text
    return ""


def _sanitize_text(value) -> str:
    """Guard against non-text field values leaking into context.

    Some JIRA fields (notably the Development/devstatus field) serialize as Java
    bean ``toString`` output like ``{summaryBean=...devstatus...}``. If a value
    is not a plain string, or is obviously such bean junk, drop it.
    """
    if not isinstance(value, str):
        return ""
    stripped = value.strip()
    lowered = stripped.casefold()
    if (
        "devstatus" in lowered
        or "summarybean" in lowered
        or "pullrequestoverall" in lowered
    ):
        return ""
    return stripped


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


def _require_json_list(response: httpx.Response) -> list:
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        raise ValueError("JIRA field catalogue returned a non-JSON response.")
    data = response.json()
    return data if isinstance(data, list) else []


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
