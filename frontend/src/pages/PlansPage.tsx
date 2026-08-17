import { Card, Table, Tag } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { planningApi } from "../services/api";
import type { PlanSummary } from "../types";

export default function PlansPage() {
  const [plans, setPlans] = useState<PlanSummary[]>([]);
  const navigate = useNavigate();

  useEffect(() => {
    planningApi.listPlans().then(setPlans);
  }, []);

  return (
    <Card title="Plan History">
      <Table<PlanSummary>
        rowKey="id"
        dataSource={plans}
        onRow={(r) => ({ onClick: () => navigate(`/plans/${r.id}`), style: { cursor: "pointer" } })}
        columns={[
          { title: "JIRA", dataIndex: "jira_ticket", width: 140 },
          { title: "Summary", dataIndex: "summary" },
          {
            title: "Status",
            dataIndex: "status",
            width: 120,
            render: (s: string) => <Tag color="green">{s}</Tag>,
          },
          {
            title: "Created",
            dataIndex: "created_at",
            width: 200,
            render: (d: string) => new Date(d).toLocaleString(),
          },
        ]}
      />
    </Card>
  );
}
