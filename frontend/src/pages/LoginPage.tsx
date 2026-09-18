import React, { useState } from "react";
import { Form, Input, Button, Typography, message, Tabs, Divider } from "antd";
import {
  UserOutlined,
  LockOutlined,
  MailOutlined,
  SwapOutlined,
  SafetyCertificateOutlined,
  CloudServerOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { login, register } from "../services/api";
import DataValidationIllustration from "../components/DataMigrationIllustration";

const { Title, Text, Paragraph } = Typography;

interface Props {
  onLogin: (token: string) => void;
}

export default function LoginPage({ onLogin }: Props) {
  const [loading, setLoading] = useState(false);

  const handleLogin = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const res = await login(values.username, values.password);
      onLogin(res.data.access_token);
    } catch {
      message.error("Invalid credentials");
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (values: {
    username: string;
    email: string;
    password: string;
    full_name?: string;
  }) => {
    setLoading(true);
    try {
      await register(values);
      message.success("Account created. Please log in.");
    } catch (err: any) {
      message.error(err.response?.data?.detail || "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        minHeight: "100vh",
        background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
      }}
    >
      {/* Left panel — illustration & branding */}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          padding: "48px 40px",
          position: "relative",
          overflow: "hidden",
        }}
      >
        {/* Decorative circles */}
        <div
          style={{
            position: "absolute",
            top: -80,
            left: -80,
            width: 300,
            height: 300,
            borderRadius: "50%",
            background: "rgba(255,255,255,0.06)",
          }}
        />
        <div
          style={{
            position: "absolute",
            bottom: -60,
            right: -60,
            width: 250,
            height: 250,
            borderRadius: "50%",
            background: "rgba(255,255,255,0.04)",
          }}
        />

        <div style={{ position: "relative", zIndex: 1, textAlign: "center", maxWidth: 500 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 12,
              marginBottom: 32,
            }}
          >
            <SwapOutlined
              style={{
                fontSize: 36,
                color: "#fff",
                background: "rgba(255,255,255,0.15)",
                padding: 12,
                borderRadius: 12,
              }}
            />
            <Title level={2} style={{ margin: 0, color: "#fff", letterSpacing: -0.5 }}>
              Migration Bridge
            </Title>
          </div>

          <div
            style={{
              background: "rgba(255,255,255,0.1)",
              backdropFilter: "blur(10px)",
              borderRadius: 20,
              padding: 24,
              marginBottom: 32,
              border: "1px solid rgba(255,255,255,0.15)",
            }}
          >
            <DataValidationIllustration width="100%" height="auto" />
          </div>

          <Paragraph
            style={{
              color: "rgba(255,255,255,0.9)",
              fontSize: 16,
              lineHeight: 1.7,
              marginBottom: 24,
            }}
          >
            Validate and compare your migrated CRM data between Salesforce IQVIA OCE
            and Veeva Vault CRM — spot mismatches, verify completeness, and ensure data integrity.
          </Paragraph>

          {/* Feature pills */}
          <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
            {[
              { icon: <SafetyCertificateOutlined />, text: "Data Validation" },
              { icon: <CloudServerOutlined />, text: "Side-by-Side Compare" },
              { icon: <ThunderboltOutlined />, text: "Mismatch Detection" },
            ].map((f, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  background: "rgba(255,255,255,0.12)",
                  borderRadius: 20,
                  padding: "6px 16px",
                  color: "#fff",
                  fontSize: 13,
                  fontWeight: 500,
                  border: "1px solid rgba(255,255,255,0.1)",
                }}
              >
                {f.icon}
                {f.text}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right panel — login form */}
      <div
        style={{
          width: 480,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          background: "#fff",
          borderRadius: "24px 0 0 24px",
          boxShadow: "-8px 0 40px rgba(0,0,0,0.1)",
          padding: "48px 40px",
        }}
      >
        <div style={{ width: "100%", maxWidth: 360 }}>
          <div style={{ textAlign: "center", marginBottom: 32 }}>
            <Title level={3} style={{ marginBottom: 4 }}>
              Welcome Back
            </Title>
            <Text type="secondary">Sign in to validate your migrated data</Text>
          </div>

          <Tabs
            centered
            size="large"
            items={[
              {
                key: "login",
                label: "Sign In",
                children: (
                  <Form onFinish={handleLogin} layout="vertical" size="large">
                    <Form.Item
                      name="username"
                      rules={[{ required: true, message: "Please enter your username" }]}
                    >
                      <Input
                        prefix={<UserOutlined style={{ color: "#bfbfbf" }} />}
                        placeholder="Username"
                        style={{ borderRadius: 10, height: 48 }}
                      />
                    </Form.Item>
                    <Form.Item
                      name="password"
                      rules={[{ required: true, message: "Please enter your password" }]}
                    >
                      <Input.Password
                        prefix={<LockOutlined style={{ color: "#bfbfbf" }} />}
                        placeholder="Password"
                        style={{ borderRadius: 10, height: 48 }}
                      />
                    </Form.Item>
                    <Form.Item style={{ marginBottom: 16 }}>
                      <Button
                        type="primary"
                        htmlType="submit"
                        block
                        loading={loading}
                        style={{
                          height: 48,
                          borderRadius: 10,
                          fontSize: 16,
                          fontWeight: 600,
                          background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
                          border: "none",
                          boxShadow: "0 4px 15px rgba(102, 126, 234, 0.4)",
                        }}
                      >
                        Sign In
                      </Button>
                    </Form.Item>
                  </Form>
                ),
              },
              {
                key: "register",
                label: "Register",
                children: (
                  <Form onFinish={handleRegister} layout="vertical" size="large">
                    <Form.Item
                      name="username"
                      rules={[{ required: true, message: "Choose a username" }]}
                    >
                      <Input
                        prefix={<UserOutlined style={{ color: "#bfbfbf" }} />}
                        placeholder="Username"
                        style={{ borderRadius: 10, height: 48 }}
                      />
                    </Form.Item>
                    <Form.Item
                      name="email"
                      rules={[
                        { required: true, message: "Enter your email" },
                        { type: "email", message: "Invalid email" },
                      ]}
                    >
                      <Input
                        prefix={<MailOutlined style={{ color: "#bfbfbf" }} />}
                        placeholder="Email"
                        style={{ borderRadius: 10, height: 48 }}
                      />
                    </Form.Item>
                    <Form.Item name="full_name">
                      <Input
                        placeholder="Full Name (optional)"
                        style={{ borderRadius: 10, height: 48 }}
                      />
                    </Form.Item>
                    <Form.Item
                      name="password"
                      rules={[{ required: true, message: "Create a password" }]}
                    >
                      <Input.Password
                        prefix={<LockOutlined style={{ color: "#bfbfbf" }} />}
                        placeholder="Password"
                        style={{ borderRadius: 10, height: 48 }}
                      />
                    </Form.Item>
                    <Form.Item style={{ marginBottom: 16 }}>
                      <Button
                        type="primary"
                        htmlType="submit"
                        block
                        loading={loading}
                        style={{
                          height: 48,
                          borderRadius: 10,
                          fontSize: 16,
                          fontWeight: 600,
                          background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
                          border: "none",
                          boxShadow: "0 4px 15px rgba(102, 126, 234, 0.4)",
                        }}
                      >
                        Create Account
                      </Button>
                    </Form.Item>
                  </Form>
                ),
              },
            ]}
          />

          <Divider style={{ margin: "16px 0" }} />

          <div style={{ textAlign: "center" }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              Post-Migration Data Validation &amp; Testing Platform
            </Text>
          </div>
        </div>
      </div>
    </div>
  );
}
