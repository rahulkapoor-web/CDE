import React, { useState } from "react";
import {
  Routes,
  Route,
  Navigate,
  useNavigate,
  useLocation,
} from "react-router-dom";
import {
  Layout,
  Menu,
  Button,
  Typography,
  ConfigProvider,
  theme,
  Avatar,
  Tooltip,
  Badge,
} from "antd";
import {
  ApiOutlined,
  ProjectOutlined,
  LogoutOutlined,
  SwapOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  DashboardOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { useAuth } from "./hooks/useAuth";
import LoginPage from "./pages/LoginPage";
import ConnectionsPage from "./pages/ConnectionsPage";
import ProjectsPage from "./pages/ProjectsPage";
import ProjectDetailPage from "./pages/ProjectDetailPage";

const { Sider, Content } = Layout;
const { Title, Text } = Typography;

function AppLayout({ onLogout }: { onLogout: () => void }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);

  const menuItems = [
    {
      key: "/projects",
      icon: <DashboardOutlined />,
      label: "Projects",
    },
    {
      key: "/connections",
      icon: <ApiOutlined />,
      label: "Connections",
    },
  ];

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        trigger={null}
        width={240}
        collapsedWidth={72}
        style={{
          background: "linear-gradient(180deg, #1a1f3d 0%, #2d1b69 100%)",
          overflow: "auto",
          height: "100vh",
          position: "fixed",
          left: 0,
          top: 0,
          bottom: 0,
          zIndex: 10,
          boxShadow: "4px 0 20px rgba(0,0,0,0.15)",
        }}
      >
        {/* Logo area */}
        <div
          style={{
            padding: collapsed ? "20px 12px" : "20px 20px",
            display: "flex",
            alignItems: "center",
            gap: 10,
            borderBottom: "1px solid rgba(255,255,255,0.08)",
            marginBottom: 8,
            justifyContent: collapsed ? "center" : "flex-start",
          }}
        >
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 10,
              background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
            }}
          >
            <SwapOutlined style={{ fontSize: 18, color: "#fff" }} />
          </div>
          {!collapsed && (
            <div style={{ overflow: "hidden" }}>
              <Title
                level={5}
                style={{
                  margin: 0,
                  color: "#fff",
                  whiteSpace: "nowrap",
                  fontSize: 15,
                }}
              >
                Migration Bridge
              </Title>
              <Text
                style={{
                  color: "rgba(255,255,255,0.45)",
                  fontSize: 11,
                }}
              >
                CRM Data Platform
              </Text>
            </div>
          )}
        </div>

        {/* Collapse toggle */}
        <div
          style={{
            padding: "4px 12px 12px",
            display: "flex",
            justifyContent: collapsed ? "center" : "flex-end",
          }}
        >
          <Button
            type="text"
            icon={
              collapsed ? (
                <MenuUnfoldOutlined style={{ color: "rgba(255,255,255,0.5)" }} />
              ) : (
                <MenuFoldOutlined style={{ color: "rgba(255,255,255,0.5)" }} />
              )
            }
            onClick={() => setCollapsed(!collapsed)}
            size="small"
          />
        </div>

        {/* Navigation */}
        <Menu
          mode="inline"
          selectedKeys={[
            location.pathname.startsWith("/projects")
              ? "/projects"
              : location.pathname,
          ]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{
            background: "transparent",
            border: "none",
          }}
          theme="dark"
        />

        {/* User section at bottom */}
        <div
          style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            padding: collapsed ? "16px 12px" : "16px 20px",
            borderTop: "1px solid rgba(255,255,255,0.08)",
            display: "flex",
            alignItems: "center",
            gap: 10,
            justifyContent: collapsed ? "center" : "flex-start",
          }}
        >
          <Badge dot status="success" offset={[-4, 28]}>
            <Avatar
              size={32}
              icon={<UserOutlined />}
              style={{
                background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
                cursor: "pointer",
              }}
            />
          </Badge>
          {!collapsed && (
            <div style={{ flex: 1, overflow: "hidden" }}>
              <Text
                style={{
                  color: "#fff",
                  fontSize: 13,
                  display: "block",
                  whiteSpace: "nowrap",
                }}
              >
                Admin User
              </Text>
              <Text
                style={{
                  color: "rgba(255,255,255,0.4)",
                  fontSize: 11,
                }}
              >
                Online
              </Text>
            </div>
          )}
          <Tooltip title="Sign out">
            <Button
              type="text"
              icon={<LogoutOutlined style={{ color: "rgba(255,255,255,0.5)" }} />}
              onClick={onLogout}
              size="small"
              style={{
                display: collapsed ? "none" : "inline-flex",
              }}
            />
          </Tooltip>
        </div>
      </Sider>

      <Layout
        style={{
          marginLeft: collapsed ? 72 : 240,
          transition: "margin-left 0.2s ease",
        }}
      >
        <Content
          style={{
            padding: 28,
            background: "#f5f7fa",
            minHeight: "100vh",
          }}
        >
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
      <ConfigProvider
        theme={{
          algorithm: theme.defaultAlgorithm,
          token: {
            colorPrimary: "#667eea",
            borderRadius: 8,
            fontFamily:
              "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
          },
        }}
      >
        <LoginPage onLogin={loginUser} />
      </ConfigProvider>
    );
  }

  return (
    <ConfigProvider
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: "#667eea",
          borderRadius: 8,
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        },
        components: {
          Card: {
            borderRadiusLG: 12,
          },
          Table: {
            borderRadiusLG: 12,
          },
          Button: {
            borderRadius: 8,
          },
        },
      }}
    >
      <AppLayout onLogout={logout} />
    </ConfigProvider>
  );
}
