import { Avatar, Dropdown, Layout, Menu } from "antd";
import {
  ApiOutlined,
  LogoutOutlined,
  ThunderboltOutlined,
  UnorderedListOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "./hooks/useAuth";
import Logo from "./components/Logo";
import LoginPage from "./pages/LoginPage";
import ConnectionsPage from "./pages/ConnectionsPage";
import GeneratePage from "./pages/GeneratePage";
import PlansPage from "./pages/PlansPage";
import PlanDetailPage from "./pages/PlanDetailPage";

const { Header, Content } = Layout;

function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  return <>{children}</>;
}

export default function App() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const selectedKey = "/" + (location.pathname.split("/")[1] || "generate");

  return (
    <Layout style={{ minHeight: "100vh" }}>
      {user && (
        <Header
          style={{
            display: "flex",
            alignItems: "center",
            gap: 32,
            paddingInline: 24,
            background: "#0b1220",
            position: "sticky",
            top: 0,
            zIndex: 10,
            boxShadow: "0 1px 0 rgba(255,255,255,0.06)",
          }}
        >
          <div
            style={{ cursor: "pointer", flexShrink: 0 }}
            onClick={() => navigate("/generate")}
          >
            <Logo size={34} />
          </div>
          <Menu
            theme="dark"
            mode="horizontal"
            selectedKeys={[selectedKey]}
            style={{ flex: 1, minWidth: 0, background: "transparent" }}
            onClick={({ key }) => navigate(key)}
            items={[
              {
                key: "/generate",
                label: "Generate",
                icon: <ThunderboltOutlined />,
              },
              { key: "/plans", label: "Plans", icon: <UnorderedListOutlined /> },
              {
                key: "/connections",
                label: "Connections",
                icon: <ApiOutlined />,
              },
            ]}
          />
          <Dropdown
            placement="bottomRight"
            menu={{
              items: [
                {
                  key: "email",
                  label: user.email,
                  disabled: true,
                },
                { type: "divider" },
                {
                  key: "logout",
                  label: "Log out",
                  icon: <LogoutOutlined />,
                  onClick: () => {
                    logout();
                    navigate("/login");
                  },
                },
              ],
            }}
          >
            <Avatar
              style={{
                backgroundColor: "#1677ff",
                cursor: "pointer",
                flexShrink: 0,
              }}
              icon={<UserOutlined />}
            />
          </Dropdown>
        </Header>
      )}
      <Content style={{ padding: user ? 24 : 0 }}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/generate"
            element={<RequireAuth><GeneratePage /></RequireAuth>}
          />
          <Route
            path="/plans"
            element={<RequireAuth><PlansPage /></RequireAuth>}
          />
          <Route
            path="/plans/:id"
            element={<RequireAuth><PlanDetailPage /></RequireAuth>}
          />
          <Route
            path="/connections"
            element={<RequireAuth><ConnectionsPage /></RequireAuth>}
          />
          <Route path="*" element={<Navigate to={user ? "/generate" : "/login"} replace />} />
        </Routes>
      </Content>
    </Layout>
  );
}
