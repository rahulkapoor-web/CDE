import React, { useEffect, useState } from "react";
import {
  Card,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Tag,
  Space,
  message,
  Popconfirm,
} from "antd";
import {
  PlusOutlined,
  ApiOutlined,
  DeleteOutlined,
  EditOutlined,
} from "@ant-design/icons";
import {
  getConnections,
  createConnection,
  updateConnection,
  deleteConnection,
  testConnection,
} from "../services/api";
import type { ConnectionProfile } from "../types";

export default function ConnectionsPage() {
  const [connections, setConnections] = useState<ConnectionProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form] = Form.useForm();
  const [systemType, setSystemType] = useState<string>("salesforce");

  const load = async () => {
    setLoading(true);
    try {
      const res = await getConnections();
      setConnections(res.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleSubmit = async (values: Record<string, unknown>) => {
    try {
      if (editingId) {
        await updateConnection(editingId, values);
        message.success("Connection updated");
      } else {
        await createConnection(values);
        message.success("Connection created");
      }
      setModalOpen(false);
      setEditingId(null);
      form.resetFields();
      load();
    } catch (err: any) {
      message.error(err.response?.data?.detail || "Failed to save");
    }
  };

  const handleEdit = (record: ConnectionProfile) => {
    setEditingId(record.id);
    setSystemType(record.system_type);
    form.resetFields();
    // Only set non-sensitive fields — passwords and tokens are never returned from the API
    form.setFieldsValue({
      name: record.name,
      system_type: record.system_type,
      environment: record.environment,
      sf_username: record.sf_username,
      sf_instance_url: record.sf_instance_url,
      sf_password: undefined,
      sf_security_token: undefined,
      sf_consumer_key: undefined,
      sf_consumer_secret: undefined,
      vault_dns: record.vault_dns,
      vault_username: record.vault_username,
      vault_password: undefined,
    });
    setModalOpen(true);
  };

  const handleDelete = async (id: string) => {
    await deleteConnection(id);
    message.success("Deleted");
    load();
  };

  const handleTest = async (id: string) => {
    try {
      const res = await testConnection(id);
      if (res.data.success) {
        message.success(res.data.message);
      } else {
        message.error(res.data.message);
      }
    } catch {
      message.error("Connection test failed");
    }
  };

  const columns = [
    { title: "Name", dataIndex: "name", key: "name" },
    {
      title: "System",
      dataIndex: "system_type",
      key: "system_type",
      render: (v: string) => (
        <Tag color={v === "salesforce" ? "blue" : "green"}>
          {v === "salesforce" ? "Salesforce (IQVIA OCEP)" : "Veeva Vault CRM"}
        </Tag>
      ),
    },
    {
      title: "Environment",
      dataIndex: "environment",
      key: "environment",
      render: (v: string) => (
        <Tag color={v === "production" ? "red" : "orange"}>{v}</Tag>
      ),
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: unknown, record: ConnectionProfile) => (
        <Space>
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            Edit
          </Button>
          <Button
            size="small"
            icon={<ApiOutlined />}
            onClick={() => handleTest(record.id)}
          >
            Test
          </Button>
          <Popconfirm
            title="Delete this connection?"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 24,
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: 24, fontWeight: 600 }}>
            Connection Profiles
          </h2>
          <p style={{ margin: "4px 0 0", color: "#8c8c8c", fontSize: 14 }}>
            Manage your Salesforce and Veeva Vault connections
          </p>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          size="large"
          onClick={() => {
            setEditingId(null);
            form.resetFields();
            setSystemType("salesforce");
            setModalOpen(true);
          }}
          style={{
            borderRadius: 10,
            height: 44,
            paddingInline: 24,
            fontWeight: 600,
            background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
            border: "none",
            boxShadow: "0 4px 15px rgba(102, 126, 234, 0.3)",
          }}
        >
          New Connection
        </Button>
      </div>
      <Card
        style={{
          borderRadius: 12,
          boxShadow: "0 2px 12px rgba(0,0,0,0.06)",
          border: "1px solid #f0f0f0",
        }}
        styles={{ body: { padding: 0 } }}
      >
        <Table
          dataSource={connections}
          columns={columns}
          rowKey="id"
          loading={loading}
          style={{ borderRadius: 12, overflow: "hidden" }}
        />

      <Modal
        title={editingId ? "Edit Connection" : "New Connection"}
        open={modalOpen}
        onCancel={() => {
          setModalOpen(false);
          setEditingId(null);
          form.resetFields();
        }}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item
            name="system_type"
            label="System Type"
            rules={[{ required: true }]}
          >
            <Select onChange={(v) => setSystemType(v)}>
              <Select.Option value="salesforce">
                Salesforce (IQVIA OCEP)
              </Select.Option>
              <Select.Option value="veeva_vault">
                Veeva Vault CRM
              </Select.Option>
            </Select>
          </Form.Item>
          <Form.Item
            name="environment"
            label="Environment"
            rules={[{ required: true }]}
          >
            <Select>
              <Select.Option value="sandbox">Sandbox</Select.Option>
              <Select.Option value="production">Production</Select.Option>
            </Select>
          </Form.Item>

          {systemType === "salesforce" && (
            <>
              <Form.Item name="sf_instance_url" label="Instance URL">
                <Input placeholder="https://myorg.my.salesforce.com" />
              </Form.Item>
              <Form.Item name="sf_username" label="Username">
                <Input />
              </Form.Item>
              <Form.Item name="sf_password" label="Password">
                <Input.Password
                  placeholder={editingId ? "Leave blank to keep current" : ""}
                  autoComplete="new-password"
                />
              </Form.Item>
              <Form.Item name="sf_security_token" label="Security Token">
                <Input
                  placeholder={editingId ? "Leave blank to keep current" : ""}
                  autoComplete="off"
                />
              </Form.Item>
              <Form.Item name="sf_consumer_key" label="Consumer Key (optional)">
                <Input
                  placeholder={editingId ? "Leave blank to keep current" : ""}
                  autoComplete="off"
                />
              </Form.Item>
              <Form.Item
                name="sf_consumer_secret"
                label="Consumer Secret (optional)"
              >
                <Input.Password
                  placeholder={editingId ? "Leave blank to keep current" : ""}
                  autoComplete="new-password"
                />
              </Form.Item>
            </>
          )}

          {systemType === "veeva_vault" && (
            <>
              <Form.Item name="vault_dns" label="Vault DNS">
                <Input placeholder="https://myvault.veevavault.com" />
              </Form.Item>
              <Form.Item name="vault_username" label="Username">
                <Input />
              </Form.Item>
              <Form.Item name="vault_password" label="Password">
                <Input.Password
                  placeholder={editingId ? "Leave blank to keep current" : ""}
                  autoComplete="new-password"
                />
              </Form.Item>
            </>
          )}
        </Form>
        </Modal>
      </Card>
    </div>
  );
}
