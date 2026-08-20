import { Layout, Menu } from "antd";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "./hooks/useAuth";
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
        <Header style={{ display: "flex", alignItems: "center" }}>
          <div style={{ color: "#fff", fontWeight: 600, marginRight: 32 }}>
            ONA Planning Engine
          </div>
          <Menu
            theme="dark"
            mode="horizontal"
            selectedKeys={[selectedKey]}
            style={{ flex: 1, minWidth: 0 }}
            onClick={({ key }) => navigate(key)}
            items={[
              { key: "/generate", label: "Generate" },
              { key: "/plans", label: "Plans" },
              { key: "/connections", label: "Connections" },
            ]}
          />
          <a style={{ color: "#fff" }} onClick={() => { logout(); navigate("/login"); }}>
            Logout ({user.email})
          </a>
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
