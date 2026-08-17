import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  Empty,
  Row,
  Space,
  Spin,
  Switch,
  Tag,
  Typography,
} from "antd";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { planningApi } from "../services/api";
import type { Plan, PlanStep } from "../types";
import { downloadFile, planToJson, planToMarkdown } from "../utils/download";

const { Title, Paragraph, Text } = Typography;

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
    </Card>
  );
}

export default function PlanDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(true);
  const [showJson, setShowJson] = useState(false);

  useEffect(() => {
    if (!id) return;
    planningApi
      .getPlan(Number(id))
      .then(setPlan)
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <Spin />;
  if (!plan) return <Empty description="Plan not found" />;

  const p = plan.plan_json;

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
