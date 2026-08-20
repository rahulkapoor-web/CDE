import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Collapse,
  Descriptions,
  Divider,
  Empty,
  Input,
  List,
  Modal,
  Popconfirm,
  Result,
  Row,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Typography,
  message,
} from "antd";
import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { connectionsApi, planningApi } from "../services/api";
import { githubSteps, orgSteps } from "../types";
import type {
  ChecklistReviewResult,
  Connection,
  DeployResult,
  GithubCommitResult,
  Plan,
  PlanningContext,
  PlanStep,
} from "../types";
import { downloadFile, planToJson, planToMarkdown } from "../utils/download";

const { TextArea } = Input;

const { Title, Paragraph, Text } = Typography;

function errText(e: unknown, fallback: string): string {
  const anyErr = e as { response?: { data?: { detail?: unknown } } };
  const detail = anyErr?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return fallback;
}

const RISK_COLOR: Record<string, string> = {
  Low: "green",
  Medium: "orange",
  High: "red",
};

const REVIEW_COLOR: Record<string, string> = {
  pass: "green",
  partial: "orange",
  fail: "red",
};

const ITEM_STATUS_COLOR: Record<string, string> = {
  pass: "green",
  partial: "orange",
  fail: "red",
  not_applicable: "default",
};

const TYPE_COLOR: Record<string, string> = {
  Configuration: "blue",
  Apex: "geekblue",
  LWC: "purple",
  Flow: "cyan",
  PermissionSet: "gold",
  IntegrationSetup: "magenta",
  DataMigration: "volcano",
  Test: "green",
  Deploy: "red",
};

const AUTOMATION_COLOR: Record<string, string> = {
  Full: "green",
  Partial: "orange",
  Manual: "default",
};

