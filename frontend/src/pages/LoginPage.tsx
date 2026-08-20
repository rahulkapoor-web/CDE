import { Button, Card, Form, Input, Tabs, message } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

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
    <div
      style={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        minHeight: "100vh",
        background: "#f0f2f5",
      }}
    >
      <Card style={{ width: 420 }} title="ONA — AI Planning Engine">
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
  );
}
