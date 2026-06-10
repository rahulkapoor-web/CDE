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
  CheckCircleOutlined,
  CloseCircleOutlined,
} from "@ant-design/icons";
import {
  getConnections,
  createConnection,
  deleteConnection,
  testConnection,
} from "../services/api";
import type { ConnectionProfile } from "../types";

export default function ConnectionsPage() {
  const [connections, setConnections] = useState<ConnectionProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
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

  const handleCreate = async (values: Record<string, unknown>) => {
    try {
      await createConnection(values);
      message.success("Connection created");
      setModalOpen(false);
      form.resetFields();
      load();
    } catch (err: any) {
      message.error(err.response?.data?.detail || "Failed to create");
    }
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
    <Card
      title="Connection Profiles"
      extra={
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setModalOpen(true)}
        >
          New Connection
        </Button>
      }
    >
      <Table
        dataSource={connections}
        columns={columns}
        rowKey="id"
        loading={loading}
      />

      <Modal
        title="New Connection"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
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
                <Input.Password />
              </Form.Item>
              <Form.Item name="sf_security_token" label="Security Token">
                <Input.Password />
              </Form.Item>
              <Form.Item name="sf_consumer_key" label="Consumer Key (optional)">
                <Input />
              </Form.Item>
              <Form.Item
                name="sf_consumer_secret"
                label="Consumer Secret (optional)"
              >
                <Input.Password />
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
                <Input.Password />
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>
    </Card>
  );
}