function StepCard({ step }: { step: PlanStep }) {
  const managed = step.description.includes("MANAGED PACKAGE");
  const artifact = step.metadata_artifact;
  const deployable = !!artifact && (artifact.files?.length || 0) > 0;
  const [showArtifact, setShowArtifact] = useState(false);
  return (
    <Card size="small" style={{ marginBottom: 12 }}>
      <Space align="start" style={{ width: "100%", justifyContent: "space-between" }}>
        <Space wrap>
          <Tag>{step.step_number}</Tag>
          <Text strong>{step.title}</Text>
          <Tag color={TYPE_COLOR[step.type] || "default"}>{step.type}</Tag>
          <Tag>{step.environment}</Tag>
          <Tag color={AUTOMATION_COLOR[step.automation_feasibility]}>
            {step.automation_feasibility}
          </Tag>
          {deployable ? (
            <Tag color="green">Auto-deploy</Tag>
          ) : (
            <Tag color="default">Manual</Tag>
          )}
        </Space>
        <Text type="secondary">{step.estimated_minutes} min</Text>
      </Space>
      {managed && (
        <Alert
          type="warning"
          showIcon
          style={{ margin: "8px 0" }}
          message="Managed package field — changes may be overwritten on upgrade"
        />
      )}
      <Paragraph style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>{step.description}</Paragraph>
      <Descriptions size="small" column={1} bordered>
        <Descriptions.Item label="Acceptance check">{step.acceptance_check}</Descriptions.Item>
        {step.metadata_path && (
          <Descriptions.Item label="Metadata path">
            <Text code>{step.metadata_path}</Text>
          </Descriptions.Item>
        )}
        {step.lsc_guide_reference && (
          <Descriptions.Item label="LSC reference">{step.lsc_guide_reference}</Descriptions.Item>
        )}
        {step.dependencies.length > 0 && (
          <Descriptions.Item label="Depends on">
            {step.dependencies.join(", ")}
          </Descriptions.Item>
        )}
        {step.automation_notes && (
          <Descriptions.Item label="Automation notes">{step.automation_notes}</Descriptions.Item>
        )}
        {step.rollback && (
          <Descriptions.Item label="Rollback">{step.rollback}</Descriptions.Item>
        )}
      </Descriptions>
      {deployable && (
        <div style={{ marginTop: 8 }}>
          <Button size="small" onClick={() => setShowArtifact((v) => !v)}>
            {showArtifact ? "Hide" : "View"} deployable metadata (
            {artifact!.files.length} file
            {artifact!.files.length === 1 ? "" : "s"})
          </Button>
          {showArtifact && (
            <div style={{ marginTop: 8 }}>
              {artifact!.members.length > 0 && (
                <Paragraph style={{ marginBottom: 8 }}>
                  <Text type="secondary">Components: </Text>
                  {artifact!.members.map((m, i) => (
                    <Tag key={i}>
                      {m.type}: {m.name}
                    </Tag>
                  ))}
                </Paragraph>
              )}
              {artifact!.files.map((f, i) => (
                <div key={i} style={{ marginBottom: 8 }}>
                  <Text code>{f.path}</Text>
                  <pre
                    style={{
                      background: "#f6f6f6",
                      padding: 8,
                      borderRadius: 4,
                      maxHeight: 240,
                      overflow: "auto",
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {f.body}
                  </pre>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

const STATUS_COLOR: Record<string, string> = {
  generating: "processing",
  generation_failed: "red",
  refining: "processing",
  generated: "default",
  approved: "blue",
  deploying: "processing",
  deployed: "green",
  deploy_failed: "red",
};

/**
 * Build refine feedback from a failed deployment's structured errors so the AI
 * can fix the exact components Salesforce rejected. Returns "" when there is
 * nothing actionable (no result, succeeded, or no error detail).
 */
function deployErrorsToFeedback(result?: DeployResult | null): string {
  if (!result || result.succeeded) return "";
  const compErrors = result.component_errors || [];
  const testErrors = result.test_errors || [];
  const lines: string[] = [];
  for (const e of compErrors) {
    const file = String(e.file ?? e.fullName ?? "").trim();
    const msg = String(e.message ?? e.problem ?? "").trim();
    if (msg) lines.push(file ? `- ${file}: ${msg}` : `- ${msg}`);
  }
  for (const e of testErrors) {
    const name = String(e.name ?? e.methodName ?? "").trim();
    const msg = String(e.message ?? e.stackTrace ?? "").trim();
    if (msg) lines.push(name ? `- Test ${name}: ${msg}` : `- Test failure: ${msg}`);
  }
  if (!lines.length && result.error) lines.push(`- ${result.error}`);
  if (!lines.length && result.state_detail) lines.push(`- ${result.state_detail}`);
  if (!lines.length) return "";
  return (
    "The Salesforce deployment failed with the following errors. Fix ONLY the " +
    "components that caused these errors so the plan deploys cleanly, keeping " +
    "everything else unchanged:\n\n" +
    lines.join("\n") +
    "\n\nCorrect the offending metadata (e.g. invalid field references, missing " +
    "bundle files, malformed XML, or dependency ordering) using the org metadata " +
    "already provided as context. Do not invent fields or objects that are not in " +
    "the org."
  );
}

/**
 * Read-only view of the Salesforce org context captured when the plan was
 * generated. Reads from the persisted context_snapshot and tolerates older
 * snapshots with missing fields, so it never crashes the page.
 */
function OrgContextPanel({
  ctx,
  capturedAt,
}: {
  ctx?: Partial<PlanningContext> | null;
  capturedAt?: string | null;
}) {
  if (!ctx) return null;
  const list = (v?: string[]) => (Array.isArray(v) ? v : []);
  const layoutNames = ctx.existing_layouts
    ? Object.keys(ctx.existing_layouts)
    : [];

  const metaSections: Array<{ key: string; label: string; items: string[] }> = [
    { key: "objects", label: "Objects", items: list(ctx.metadata_objects) },
    { key: "fields", label: "Fields", items: list(ctx.metadata_fields) },
    { key: "flows", label: "Flows", items: list(ctx.metadata_flows) },
    { key: "apex", label: "Apex classes", items: list(ctx.metadata_apex_classes) },
    {
      key: "permsets",
      label: "Permission sets",
      items: list(ctx.metadata_permission_sets),
    },
    { key: "layouts", label: "Layouts", items: layoutNames },
  ];

  const hasAnything =
    ctx.sf_org_edition ||
    ctx.sf_api_version ||
    list(ctx.lsc_modules).length ||
    list(ctx.installed_packages).length ||
    metaSections.some((s) => s.items.length);

  if (!hasAnything) return null;

  return (
    <Card
      size="small"
      title="Org Context (at generation)"
      style={{ marginBottom: 16 }}
      extra={
        capturedAt ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            captured {new Date(capturedAt).toLocaleString()}
          </Text>
        ) : undefined
      }
    >
      <Paragraph type="secondary" style={{ marginBottom: 8, fontSize: 12 }}>
        Snapshot of the connected org the AI planned against. It may be stale if
        the org changed since generation — refine to re-ground on current state.
      </Paragraph>
      <Descriptions column={1} size="small" style={{ marginBottom: 8 }}>
        {ctx.sf_org_edition && (
          <Descriptions.Item label="Edition">
            {ctx.sf_org_edition}
          </Descriptions.Item>
        )}
        {ctx.sf_api_version && (
          <Descriptions.Item label="API version">
            {ctx.sf_api_version}
          </Descriptions.Item>
        )}
        {list(ctx.lsc_modules).length > 0 && (
          <Descriptions.Item label="LSC modules">
            {list(ctx.lsc_modules).map((m) => (
              <Tag key={m}>{m}</Tag>
            ))}
          </Descriptions.Item>
        )}
        {list(ctx.installed_packages).length > 0 && (
          <Descriptions.Item label="Installed packages">
            {list(ctx.installed_packages).map((m) => (
              <Tag key={m}>{m}</Tag>
            ))}
          </Descriptions.Item>
        )}
      </Descriptions>
      <Collapse
        size="small"
        items={metaSections
          .filter((s) => s.items.length > 0)
          .map((s) => ({
            key: s.key,
            label: `${s.label} (${s.items.length})`,
            children: (
              <div style={{ maxHeight: 220, overflow: "auto" }}>
                {s.items.map((it) => (
                  <Tag key={it} style={{ marginBottom: 4 }}>
                    {it}
                  </Tag>
                ))}
              </div>
            ),
          }))}
      />
    </Card>
  );
}

function DeployResultView({ result }: { result: DeployResult }) {
  const errors = result.component_errors || [];
  return (
    <div>
      <Space wrap style={{ marginBottom: 8 }}>
        <Tag color={result.succeeded ? "green" : "red"}>
          {result.state || (result.succeeded ? "Succeeded" : "Failed")}
        </Tag>
        {result.check_only && <Tag color="blue">Validation only (dry run)</Tag>}
        {result.components_deployed != null && (
          <Text type="secondary">
            {result.components_deployed}/{result.components_total} components
            deployed
          </Text>
        )}
      </Space>
      {result.state_detail && (
        <Paragraph type="secondary">{result.state_detail}</Paragraph>
      )}
      {result.error && <Alert type="error" showIcon message={result.error} />}
      {errors.length > 0 && (
        <List
          size="small"
          header={<Text strong>Component errors</Text>}
          dataSource={errors}
          renderItem={(e: Record<string, unknown>) => (
            <List.Item>
              <Text code>{String(e.file ?? "")}</Text> — {String(e.message ?? "")}
            </List.Item>
          )}
        />
      )}
    </div>
  );
}

export default function PlanDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(true);
  const [showJson, setShowJson] = useState(false);
  const [approving, setApproving] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [sfConnections, setSfConnections] = useState<Connection[]>([]);
  const [ghConnections, setGhConnections] = useState<Connection[]>([]);
  const [jiraConnections, setJiraConnections] = useState<Connection[]>([]);
  const [checklistConnections, setChecklistConnections] = useState<
    Connection[]
  >([]);
  const [deployModalOpen, setDeployModalOpen] = useState(false);
  const [selectedConnId, setSelectedConnId] = useState<number | undefined>();
  const [dryRunResult, setDryRunResult] = useState<DeployResult | null>(null);

  // Deploy-time selection (UI-only). null set = "not initialized yet".
  const [selectedSteps, setSelectedSteps] = useState<Set<number>>(new Set());
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set());

  // Post unit test plan to JIRA.
  const [jiraModalOpen, setJiraModalOpen] = useState(false);
  const [jiraConnId, setJiraConnId] = useState<number | undefined>();
  const [postingJira, setPostingJira] = useState(false);

  // Review against checklist.
  const [checklistModalOpen, setChecklistModalOpen] = useState(false);
  const [checklistConnId, setChecklistConnId] = useState<number | undefined>();
  const [reviewing, setReviewing] = useState(false);
  const [review, setReview] = useState<ChecklistReviewResult | null>(null);

  // Human-in-the-loop refinement.
  const [feedback, setFeedback] = useState("");
  const [refining, setRefining] = useState(false);

  // GitHub commit path.
  const [ghModalOpen, setGhModalOpen] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [ghConnId, setGhConnId] = useState<number | undefined>();
  const [ghFormat, setGhFormat] = useState<string | undefined>();
  const [ghBranch, setGhBranch] = useState("");
  const [ghResult, setGhResult] = useState<GithubCommitResult | null>(null);

  // Initial load.
  useEffect(() => {
    if (!id) return;
    planningApi
      .getPlan(Number(id))
      .then(setPlan)
      .finally(() => setLoading(false));
  }, [id]);

  // Generation and refinement run in the background; whenever the plan enters a
  // pending state (generating/refining), poll until it settles so the page
  // updates on its own. Keyed on plan?.status so triggering a refine (which
  // sets the plan to "refining" locally) starts polling without a reload.
  const pendingState =
    plan?.status === "generating" || plan?.status === "refining";
  useEffect(() => {
    if (!id || !pendingState) return;
    let cancelled = false;
    const timer = setInterval(async () => {
      const p = await planningApi.getPlan(Number(id));
      if (cancelled) return;
      setPlan(p);
    }, 3000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [id, pendingState]);

  useEffect(() => {
    connectionsApi
      .list()
      .then((all) => {
        setSfConnections(all.filter((c) => c.conn_type === "salesforce"));
        setGhConnections(all.filter((c) => c.conn_type === "github"));
        setJiraConnections(all.filter((c) => c.conn_type === "jira"));
        setChecklistConnections(
          all.filter((c) => c.conn_type === "checklist"),
        );
      })
      .catch(() => {
        setSfConnections([]);
        setGhConnections([]);
        setJiraConnections([]);
        setChecklistConnections([]);
      });
  }, []);

  // Preselect the checklist chosen at generation time (passed via nav state).
  useEffect(() => {
    const stateConnId = (location.state as { checklistConnId?: number } | null)
      ?.checklistConnId;
    if (stateConnId) setChecklistConnId(stateConnId);
  }, [location.state]);

  // Default deploy selection to everything deployable whenever the plan loads.
  const deployableSteps = useMemo<PlanStep[]>(
    () =>
      (plan?.plan_json.steps || []).filter(
        (s) => (s.metadata_artifact?.files?.length || 0) > 0,
      ),
    [plan],
  );

  useEffect(() => {
    if (!plan) return;
    setSelectedSteps(new Set(deployableSteps.map((s) => s.step_number)));
    setSelectedPaths(
      new Set(
        deployableSteps.flatMap((s) =>
          (s.metadata_artifact?.files || []).map((f) => f.path),
        ),
      ),
    );
  }, [plan, deployableSteps]);

  const handleApprove = async () => {
    if (!plan) return;
    setApproving(true);
    try {
      const updated = await planningApi.approve(plan.id);
      setPlan(updated);
      message.success("Plan approved. You can now deploy to a Salesforce org.");
    } catch (e) {
      message.error(errText(e, "Approval failed"));
    } finally {
      setApproving(false);
    }
  };

  const runDeploy = async (checkOnly: boolean) => {
    if (!plan || !selectedConnId) {
      message.warning("Select a Salesforce connection first.");
      return;
    }
    setDeploying(true);
    setDryRunResult(null);
    try {
      // Only send a selection when the reviewer narrowed it; otherwise deploy
      // everything (undefined = no filtering server-side).
      const allSteps = deployableSteps.map((s) => s.step_number);
      const allPaths = deployableSteps.flatMap((s) =>
        (s.metadata_artifact?.files || []).map((f) => f.path),
      );
      const stepsNarrowed = selectedSteps.size !== allSteps.length;
      const pathsNarrowed = selectedPaths.size !== allPaths.length;
      const selection =
        stepsNarrowed || pathsNarrowed
          ? {
              step_numbers: Array.from(selectedSteps),
              artifact_paths: Array.from(selectedPaths),
            }
          : undefined;
      const updated = await planningApi.deploy(
        plan.id,
        selectedConnId,
        checkOnly,
        selection,
      );
      if (checkOnly) {
        setDryRunResult(updated.deploy_result || null);
        message.success("Validation (dry run) complete.");
      } else {
        setPlan(updated);
        setDeployModalOpen(false);
        if (updated.status === "deployed") {
          message.success("Deployment succeeded.");
        } else {
          message.error("Deployment failed. See the result panel for details.");
        }
      }
    } catch (e) {
      message.error(errText(e, "Deployment failed"));
    } finally {
      setDeploying(false);
    }
  };

  const handleRefine = async () => {
    if (!plan) return;
    const fb = feedback.trim();
    if (!fb) {
      message.warning("Enter feedback describing the changes you want.");
      return;
    }
    await runRefine(fb);
  };

  const runRefine = async (fb: string) => {
    if (!plan) return;
    setRefining(true);
    try {
      // Refinement runs in the background; the API returns the plan in a
      // "refining" state immediately and the poll picks up the result. That
      // avoids the preview gateway aborting the long LLM call.
      const updated = await planningApi.refine(plan.id, fb);
      setPlan(updated);
      setFeedback("");
      message.success("Refining plan… this page updates when it's ready.");
    } catch (e) {
      message.error(errText(e, "Refinement failed"));
    } finally {
      setRefining(false);
    }
  };

  // Turn the last deployment's structured errors into refine feedback so the AI
  // fixes the exact components Salesforce rejected, grounded in the real error
  // messages rather than the reviewer having to retype them.
  const handleFixDeployErrors = async () => {
    if (!plan) return;
    const fb = deployErrorsToFeedback(plan.deploy_result);
    if (!fb) {
      message.warning("No deployment errors to fix.");
      return;
    }
    await runRefine(fb);
  };

  const runCommit = async () => {
    if (!plan || !ghConnId) {
      message.warning("Select a GitHub connection first.");
      return;
    }
    setCommitting(true);
    setGhResult(null);
    try {
      const result = await planningApi.commitToGithub(plan.id, {
        github_connection_id: ghConnId,
        branch: ghBranch.trim() || undefined,
        metadata_format: ghFormat,
      });
      setGhResult(result);
      message.success(
        `Committed ${result.files.length} file${result.files.length === 1 ? "" : "s"} to ${result.branch}.`,
      );
    } catch (e) {
      message.error(errText(e, "GitHub commit failed"));
    } finally {
      setCommitting(false);
    }
  };

  const handlePostTestPlan = async () => {
    if (!plan || !jiraConnId) {
      message.warning("Select a JIRA connection first.");
      return;
    }
    setPostingJira(true);
    try {
      const result = await planningApi.postTestPlanToJira(plan.id, jiraConnId);
      message.success(`Unit test plan posted to ${result.ticket_id}.`);
      setJiraModalOpen(false);
    } catch (e) {
      message.error(errText(e, "Posting to JIRA failed"));
    } finally {
      setPostingJira(false);
    }
  };

  const handleReviewChecklist = async () => {
    if (!plan || !checklistConnId) {
      message.warning("Select a checklist first.");
      return;
    }
    setReviewing(true);
    setReview(null);
    try {
      const result = await planningApi.reviewChecklist(plan.id, checklistConnId);
      setReview(result);
      const tone =
        result.overall === "pass"
          ? "success"
          : result.overall === "partial"
            ? "warning"
            : "error";
      message[tone](`Checklist review: ${result.overall.toUpperCase()}`);
    } catch (e) {
      message.error(errText(e, "Checklist review failed"));
    } finally {
      setReviewing(false);
    }
  };

  const toggleStep = (stepNumber: number, files: { path: string }[]) => {
    setSelectedSteps((prev) => {
      const next = new Set(prev);
      const on = !next.has(stepNumber);
      if (on) next.add(stepNumber);
      else next.delete(stepNumber);
      setSelectedPaths((paths) => {
        const np = new Set(paths);
        files.forEach((f) => (on ? np.add(f.path) : np.delete(f.path)));
        return np;
      });
      return next;
    });
  };

  const togglePath = (path: string, stepNumber: number) => {
    setSelectedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else {
        next.add(path);
        // Selecting any file implies the step is included.
        setSelectedSteps((s) => new Set(s).add(stepNumber));
      }
      return next;
    });
  };

  if (loading) return <Spin />;
  if (!plan) return <Empty description="Plan not found" />;

  // Background generation in progress: show a spinner and let the poll flip the
  // page to the finished plan (or the failure) on its own.
  if (plan.status === "generating") {
    return (
      <Result
        icon={<Spin size="large" />}
        title="Generating plan…"
        subTitle="The AI is drafting your plan. This usually takes a minute or two — this page updates automatically."
        extra={<Button onClick={() => navigate("/plans")}>← Back to plans</Button>}
      />
    );
  }

  // Background refinement in progress: the plan keeps its previous content, but
  // show a spinner so the reviewer waits for the refined version rather than
  // acting on the stale one. The poll flips the page back when it settles.
  if (plan.status === "refining") {
    return (
      <Result
        icon={<Spin size="large" />}
        title="Refining plan…"
        subTitle="The AI is revising the plan with your feedback. This usually takes a minute or two — this page updates automatically."
        extra={<Button onClick={() => navigate("/plans")}>← Back to plans</Button>}
      />
    );
  }

  if (plan.status === "generation_failed") {
    return (
      <Result
        status="error"
        title="Plan generation failed"
        subTitle={
          plan.generation_error ||
          "The AI could not produce a valid plan. Try again, and refine the ticket details if it keeps failing."
        }
        extra={[
          <Button key="retry" type="primary" onClick={() => navigate("/generate")}>
            Try again
          </Button>,
          <Button key="back" onClick={() => navigate("/plans")}>
            ← Back to plans
          </Button>,
        ]}
      />
    );
  }

  const p = plan.plan_json;
  const status = plan.status;
  const deployableCount = p.steps.filter(
    (s) => (s.metadata_artifact?.files?.length || 0) > 0,
  ).length;
  const manualCount = p.steps.length - deployableCount;

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Button onClick={() => navigate("/plans")}>← Back</Button>
        <Button
          onClick={() =>
            navigate("/generate")
          }
        >
          New Plan
        </Button>
        <Button
          onClick={() => downloadFile(`${p.plan_id}.json`, planToJson(p), "application/json")}
        >
          Export JSON
        </Button>
        <Button
          onClick={() => downloadFile(`${p.plan_id}.md`, planToMarkdown(p), "text/markdown")}
        >
          Export Markdown
        </Button>
        <Space>
          <span>Raw JSON</span>
          <Switch checked={showJson} onChange={setShowJson} />
        </Space>
      </Space>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap align="center" style={{ justifyContent: "space-between", width: "100%" }}>
          <Space wrap align="center">
            <Text strong>Status:</Text>
            <Tag color={STATUS_COLOR[status] || "default"}>{status}</Tag>
            <Text type="secondary">
              {deployableCount} auto-deploy · {manualCount} manual step
              {manualCount === 1 ? "" : "s"}
            </Text>
          </Space>
          <Space wrap>
            {status === "generated" && (
              <Popconfirm
                title="Approve this plan?"
                description="This marks the plan ready to deploy. No org changes happen yet."
                okText="Approve"
                onConfirm={handleApprove}
              >
                <Button type="primary" loading={approving}>
                  Approve (Go ahead)
                </Button>
              </Popconfirm>
            )}
            {(status === "approved" ||
              status === "deploy_failed" ||
              status === "deployed") && (
              <Button
                loading={committing}
                onClick={() => {
                  setGhResult(null);
                  setGhModalOpen(true);
                }}
                disabled={deployableCount === 0}
              >
                Commit to GitHub
              </Button>
            )}
            {(status === "approved" || status === "deploy_failed") && (
              <Button
                type="primary"
                loading={deploying}
                onClick={() => {
                  setDryRunResult(null);
                  setDeployModalOpen(true);
                }}
                disabled={deployableCount === 0}
              >
                {status === "deploy_failed" ? "Retry Deploy" : "Deploy to Salesforce"}
              </Button>
            )}
            {status === "deploying" && (
              <Button loading disabled>
                Deploying…
              </Button>
            )}
            {status === "deployed" && <Tag color="green">Deployed ✓</Tag>}
            <Button
              onClick={() => setJiraModalOpen(true)}
              disabled={!p.testing_requirements.unit_tests}
            >
              Post test plan to JIRA
            </Button>
            <Button
              loading={reviewing}
              onClick={() => setChecklistModalOpen(true)}
            >
              Review against checklist
            </Button>
          </Space>
        </Space>
        {plan.generation_error && (
          <Alert
            style={{ marginTop: 12 }}
            type="error"
            showIcon
            closable
            message="Last refinement failed"
            description={`${plan.generation_error} — the plan is unchanged. Adjust your feedback and try again.`}
          />
        )}
        {deployableCount === 0 && status !== "generated" && (
          <Alert
            style={{ marginTop: 12 }}
            type="info"
            showIcon
            message="This plan has no auto-deployable metadata"
            description="All steps are manual (e.g. out-of-box enablement). Follow each step's instructions to apply them by hand."
          />
        )}
        {plan.deploy_result && (
          <div style={{ marginTop: 12 }}>
            <Divider orientation="left" style={{ margin: "8px 0" }}>
              Last deployment result
            </Divider>
            <DeployResultView result={plan.deploy_result} />
            {deployErrorsToFeedback(plan.deploy_result) && status !== "deploying" && (
              <div style={{ marginTop: 8 }}>
                <Button
                  danger
                  loading={refining}
                  onClick={handleFixDeployErrors}
                >
                  Fix deploy errors with AI
                </Button>
                <Text type="secondary" style={{ marginLeft: 8 }}>
                  Feeds the errors above into the AI to correct the offending
                  components.
                </Text>
              </div>
            )}
          </div>
        )}
        {status !== "deploying" && (
          <div style={{ marginTop: 12 }}>
            <Divider orientation="left" style={{ margin: "8px 0" }}>
              Refine this plan
            </Divider>
            <Paragraph type="secondary" style={{ marginBottom: 8 }}>
              Describe changes and the AI will revise this plan in place.
              Refining resets it to <Tag>generated</Tag> for re-review.
            </Paragraph>
            <TextArea
              rows={3}
              placeholder="e.g. Remove the validation-rule step; the story only asks for the field. Add the field to the Compact Layout too."
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              disabled={refining}
            />
            <div style={{ marginTop: 8, textAlign: "right" }}>
              <Button
                type="primary"
                loading={refining}
                onClick={handleRefine}
                disabled={!feedback.trim()}
              >
                Refine with AI
              </Button>
            </div>
          </div>
        )}
      </Card>

      <Modal
        title="Deploy to Salesforce"
        open={deployModalOpen}
        onCancel={() => setDeployModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setDeployModalOpen(false)}>
            Cancel
          </Button>,
          <Button
            key="validate"
            loading={deploying}
            disabled={selectedPaths.size === 0}
            onClick={() => runDeploy(true)}
          >
            Validate (dry run)
          </Button>,
          <Button
            key="deploy"
            type="primary"
            loading={deploying}
            disabled={selectedPaths.size === 0}
            onClick={() => runDeploy(false)}
          >
            Deploy now
          </Button>,
        ]}
      >
        <Paragraph>
          Deploys {deployableCount} step
          {deployableCount === 1 ? "" : "s"} of metadata to the selected org via
          the Metadata API. Manual steps ({manualCount}) are not automated.
        </Paragraph>
        <Select
          style={{ width: "100%" }}
          placeholder="Select a Salesforce connection"
          value={selectedConnId}
          onChange={setSelectedConnId}
          options={sfConnections.map((c) => ({ value: c.id, label: c.name }))}
          notFoundContent="No Salesforce connections. Add one on the Connections page."
        />
        {deployableSteps.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <Divider orientation="left" style={{ margin: "8px 0" }}>
              Select what to deploy
            </Divider>
            <Paragraph type="secondary" style={{ marginBottom: 8 }}>
              Uncheck any step or file to exclude it from this deployment. This
              selection is not saved.
            </Paragraph>
            <Space direction="vertical" style={{ width: "100%" }} size="small">
              {deployableSteps.map((s) => {
                const files = s.metadata_artifact?.files || [];
                const stepChecked = selectedSteps.has(s.step_number);
                return (
                  <div
                    key={s.step_number}
                    style={{
                      border: "1px solid #f0f0f0",
                      borderRadius: 6,
                      padding: "8px 12px",
                    }}
                  >
                    <Checkbox
                      checked={stepChecked}
                      onChange={() => toggleStep(s.step_number, files)}
                    >
                      <Text strong>
                        Step {s.step_number}: {s.title}
                      </Text>
                    </Checkbox>
                    <div style={{ paddingLeft: 24, marginTop: 4 }}>
                      {files.map((f) => (
                        <div key={f.path}>
                          <Checkbox
                            checked={selectedPaths.has(f.path)}
                            onChange={() => togglePath(f.path, s.step_number)}
                          >
                            <Text code style={{ fontSize: 12 }}>
                              {f.path}
                            </Text>
                          </Checkbox>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </Space>
            {selectedPaths.size === 0 && (
              <Alert
                style={{ marginTop: 8 }}
                type="warning"
                showIcon
                message="Nothing selected — deploy is disabled."
              />
            )}
          </div>
        )}
        {dryRunResult && (
          <div style={{ marginTop: 16 }}>
            <Divider orientation="left" style={{ margin: "8px 0" }}>
              Validation result
            </Divider>
            <DeployResultView result={dryRunResult} />
          </div>
        )}
      </Modal>

      <Modal
        title="Commit to GitHub"
        open={ghModalOpen}
        onCancel={() => setGhModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setGhModalOpen(false)}>
            Close
          </Button>,
          <Button
            key="commit"
            type="primary"
            loading={committing}
            onClick={runCommit}
          >
            Commit to branch
          </Button>,
        ]}
      >
        <Paragraph>
          Commits {deployableCount} step
          {deployableCount === 1 ? "" : "s"} of metadata to a new branch in the
          selected repo so you can review a diff and deploy from your pipeline.
          No pull request is opened.
        </Paragraph>
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          <div>
            <Text type="secondary">GitHub connection</Text>
            <Select
              style={{ width: "100%" }}
              placeholder="Select a GitHub connection"
              value={ghConnId}
              onChange={setGhConnId}
              options={ghConnections.map((c) => ({ value: c.id, label: c.name }))}
              notFoundContent="No GitHub connections. Add one on the Connections page."
            />
          </div>
          <div>
            <Text type="secondary">Metadata format</Text>
            <Select
              style={{ width: "100%" }}
              placeholder="Auto-detect from repo (default)"
              value={ghFormat}
              onChange={setGhFormat}
              allowClear
              options={[
                { value: "sfdx", label: "SFDX source format (force-app/…)" },
                { value: "mdapi", label: "Metadata API format (src/ + package.xml)" },
              ]}
            />
          </div>
          <div>
            <Text type="secondary">Branch name (optional)</Text>
            <Input
              placeholder="Auto-generated from ticket (default)"
              value={ghBranch}
              onChange={(e) => setGhBranch(e.target.value)}
            />
          </div>
        </Space>
        {ghResult && (
          <div style={{ marginTop: 16 }}>
            <Divider orientation="left" style={{ margin: "8px 0" }}>
              Commit result
            </Divider>
            <Space direction="vertical" size="small">
              <Space wrap>
                <Tag color="green">{ghResult.metadata_format}</Tag>
                <Tag color={ghResult.created_branch ? "blue" : "default"}>
                  {ghResult.created_branch ? "Branch created" : "Branch updated"}
                </Tag>
                <Text>
                  {ghResult.files.length} file
                  {ghResult.files.length === 1 ? "" : "s"} committed
                </Text>
              </Space>
              <div>
                <Text strong>Branch: </Text>
                <a href={ghResult.branch_url} target="_blank" rel="noreferrer">
                  {ghResult.branch}
                </a>
              </div>
              <div>
                <Text strong>Commit: </Text>
                <a href={ghResult.commit_url} target="_blank" rel="noreferrer">
                  {ghResult.commit_sha.slice(0, 7)}
                </a>
              </div>
            </Space>
          </div>
        )}
      </Modal>

      <Modal
        title="Post unit test plan to JIRA"
        open={jiraModalOpen}
        onCancel={() => setJiraModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setJiraModalOpen(false)}>
            Cancel
          </Button>,
          <Button
            key="post"
            type="primary"
            loading={postingJira}
            disabled={!jiraConnId}
            onClick={handlePostTestPlan}
          >
            Post comment
          </Button>,
        ]}
      >
        <Paragraph>
          Adds the plan's unit test plan (and functional/regression/coverage
          notes) as a comment on <Tag color="blue">{p.jira_ticket}</Tag>.
        </Paragraph>
        <Select
          style={{ width: "100%" }}
          placeholder="Select a JIRA connection"
          value={jiraConnId}
          onChange={setJiraConnId}
          options={jiraConnections.map((c) => ({ value: c.id, label: c.name }))}
          notFoundContent="No JIRA connections. Add one on the Connections page."
        />
        <Divider orientation="left" style={{ margin: "12px 0 8px" }}>
          Preview
        </Divider>
        <pre
          style={{
            whiteSpace: "pre-wrap",
            background: "#fafafa",
            padding: 12,
            borderRadius: 6,
            maxHeight: 240,
            overflow: "auto",
            fontSize: 12,
          }}
        >
          {p.testing_requirements.unit_tests || "(No unit tests specified.)"}
        </pre>
      </Modal>

      <Modal
        title="Review plan against checklist"
        open={checklistModalOpen}
        onCancel={() => setChecklistModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setChecklistModalOpen(false)}>
            Close
          </Button>,
          <Button
            key="review"
            type="primary"
            loading={reviewing}
            disabled={!checklistConnId}
            onClick={handleReviewChecklist}
          >
            Run review
          </Button>,
        ]}
      >
        <Paragraph>
          Evaluates this plan against each item in the selected checklist and
          reports pass / fail / partial per item.
        </Paragraph>
        <Select
          style={{ width: "100%" }}
          placeholder="Select a checklist"
          value={checklistConnId}
          onChange={setChecklistConnId}
          options={checklistConnections.map((c) => ({
            value: c.id,
            label: c.name,
          }))}
          notFoundContent="No checklists. Add one on the Connections page."
        />
        {review && (
          <div style={{ marginTop: 16 }}>
            <Divider orientation="left" style={{ margin: "8px 0" }}>
              Result
            </Divider>
            <Space wrap style={{ marginBottom: 8 }}>
              <Text strong>Overall:</Text>
              <Tag color={REVIEW_COLOR[review.overall]}>
                {review.overall.toUpperCase()}
              </Tag>
              <Text type="secondary">{review.checklist_name}</Text>
            </Space>
            {review.summary && (
              <Paragraph type="secondary">{review.summary}</Paragraph>
            )}
            <List
              size="small"
              dataSource={review.results}
              renderItem={(r) => (
                <List.Item>
                  <Space align="start">
                    <Tag color={ITEM_STATUS_COLOR[r.status] || "default"}>
                      {r.status}
                    </Tag>
                    <div>
                      <Text>{r.item}</Text>
                      {r.finding && (
                        <div>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {r.finding}
                          </Text>
                        </div>
                      )}
                    </div>
                  </Space>
                </List.Item>
              )}
            />
          </div>
        )}
      </Modal>

      {showJson ? (
        <Card>
          <pre style={{ whiteSpace: "pre-wrap", maxHeight: "70vh", overflow: "auto" }}>
            {planToJson(p)}
          </pre>
        </Card>
      ) : (
        <Row gutter={16}>
          <Col span={16}>
            <Card>
              <Title level={4}>{p.summary}</Title>
              <Space wrap>
                <Tag color="blue">{p.jira_ticket}</Tag>
                <Tag>{p.change_classification}</Tag>
                <Tag color={RISK_COLOR[p.deployment_risk]}>Risk: {p.deployment_risk}</Tag>
                <Tag>Effort: {p.estimated_effort}</Tag>
              </Space>
              <Paragraph style={{ marginTop: 12 }} type="secondary">
                {p.risk_rationale}
              </Paragraph>
            </Card>

            {p.open_questions.length > 0 && (
              <Alert
                style={{ margin: "16px 0" }}
                type="info"
                showIcon
                message="Open Questions"
                description={
                  <ul style={{ margin: 0, paddingLeft: 20 }}>
                    {p.open_questions.map((q, i) => (
                      <li key={i}>{q}</li>
                    ))}
                  </ul>
                }
              />
            )}

            <Divider orientation="left">Steps</Divider>
            {p.steps.map((s) => (
              <StepCard key={s.step_number} step={s} />
            ))}
          </Col>

          <Col span={8}>
            {p.prerequisites.length > 0 && (
              <Card size="small" title="Prerequisites" style={{ marginBottom: 16 }}>
                <ul style={{ margin: 0, paddingLeft: 20 }}>
                  {p.prerequisites.map((q, i) => (
                    <li key={i}>{q}</li>
                  ))}
                </ul>
              </Card>
            )}

            {p.assumed_prerequisites?.length > 0 && (
              <Card
                size="small"
                title="Assumed prerequisites"
                style={{ marginBottom: 16 }}
              >
                <Paragraph type="secondary" style={{ marginBottom: 8 }}>
                  Assumed already present in the org. Not created or deployed by
                  this plan — confirm they exist before applying.
                </Paragraph>
                <ul style={{ margin: 0, paddingLeft: 20 }}>
                  {p.assumed_prerequisites.map((q, i) => (
                    <li key={i}>{q}</li>
                  ))}
                </ul>
              </Card>
            )}

            <Card size="small" title="Testing" style={{ marginBottom: 16 }}>
              <Descriptions column={1} size="small">
                <Descriptions.Item label="Unit tests">
                  {p.testing_requirements.unit_tests}
                </Descriptions.Item>
                <Descriptions.Item label="Functional">
                  {p.testing_requirements.functional_tests}
                </Descriptions.Item>
                <Descriptions.Item label="Regression">
                  {p.testing_requirements.regression_areas}
                </Descriptions.Item>
                <Descriptions.Item label="Min coverage">
                  {p.testing_requirements.minimum_code_coverage}%
                </Descriptions.Item>
              </Descriptions>
            </Card>

            <Card size="small" title="Deployment Sequence" style={{ marginBottom: 16 }}>
              <p>
                <Text strong>Connected org:</Text>{" "}
                {orgSteps(p.deployment_sequence).join(", ") || "—"}
              </p>
              <p>
                <Text strong>GitHub Actions:</Text>{" "}
                {githubSteps(p.deployment_sequence).join(", ") || "—"}
              </p>
            </Card>

            <OrgContextPanel
              ctx={plan.context_snapshot}
              capturedAt={plan.created_at}
            />

            {p.lsc_guide_references.length > 0 && (
              <Card size="small" title="LSC Guide References" style={{ marginBottom: 16 }}>
                {p.lsc_guide_references.map((r, i) => (
                  <div key={i} style={{ marginBottom: 8 }}>
                    <Text strong>
                      {r.module} → {r.section}
                    </Text>
                    <div>
                      <Text type="secondary">{r.page_or_url}</Text>
                    </div>
                    <div>{r.relevance}</div>
                  </div>
                ))}
              </Card>
            )}

            {p.post_deployment.length > 0 && (
              <Card size="small" title="Post-Deployment" style={{ marginBottom: 16 }}>
                <ul style={{ margin: 0, paddingLeft: 20 }}>
                  {p.post_deployment.map((q, i) => (
                    <li key={i}>{q}</li>
                  ))}
                </ul>
              </Card>
            )}

            {p.copilot_suggested_actions.length > 0 && (
              <Card size="small" title="Copilot Suggested Actions">
                <ul style={{ margin: 0, paddingLeft: 20 }}>
                  {p.copilot_suggested_actions.map((q, i) => (
                    <li key={i}>{q}</li>
                  ))}
                </ul>
              </Card>
            )}
          </Col>
        </Row>
      )}
    </>
  );
}
