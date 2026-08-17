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

export default function ConnectionsPage() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [open, setOpen] = useState(false);
  const [connType, setConnType] = useState<ConnType>("jira");
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setConnections(await connectionsApi.list());
  }

  useEffect(() => {
    refresh();
  }, []);

  async function onCreate() {
    const values = await form.validateFields();
    setLoading(true);
    try {
      const { name, ...rest } = values;
      const { config, secrets } = splitFields(connType, rest);
      await connectionsApi.create({ name, conn_type: connType, config, secrets });
      message.success("Connection created");
      setOpen(false);
      form.resetFields();
      refresh();
    } catch {
      message.error("Failed to create connection");
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

  return (
    <Card
      title="Connections"
      extra={
        <Button type="primary" onClick={() => setOpen(true)}>
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
                <Button size="small" danger onClick={() => onDelete(r.id)}>
                  Delete
                </Button>
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title="Add Connection"
        open={open}
        onOk={onCreate}
        confirmLoading={loading}
        onCancel={() => setOpen(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input placeholder="e.g. Prod JIRA" />
          </Form.Item>
          <Form.Item label="Type">
            <Select
              value={connType}
              onChange={(v) => setConnType(v)}
              options={[
                { value: "jira", label: "JIRA" },
                { value: "github", label: "GitHub" },
                { value: "salesforce", label: "Salesforce" },
              ]}
            />
          </Form.Item>
          {connType === "jira" && (
            <>
              <Form.Item name="base_url" label="Base URL" rules={[{ required: true }]}>
                <Input placeholder="https://your-org.atlassian.net" />
              </Form.Item>
              <Form.Item name="email" label="Email (Cloud) — leave blank for PAT">
                <Input placeholder="you@example.com" />
              </Form.Item>
              <Form.Item name="api_token" label="API Token / PAT" rules={[{ required: true }]}>
                <Input.Password />
              </Form.Item>
            </>
          )}
          {connType === "github" && (
            <>
              <Form.Item name="repo" label="Repository (owner/repo)" rules={[{ required: true }]}>
                <Input placeholder="octocat/hello-world" />
              </Form.Item>
              <Form.Item name="token" label="Personal Access Token" rules={[{ required: true }]}>
                <Input.Password />
              </Form.Item>
            </>
          )}
          {connType === "salesforce" && (
            <>
              <Form.Item name="username" label="Username">
                <Input placeholder="user@org.com" />
              </Form.Item>
              <Form.Item name="password" label="Password">
                <Input.Password />
              </Form.Item>
              <Form.Item name="security_token" label="Security Token">
                <Input.Password />
              </Form.Item>
              <Form.Item name="instance_url" label="Instance URL (for OAuth token)">
                <Input placeholder="https://your.my.salesforce.com" />
              </Form.Item>
              <Form.Item name="access_token" label="Access Token (OAuth)">
                <Input.Password />
              </Form.Item>
              <Form.Item name="is_sandbox" label="Sandbox" valuePropName="checked">
                <Switch />
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>
    </Card>
  );
}

function splitFields(type: ConnType, values: Record<string, unknown>) {
  const secretKeys: Record<ConnType, string[]> = {
    jira: ["api_token"],
    github: ["token"],
    salesforce: ["password", "security_token", "access_token"],
  };
  const config: Record<string, unknown> = {};
  const secrets: Record<string, unknown> = {};
  Object.entries(values).forEach(([k, v]) => {
    if (v === undefined || v === "") return;
    if (secretKeys[type].includes(k)) secrets[k] = v;
    else config[k] = v;
  });
  return { config, secrets };
}
