# X-Ray test integration — design (not yet implemented)

Status: **planned, on hold.** This documents the intended design for two held
requests so they can be built later without re-deciding the approach:

1. Store the generated unit test script in JIRA X-Ray and assign it to a developer.
2. Store the test script in JIRA X-Ray.

Both depend on X-Ray (a JIRA test-management app). The current release only posts
the unit test plan as a plain JIRA comment (see `post-test-plan-jira`); X-Ray
issues are richer and require its dedicated API.

## Background

X-Ray models tests as JIRA issues of type **Test** with extra fields:

- Test **type**: Manual, Cucumber, or Generic/Unstructured.
- For Generic tests: an **unstructured definition** field holding the script text.
- For Manual tests: ordered **steps** (action / data / expected result).
- Tests link to requirements (the story) via a "tests"/"is tested by" issue link.

X-Ray Cloud and X-Ray Server/DC have **different APIs**:

- **X-Ray Cloud**: separate GraphQL API at `https://xray.cloud.getxray.app`,
  authenticated with a client-id/client-secret that is exchanged for a bearer
  token. Test issues are created via the normal JIRA Cloud REST API; X-Ray
  specifics (test type, steps, definition) are set via the GraphQL API.
- **X-Ray Server/DC**: REST API under `/rest/raven/2.0/` on the JIRA base URL,
  using the same JIRA auth (PAT/basic).

The connector must therefore branch on deployment type, mirroring how the
Salesforce connector branches on auth flow.

## Proposed data model

Reuse the existing JIRA connection; add optional X-Ray config/secrets rather than
a new connection type:

- `config.xray_deployment`: `"cloud" | "server"`.
- `config.xray_test_type`: default `"Generic"` (script in the definition field).
- `config.xray_project_key`: project to create Test issues in (defaults to the
  story's project).
- secrets `xray_client_id`, `xray_client_secret` (Cloud only).

## Proposed API surface

New endpoint, parallel to `post-test-plan-jira`:

```
POST /planning/plans/{plan_id}/create-xray-test
body: {
  jira_connection_id: int,
  assignee: str | null,          # JIRA accountId (Cloud) or username (Server)
  test_type: "Generic" | "Manual" | null,   # overrides connection default
  link_to_story: bool = true
}
-> { test_issue_key: str, url: str, linked: bool, assigned_to: str | null }
```

Flow:

1. Resolve the JIRA/X-Ray connection and its deployment type.
2. Create a Test issue:
   - Cloud: JIRA REST `POST /rest/api/3/issue` with `issuetype=Test`, then
     X-Ray GraphQL `updateUnstructuredTestDefinition` (Generic) or
     `updateTestSteps` (Manual).
   - Server: X-Ray REST `POST /rest/raven/2.0/import/test` or create the issue
     then `PUT /rest/raven/2.0/api/test/{key}` for the definition/steps.
3. Set the assignee (`assignee` field on issue create, or a follow-up
   `assign` call).
4. Link the Test to the story (`Test` "tests" `Story`).
5. Return the created key + browse URL.

## Source of the script

- **Generic test**: use `plan_json.testing_requirements.unit_tests` verbatim as
  the unstructured definition (same content posted as a comment today).
- **Manual test**: parse the unit-test text into steps. Better: extend the plan
  schema with an optional `unit_test_steps: [{action, data, expected}]` the LLM
  can populate, so Manual tests are first-class rather than parsed heuristically.

## Frontend

Add a "Create X-Ray test" action next to "Post test plan to JIRA" on the plan
detail page, opening a modal to pick the connection, test type, and assignee
(assignee list fetched via JIRA user search). Show the resulting Test issue key
as a link on success.

## Open questions (resolve before building)

- Cloud vs Server: which does the target org use? (drives the whole connector)
- One Test per plan, or one per acceptance criterion / per unit_tests block?
- Assignee identity: accountId (Cloud) vs username (Server) — needs a user
  picker backed by the right JIRA search endpoint.
- Idempotency: re-running should update the existing Test, not create duplicates
  (store the created key on the plan, or search by a stable label).

## Not doing now

No code, schema, connector, or endpoint changes are included in this release for
X-Ray. This file is the design record for the held items only.
