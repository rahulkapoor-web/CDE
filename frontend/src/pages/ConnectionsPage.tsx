import {
  Button,
  Card,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  message,
} from "antd";
import { useEffect, useState } from "react";
import { connectionsApi } from "../services/api";
import type { Connection, ConnType } from "../types";

const TYPE_COLORS: Record<ConnType, string> = {
  jira: "blue",
  github: "purple",
  salesforce: "cyan",
};

const SECRET_KEYS: Record<ConnType, string[]> = {
  jira: ["api_token"],
  github: ["token"],
  salesforce: [
    "client_secret",
    "password",
    "security_token",
    "private_key",
    "access_token",
  ],
};

export default function ConnectionsPage() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [open, setOpen] = useState(false);
  const [connType, setConnType] = useState<ConnType>("jira");
  const [editing, setEditing] = useState<Connection | null>(null);
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setConnections(await connectionsApi.list());
  }

  useEffect(() => {
    refresh();
  }, []);

  function openCreate() {
    setEditing(null);
    setConnType("jira");
    form.resetFields();
    setOpen(true);
  }

  function openEdit(conn: Connection) {
    setEditing(conn);
    setConnType(conn.conn_type);
    form.resetFields();
    // Pre-fill non-secret config; secret fields stay blank (blank = keep existing).
    form.setFieldsValue({ name: conn.name, ...conn.config });
    setOpen(true);
  }

  async function onSubmit() {
    const values = await form.validateFields();
    setLoading(true);
    try {
      const { name, ...rest } = values;
      const { config, secrets } = splitFields(connType, rest);
      if (editing) {
        await connectionsApi.update(editing.id, {
          name,
          config,
          // Only send secrets the user actually re-entered.
          ...(Object.keys(secrets).length ? { secrets } : {}),
        });
        message.success("Connection updated");
      } else {
        await connectionsApi.create({ name, conn_type: connType, config, secrets });
        message.success("Connection created");
      }
      setOpen(false);
      setEditing(null);
      form.resetFields();
      refresh();
    } catch {
      message.error(
        editing ? "Failed to update connection" : "Failed to create connection",
      );
    } finally {
      setLoading(false);
    }
  }

  async function onTest(id: number) {
    const res = await connectionsApi.test(id);
    if (res.ok) message.success(res.detail);
    else message.error(res.detail);
  }

  async function onDelete(id: number) {
    await connectionsApi.remove(id);
    refresh();
  }

  const secretRequired = !editing; // secrets optional when editing (blank keeps existing)

  return (
    <Card
      title="Connections"
      extra={
        <Button type="primary" onClick={openCreate}>
          Add Connection
        </Button>
      }
    >
      <Table<Connection>
        rowKey="id"
        dataSource={connections}
        pagination={false}
        columns={[
          { title: "Name", dataIndex: "name" },
          {
            title: "Type",
            dataIndex: "conn_type",
            render: (t: ConnType) => <Tag color={TYPE_COLORS[t]}>{t}</Tag>,
          },
          {
            title: "Secrets",
            dataIndex: "has_secrets",
            render: (v: boolean) => (v ? <Tag color="green">stored</Tag> : <Tag>none</Tag>),
          },
          {
            title: "Actions",
            render: (_, r) => (
              <Space>
                <Button size="small" onClick={() => onTest(r.id)}>
                  Test
                </Button>
                <Button size="small" onClick={() => openEdit(r)}>
                  Edit
                </Button>
                <Button size="small" danger onClick={() => onDelete(r.id)}>
                  Delete
                </Button>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title={editing ? `Edit Connection: ${editing.name}` : "Add Connection"}
        open={open}
        onOk={onSubmit}
        okText={editing ? "Save" : "Create"}
        confirmLoading={loading}
        onCancel={() => {
          setOpen(false);
          setEditing(null);
        }}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input placeholder="e.g. Prod JIRA" />
          </Form.Item>
          <Form.Item label="Type">
            <Select
              value={connType}
              disabled={!!editing}
              onChange={(v) => setConnType(v)}
              options={[
                { value: "jira", label: "JIRA" },
                { value: "github", label: "GitHub" },
                { value: "salesforce", label: "Salesforce" },
              ]}
            />
          </Form.Item>

          {editing && (
            <div style={{ marginBottom: 16, color: "#888" }}>
              Leave secret fields blank to keep the existing stored value.
            </div>
          )}

          {connType === "jira" && (
            <>
              <Form.Item name="base_url" label="Base URL" rules={[{ required: true }]}>
                <Input placeholder="https://your-org.atlassian.net" />
              </Form.Item>
              <Form.Item name="email" label="Email (Cloud) — leave blank for PAT">
                <Input placeholder="you@example.com" />
              </Form.Item>
              <Form.Item
                name="api_token"
                label="API Token / PAT"
                rules={[{ required: secretRequired }]}
              >
                <Input.Password placeholder={editing ? "(unchanged)" : ""} />
              </Form.Item>
            </>
          )}
          {connType === "github" && (
            <>
              <Form.Item name="repo" label="Repository (owner/repo)" rules={[{ required: true }]}>
                <Input placeholder="octocat/hello-world" />
              </Form.Item>
              <Form.Item
                name="token"
                label="Personal Access Token"
                rules={[{ required: secretRequired }]}
              >
                <Input.Password placeholder={editing ? "(unchanged)" : ""} />
              </Form.Item>
            </>
          )}
          {connType === "salesforce" && (
            <>
              <Form.Item
                name="auth_flow"
                label="Auth Flow"
                initialValue="client_credentials"
              >
                <Select
                  options={[
                    {
                      value: "client_credentials",
                      label: "Client Credentials (client_id + secret)",
                    },
                    {
                      value: "password",
                      label: "Username-Password (OAuth ROPC)",
                    },
                    {
                      value: "jwt_bearer",
                      label: "JWT Bearer (private key)",
                    },
                    {
                      value: "access_token",
                      label: "Access Token (pre-obtained)",
                    },
                  ]}
                />
              </Form.Item>
              <Form.Item
                noStyle
                shouldUpdate={(prev, cur) => prev.auth_flow !== cur.auth_flow}
              >
                {({ getFieldValue }) => {
                  const flow =
                    getFieldValue("auth_flow") || "client_credentials";
                  const showClientId = [
                    "client_credentials",
                    "password",
                    "jwt_bearer",
                  ].includes(flow);
                  const showClientSecret = [
                    "client_credentials",
                    "password",
                  ].includes(flow);
                  const showUsername =
                    flow === "password" || flow === "jwt_bearer";
                  const showUserPass = flow === "password";
                  const showPrivateKey = flow === "jwt_bearer";
                  const showAccessToken = flow === "access_token";
                  return (
                    <>
                      {showClientId && (
                        <Form.Item
                          name="client_id"
                          label="Consumer Key (client_id)"
                        >
                          <Input placeholder="3MVG9..." />
                        </Form.Item>
                      )}
                      {showClientSecret && (
                        <Form.Item
                          name="client_secret"
                          label="Consumer Secret"
                        >
                          <Input.Password
                            placeholder={editing ? "(unchanged)" : ""}
                          />
                        </Form.Item>
                      )}
                      {showUsername && (
                        <Form.Item name="username" label="Username">
                          <Input placeholder="user@org.com" />
                        </Form.Item>
                      )}
                      {showUserPass && (
                        <Form.Item name="password" label="Password">
                          <Input.Password
                            placeholder={editing ? "(unchanged)" : ""}
                          />
                        </Form.Item>
                      )}
                      {showUserPass && (
                        <Form.Item
                          name="security_token"
                          label="Security Token (optional)"
                        >
                          <Input.Password
                            placeholder={editing ? "(unchanged)" : ""}
                          />
                        </Form.Item>
                      )}
                      {showPrivateKey && (
                        <Form.Item
                          name="private_key"
                          label="Private Key (PEM)"
                        >
                          <Input.TextArea
                            rows={4}
                            placeholder={
                              editing
                                ? "(unchanged)"
                                : "-----BEGIN PRIVATE KEY-----"
                            }
                          />
                        </Form.Item>
                      )}
                      {showAccessToken && (
                        <Form.Item name="access_token" label="Access Token">
                          <Input.Password
                            placeholder={editing ? "(unchanged)" : ""}
                          />
                        </Form.Item>
                      )}
                      <Form.Item
                        name="instance_url"
                        label="Instance URL (My Domain)"
                      >
                        <Input placeholder="https://your.my.salesforce.com" />
                      </Form.Item>
                      <Form.Item
                        name="is_sandbox"
                        label="Sandbox"
                        valuePropName="checked"
                      >
                        <Switch />
                      </Form.Item>
                    </>
                  );
                }}
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>
    </Card>
  );
}

function splitFields(type: ConnType, values: Record<string, unknown>) {
  const config: Record<string, unknown> = {};
  const secrets: Record<string, unknown> = {};
  Object.entries(values).forEach(([k, v]) => {
    if (v === undefined || v === "") return;
    if (SECRET_KEYS[type].includes(k)) secrets[k] = v;
    else config[k] = v;
  });
  return { config, secrets };
}
