import React from "react";
import { Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
import { Layout, Menu, Button, Typography, ConfigProvider, theme } from "antd";
import {
  ApiOutlined,
  ProjectOutlined,
  LogoutOutlined,
  SwapOutlined,
} from "@ant-design/icons";
import { useAuth } from "./hooks/useAuth";
import LoginPage from "./pages/LoginPage";
import ConnectionsPage from "./pages/ConnectionsPage";
import ProjectsPage from "./pages/ProjectsPage";
import ProjectDetailPage from "./pages/ProjectDetailPage";

const { Header, Sider, Content } = Layout;
const { Title } = Typography;

function AppLayout({ onLogout }: { onLogout: () => void }) {
  const navigate = useNavigate();
  const location = useLocation();

  const menuItems = [
    {
      key: "/connections",
      icon: <ApiOutlined />,
      label: "Connections",
    },
    {
      key: "/projects",
      icon: <ProjectOutlined />,
      label: "Projects",
    },
  ];

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider theme="light" width={220}>
        <div
          style={{
            padding: "16px 20px",
            display: "flex",
            alignItems: "center",
            gap: 8,
            borderBottom: "1px solid #f0f0f0",
          }}
        >
          <SwapOutlined style={{ fontSize: 20, color: "#1677ff" }} />
          <Title level={5} style={{ margin: 0 }}>
            Migration Bridge
          </Title>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ borderRight: 0 }}
        />
        <div style={{ position: "absolute", bottom: 16, left: 16 }}>
          <Button
            type="text"
            icon={<LogoutOutlined />}
            onClick={onLogout}
            danger
          >
            Logout
          </Button>
        </div>
      </Sider>
      <Layout>
        <Content style={{ padding: 24, background: "#f5f5f5" }}>
          <Routes>
            <Route path="/connections" element={<ConnectionsPage />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route
              path="/projects/:projectId"
              element={<ProjectDetailPage />}
            />
            <Route path="*" element={<Navigate to="/projects" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}

export default function App() {
  const { isAuthenticated, loginUser, logout } = useAuth();

  if (!isAuthenticated) {
    return (
      <ConfigProvider theme={{ algorithm: theme.defaultAlgorithm }}>
        <LoginPage onLogin={loginUser} />
      </ConfigProvider>
    );
  }

  return (
    <ConfigProvider theme={{ algorithm: theme.defaultAlgorithm }}>
      <AppLayout onLogout={logout} />
    </ConfigProvider>
  );
}
