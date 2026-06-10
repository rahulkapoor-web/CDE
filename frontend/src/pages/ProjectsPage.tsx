import React, { useEffect, useState } from "react";
import {
  Card,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Space,
  message,
  Popconfirm,
} from "antd";
import { PlusOutlined, DeleteOutlined, RightOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import {
  getProjects,
  createProject,
  deleteProject,
  getConnections,
} from "../services/api";
import type { MigrationProject, ConnectionProfile } from "../types";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<MigrationProject[]>([]);
  const [connections, setConnections] = useState<ConnectionProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const navigate = useNavigate();

  const load = async () => {
    setLoading(true);
    try {
      const [projRes, connRes] = await Promise.all([
        getProjects(),
        getConnections(),
      ]);
      setProjects(projRes.data);
      setConnections(connRes.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleCreate = async (values: Record<string, unknown>) => {
    try {
      await createProject(values);
      message.success("Project created");
      setModalOpen(false);
      form.resetFields();
      load();
    } catch (err: any) {
      message.error(err.response?.data?.detail || "Failed");
    }
  };

  const handleDelete = async (id: string) => {
    await deleteProject(id);
    message.success("Deleted");
    load();
  };

  const connName = (id: string) =>
    connections.find((c) => c.id === id)?.name || id;

  const columns = [
    { title: "Name", dataIndex: "name", key: "name" },
    { title: "Description", dataIndex: "description", key: "description" },
    {
      title: "Source",
      dataIndex: "source_connection_id",
      key: "source",
      render: (v: string) => connName(v),
    },
    {
      title: "Target",
      dataIndex: "target_connection_id",
      key: "target",
      render: (v: string) => connName(v),
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: unknown, record: MigrationProject) => (
        <Space>
          <Button
            type="primary"
            size="small"
            icon={<RightOutlined />}
            onClick={() => navigate(`/projects/${record.id}`)}
          >
            Open
          </Button>
          <Popconfirm
            title="Delete this project?"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const sfConnections = connections.filter(
    (c) => c.system_type === "salesforce"
  );
  const vaultConnections = connections.filter(
    (c) => c.system_type === "veeva_vault"
  );

  return (
    <Card
      title="Migration Projects"
      extra={
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setModalOpen(true)}
        >
          New Project
        </Button>
      }
    >
      <Table
        dataSource={projects}
        columns={columns}
        rowKey="id"
        loading={loading}
      />

      <Modal
        title="New Migration Project"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item
            name="source_connection_id"
            label="Source (Salesforce / IQVIA OCEP)"
            rules={[{ required: true }]}
          >
            <Select>
              {sfConnections.map((c) => (
                <Select.Option key={c.id} value={c.id}>
                  {c.name} ({c.environment})
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item
            name="target_connection_id"
            label="Target (Veeva Vault CRM)"
            rules={[{ required: true }]}
          >
            <Select>
              {vaultConnections.map((c) => (
                <Select.Option key={c.id} value={c.id}>
                  {c.name} ({c.environment})
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
