import { Button, Card, Form, Input, Tabs, Typography, message } from "antd";
import {
  CloudOutlined,
  DeploymentUnitOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import Logo from "../components/Logo";

const { Title, Paragraph } = Typography;

const FEATURES = [
  {
    icon: <ThunderboltOutlined />,
    title: "AI-generated plans",
    text: "Turn a JIRA ticket into a grounded, step-by-step delivery plan.",
  },
  {
    icon: <CloudOutlined />,
    title: "Org-aware metadata",
    text: "Apex and LWC authored against your org's real API version.",
  },
  {
    icon: <DeploymentUnitOutlined />,
    title: "One-click deploy",
    text: "Deploy to the connected org and fix errors with AI in place.",
  },
];

export default function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);

  async function onLogin(values: { email: string; password: string }) {
    setLoading(true);
    try {
      await login(values.email, values.password);
      navigate("/generate");
    } catch {
      message.error("Login failed. Check your credentials.");
    } finally {
      setLoading(false);
    }
  }

  async function onRegister(values: {
    email: string;
    password: string;
    full_name?: string;
  }) {
    setLoading(true);
    try {
      await register(values.email, values.password, values.full_name);
      navigate("/generate");
    } catch {
      message.error("Registration failed. Email may already be in use.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      {/* Branded hero panel (hidden on narrow screens via flex-wrap fallback). */}
      <div
        style={{
          flex: "1 1 0",
          minWidth: 0,
          background:
            "linear-gradient(135deg, #00A1E0 0%, #1677ff 55%, #0b1220 100%)",
          color: "#fff",
          padding: "56px 48px",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
        }}
      >
        <Logo size={44} />
        <Title
          level={2}
          style={{ color: "#fff", marginTop: 32, marginBottom: 8, maxWidth: 460 }}
        >
          Ship Salesforce changes faster, with confidence.
        </Title>
        <Paragraph
          style={{ color: "rgba(255,255,255,0.85)", maxWidth: 460, fontSize: 15 }}
        >
          SFDC Dev Agent plans, builds, and deploys Salesforce metadata from your
          delivery tickets — grounded in your org's real configuration.
        </Paragraph>
        <div style={{ marginTop: 32, display: "grid", gap: 20, maxWidth: 460 }}>
          {FEATURES.map((f) => (
            <div key={f.title} style={{ display: "flex", gap: 14 }}>
              <div
                style={{
                  fontSize: 20,
                  background: "rgba(255,255,255,0.15)",
                  borderRadius: 10,
                  width: 40,
                  height: 40,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                }}
              >
                {f.icon}
              </div>
              <div>
                <div style={{ fontWeight: 600 }}>{f.title}</div>
                <div style={{ color: "rgba(255,255,255,0.8)", fontSize: 13 }}>
                  {f.text}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Auth panel. */}
      <div
        style={{
          flex: "0 0 clamp(360px, 38%, 520px)",
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          background: "#f0f2f5",
          padding: 24,
        }}
      >
        <Card style={{ width: "100%", maxWidth: 400 }} title="Welcome back">
        <Tabs
          items={[
            {
              key: "login",
              label: "Login",
              children: (
                <Form layout="vertical" onFinish={onLogin}>
                  <Form.Item name="email" label="Email" rules={[{ required: true, type: "email" }]}>
                    <Input placeholder="you@example.com" />
                  </Form.Item>
                  <Form.Item name="password" label="Password" rules={[{ required: true }]}>
                    <Input.Password />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" block loading={loading}>
                    Log in
                  </Button>
                </Form>
              ),
            },
            {
              key: "register",
              label: "Register",
              children: (
                <Form layout="vertical" onFinish={onRegister}>
                  <Form.Item name="full_name" label="Full name">
                    <Input />
                  </Form.Item>
                  <Form.Item name="email" label="Email" rules={[{ required: true, type: "email" }]}>
                    <Input placeholder="you@example.com" />
                  </Form.Item>
                  <Form.Item name="password" label="Password" rules={[{ required: true, min: 6 }]}>
                    <Input.Password />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" block loading={loading}>
                    Create account
                  </Button>
                </Form>
              ),
            },
          ]}
        />
        </Card>
      </div>
    </div>
  );
}
