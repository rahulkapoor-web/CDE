import { InboxOutlined } from "@ant-design/icons";
import {
  Button,
  Card,
  Col,
  Divider,
  Form,
  Input,
  Row,
  Select,
  Space,
  Spin,
  Upload,
  message,
} from "antd";
import type { UploadFile } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { connectionsApi, planningApi } from "../services/api";
import type { Connection, PlanningContext } from "../types";

const ACCEPTED_IMAGE_TYPES = [
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/gif",
];
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_IMAGES = 4;

const { TextArea } = Input;

export default function GeneratePage() {
  const navigate = useNavigate();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [context, setContext] = useState<PlanningContext | null>(null);
  const [gathering, setGathering] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [designFiles, setDesignFiles] = useState<UploadFile[]>([]);
  // Chosen at gather time; not part of the context. Carried to the plan page so
  // the plan can be reviewed against it after generation.
  const [checklistConnId, setChecklistConnId] = useState<number | null>(null);
  const [gatherForm] = Form.useForm();
  const [ctxForm] = Form.useForm();

  useEffect(() => {
    connectionsApi.list().then(setConnections);
  }, []);

  const byType = (t: string) =>
    connections
      .filter((c) => c.conn_type === t)
      .map((c) => ({ value: c.id, label: c.name }));

  async function onGather() {
    const values = await gatherForm.validateFields().catch(() => null);
    if (!values) return;
    // checklist selection is not a gather-context input; keep it client-side.
    const { checklist_connection_id, ...gatherValues } = values;
    setChecklistConnId(
      checklist_connection_id != null ? Number(checklist_connection_id) : null,
    );
    setGathering(true);
    try {
      const ctx = await planningApi.gatherContext(gatherValues);
      setContext(ctx);
      ctxForm.setFieldsValue(toFormValues(ctx));
      // Surface JIRA image attachments in the existing upload area as
      // done-status entries with data-URL thumbnails. They flow to the backend
      // via the context (not as multipart), so they carry no originFileObj.
      const jiraEntries: UploadFile[] = (ctx.jira_images || []).map((img, i) => ({
        uid: `jira-${i}`,
        name: img.filename,
        status: "done" as const,
        url: `data:${img.media_type};base64,${img.data}`,
        thumbUrl: `data:${img.media_type};base64,${img.data}`,
      }));
      setDesignFiles((prev) => [
        ...jiraEntries,
        ...prev.filter((f) => !f.uid.startsWith("jira-")),
      ]);
      const count = jiraEntries.length;
      message.success(
        count > 0
          ? `Context gathered — ${count} JIRA image${count === 1 ? "" : "s"} attached. Review and edit below.`
          : "Context gathered — review and edit below",
      );
    } catch {
      message.error("Failed to gather context");
    } finally {
      setGathering(false);
    }
  }

  async function onGenerate() {
    const values = await ctxForm.validateFields();
    setGenerating(true);
    try {
      const ctx = fromFormValues(values);
      // The Salesforce org-context fields are no longer shown in the form; carry
      // the gathered values through so the planner still receives full org
      // context (edition, objects, fields, flows, apex, permission sets,
      // packages, profiles). jira_images and existing_layouts are likewise not
      // form fields — the latter is required so layout_edits merge into the real
      // layout (else deploy fails on "required layout field: Name").
      if (context) {
        ctx.sf_org_edition = context.sf_org_edition ?? "";
        ctx.lsc_modules = context.lsc_modules ?? [];
        ctx.installed_packages = context.installed_packages ?? [];
        ctx.metadata_objects = context.metadata_objects ?? [];
        ctx.metadata_fields = context.metadata_fields ?? [];
        ctx.metadata_flows = context.metadata_flows ?? [];
        ctx.metadata_apex_classes = context.metadata_apex_classes ?? [];
        ctx.metadata_permission_sets = context.metadata_permission_sets ?? [];
        ctx.metadata_profiles = context.metadata_profiles ?? [];
      }
      ctx.jira_images = context?.jira_images ?? [];
      ctx.existing_layouts = context?.existing_layouts ?? {};
      const files = designFiles
        .map((f) => f.originFileObj as File | undefined)
        .filter((f): f is File => !!f);
      const plan =
        files.length > 0
          ? await planningApi.generateWithImages(ctx, files)
          : await planningApi.generate(ctx);
      message.success("Plan generated");
      navigate(`/plans/${plan.id}`, {
        state: checklistConnId ? { checklistConnId } : undefined,
      });
    } catch (e: unknown) {
      const detail = extractError(e);
      message.error(detail);
    } finally {
      setGenerating(false);
    }
  }

  function beforeUpload(file: File): boolean {
    if (!ACCEPTED_IMAGE_TYPES.includes(file.type)) {
      message.error(`${file.name}: unsupported type. Use PNG, JPG, WebP, or GIF.`);
      return Upload.LIST_IGNORE as unknown as boolean;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      message.error(`${file.name}: exceeds the 5 MB limit.`);
      return Upload.LIST_IGNORE as unknown as boolean;
    }
    // Prevent auto-upload; we send files with the generate request.
    return false;
  }

  return (
    <Row gutter={16}>
      <Col span={8}>
        <Card title="1. Gather Context">
          <Form form={gatherForm} layout="vertical">
            <Form.Item name="jira_connection_id" label="JIRA connection">
              <Select allowClear options={byType("jira")} placeholder="Select" />
            </Form.Item>
            <Form.Item name="jira_ticket_id" label="JIRA ticket ID">
              <Input placeholder="LSC-123" />
            </Form.Item>
            <Form.Item name="github_connection_id" label="GitHub connection">
              <Select allowClear options={byType("github")} placeholder="Select" />
            </Form.Item>
            <Form.Item name="github_branch" label="GitHub branch (optional)">
              <Input placeholder="main" />
            </Form.Item>
            <Form.Item name="salesforce_connection_id" label="Salesforce connection">
              <Select allowClear options={byType("salesforce")} placeholder="Select" />
            </Form.Item>
            <Form.Item name="sfdx_path" label="SFDX project path (optional)">
              <Input placeholder="/path/to/sfdx-project" />
            </Form.Item>
            <Form.Item
              name="checklist_connection_id"
              label="Review checklist (optional)"
            >
              <Select
                allowClear
                options={byType("checklist")}
                placeholder="Select a checklist to review against"
              />
            </Form.Item>
            <Button type="primary" block loading={gathering} onClick={onGather}>
              Gather Context
            </Button>
          </Form>
        </Card>
      </Col>

      <Col span={16}>
        <Card title="2. Review Context & Generate">
          {!context && !gathering && (
            <div style={{ color: "#888" }}>
              Gather context first, or fill the fields manually below and generate.
            </div>
          )}
          {gathering && <Spin />}
          <Form form={ctxForm} layout="vertical" style={{ marginTop: 8 }}>
            <Row gutter={12}>
              <Col span={8}>
                <Form.Item name="jira_ticket_id" label="Ticket ID" rules={[{ required: true }]}>
                  <Input />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="jira_type" label="Type">
                  <Input placeholder="Story / Bug / Task" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="jira_priority" label="Priority">
                  <Input />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="jira_summary" label="Summary">
              <Input />
            </Form.Item>
            <Form.Item name="jira_description" label="Description">
              <TextArea rows={3} />
            </Form.Item>
            <Form.Item name="jira_acceptance_criteria" label="Acceptance criteria">
              <TextArea rows={3} />
            </Form.Item>

            <Divider orientation="left">Access Enablement</Divider>
            <Form.Item
              name="enablement_target"
              label="Enable new access via"
              extra="Choose how the plan should grant access for anything this story adds (field-level security, object/tab/app visibility, Apex access)."
            >
              <Select
                allowClear
                placeholder="Select mechanism"
                options={[
                  { value: "profile", label: "Profile" },
                  { value: "permission_set", label: "Permission Set" },
                ]}
              />
            </Form.Item>
            <Form.Item
              noStyle
              shouldUpdate={(prev, cur) =>
                prev.enablement_target !== cur.enablement_target
              }
            >
              {({ getFieldValue }) => {
                const target = getFieldValue("enablement_target");
                if (target === "profile") {
                  return (
                    <Form.Item
                      name="enablement_profiles"
                      label="Profiles"
                      rules={[
                        {
                          required: true,
                          message: "Select at least one profile",
                        },
                      ]}
                    >
                      <Select
                        mode="multiple"
                        allowClear
                        placeholder="Select profiles to enable"
                        options={(context?.metadata_profiles ?? []).map((p) => ({
                          value: p,
                          label: p,
                        }))}
                        showSearch
                        optionFilterProp="label"
                      />
                    </Form.Item>
                  );
                }
                if (target === "permission_set") {
                  return (
                    <Form.Item
                      name="enablement_permission_sets"
                      label="Permission sets"
                      rules={[
                        {
                          required: true,
                          message: "Select at least one permission set",
                        },
                      ]}
                    >
                      <Select
                        mode="multiple"
                        allowClear
                        placeholder="Select permission sets to enable"
                        options={(context?.metadata_permission_sets ?? []).map(
                          (p) => ({ value: p, label: p }),
                        )}
                        showSearch
                        optionFilterProp="label"
                      />
                    </Form.Item>
                  );
                }
                return null;
              }}
            </Form.Item>

            <Divider orientation="left">GitHub Context</Divider>
            <Form.Item name="github_branch" label="Branch">
              <Input />
            </Form.Item>
            <Form.Item name="github_recent_commits" label="Recent commits">
              <Select mode="tags" tokenSeparators={["\n"]} />
            </Form.Item>
            <Form.Item name="github_open_prs" label="Open PRs">
              <Select mode="tags" tokenSeparators={["\n"]} />
            </Form.Item>

            <Divider orientation="left">Design Reference (optional)</Divider>
            <Form.Item
              label="Figma / UI design images"
              extra={`Upload up to ${MAX_IMAGES} exported images (PNG, JPG, WebP, GIF; max 5 MB each). Claude uses them as visual context for the plan.`}
            >
              <Upload.Dragger
                multiple
                accept={ACCEPTED_IMAGE_TYPES.join(",")}
                listType="picture"
                fileList={designFiles}
                beforeUpload={beforeUpload}
                onChange={({ fileList }) =>
                  setDesignFiles(fileList.slice(0, MAX_IMAGES))
                }
                onRemove={(file) =>
                  setDesignFiles((prev) =>
                    prev.filter((f) => f.uid !== file.uid),
                  )
                }
              >
                <p className="ant-upload-drag-icon">
                  <InboxOutlined />
                </p>
                <p className="ant-upload-text">
                  Click or drag Figma export(s) here
                </p>
                <p className="ant-upload-hint">
                  Export a frame from Figma as PNG/JPG and drop it here.
                </p>
              </Upload.Dragger>
            </Form.Item>

            <Space>
              <Button type="primary" loading={generating} onClick={onGenerate}>
                Generate Plan
              </Button>
            </Space>
          </Form>
        </Card>
      </Col>
    </Row>
  );
}

