import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  Empty,
  List,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Typography,
  message,
} from "antd";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { connectionsApi, planningApi } from "../services/api";
import type { Connection, DeployResult, Plan, PlanStep } from "../types";
import { downloadFile, planToJson, planToMarkdown } from "../utils/download";

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
  generated: "default",
  approved: "blue",
  deploying: "processing",
  deployed: "green",
  deploy_failed: "red",
};

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
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(true);
  const [showJson, setShowJson] = useState(false);
  const [approving, setApproving] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [sfConnections, setSfConnections] = useState<Connection[]>([]);
  const [deployModalOpen, setDeployModalOpen] = useState(false);
  const [selectedConnId, setSelectedConnId] = useState<number | undefined>();
  const [dryRunResult, setDryRunResult] = useState<DeployResult | null>(null);

  useEffect(() => {
    if (!id) return;
    planningApi
      .getPlan(Number(id))
      .then(setPlan)
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    connectionsApi
      .list()
      .then((all) => setSfConnections(all.filter((c) => c.conn_type === "salesforce")))
      .catch(() => setSfConnections([]));
  }, []);

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
      const updated = await planningApi.deploy(plan.id, selectedConnId, checkOnly);
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

  if (loading) return <Spin />;
  if (!plan) return <Empty description="Plan not found" />;

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
          </Space>
        </Space>
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
            onClick={() => runDeploy(true)}
          >
            Validate (dry run)
          </Button>,
          <Button
            key="deploy"
            type="primary"
            loading={deploying}
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
        {dryRunResult && (
          <div style={{ marginTop: 16 }}>
            <Divider orientation="left" style={{ margin: "8px 0" }}>
              Validation result
            </Divider>
            <DeployResultView result={dryRunResult} />
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
                <Text strong>Sandbox:</Text>{" "}
                {p.deployment_sequence.sandbox_steps.join(", ") || "—"}
              </p>
              <p>
                <Text strong>Production:</Text>{" "}
                {p.deployment_sequence.production_steps.join(", ") || "—"}
              </p>
              <p>
                <Text strong>GitHub Actions:</Text>{" "}
                {p.deployment_sequence.github_actions_steps.join(", ") || "—"}
              </p>
            </Card>

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