function toFormValues(ctx: PlanningContext) {
  return { ...ctx };
}

function fromFormValues(values: Record<string, unknown>): PlanningContext {
  const listFields = [
    "lsc_modules",
    "installed_packages",
    "metadata_objects",
    "metadata_fields",
    "metadata_flows",
    "metadata_apex_classes",
    "metadata_permission_sets",
    "metadata_profiles",
    "enablement_profiles",
    "enablement_permission_sets",
    "github_recent_commits",
    "github_open_prs",
  ];
  const out: Record<string, unknown> = { ...values };
  listFields.forEach((f) => {
    if (!out[f]) out[f] = [];
  });
  if (!out.jira_images) out.jira_images = [];
  if (!out.existing_layouts) out.existing_layouts = {};
  const stringFields = [
    "jira_ticket_id",
    "jira_summary",
    "jira_description",
    "jira_acceptance_criteria",
    "jira_type",
    "jira_priority",
    "sf_org_edition",
    "enablement_target",
    "github_branch",
  ];
  stringFields.forEach((f) => {
    if (!out[f]) out[f] = "";
  });
  return out as unknown as PlanningContext;
}

function extractError(e: unknown): string {
  const err = e as { response?: { data?: { detail?: unknown } } };
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const d = detail as { message?: string; errors?: string[] };
    return `${d.message ?? "Generation failed"}: ${(d.errors ?? []).join("; ")}`;
  }
  return "Generation failed";
}
