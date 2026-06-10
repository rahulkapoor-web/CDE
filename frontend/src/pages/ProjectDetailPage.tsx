import React, { useEffect, useState } from "react";
import {
  Card,
  Tabs,
  Table,
  Button,
  Modal,
  Select,
  Space,
  Tag,
  message,
  Popconfirm,
  Spin,
  Typography,
  Progress,
  Upload,
  Tooltip,
} from "antd";
import {
  PlusOutlined,
  DeleteOutlined,
  ThunderboltOutlined,
  DownloadOutlined,
  UploadOutlined,
  SyncOutlined,
  CheckCircleFilled,
  ExclamationCircleFilled,
  CloseCircleFilled,
} from "@ant-design/icons";
import { useParams } from "react-router-dom";
import {
  getProject,
  getSourceObjects,
  getTargetObjects,
  getObjectMappings,
  createObjectMapping,
  deleteObjectMapping,
  autoMapFields,
  applySuggestions,
  getFieldMappings,
  deleteFieldMapping,
  getMatchKeys,
  createMatchKey,
  deleteMatchKey,
  exportMappings,
  createValidationRun,
  getValidationRuns,
  getValidationSummaries,
  getValidationDetails,
  exportSummaryReport,
  exportDetailReport,
} from "../services/api";
import { downloadBlob } from "../utils/download";
import type {
  MigrationProject,
  ObjectMapping,
  FieldMapping,
  MatchKeyConfig,
  AutoMappingSuggestion,
  ValidationRun,
  ValidationSummary,
  ValidationDetail,
} from "../types";

const { Text, Title } = Typography;

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<MigrationProject | null>(null);
  const [sourceObjects, setSourceObjects] = useState<
    { name: string; label: string }[]
  >([]);
  const [targetObjects, setTargetObjects] = useState<
    { name: string; label: string }[]
  >([]);
  const [objectMappings, setObjectMappings] = useState<ObjectMapping[]>([]);
  const [loading, setLoading] = useState(false);

  // Mapping detail state
  const [selectedMapping, setSelectedMapping] = useState<ObjectMapping | null>(
    null
  );
  const [fieldMappings, setFieldMappings] = useState<FieldMapping[]>([]);
  const [matchKeys, setMatchKeys] = useState<MatchKeyConfig[]>([]);
  const [suggestions, setSuggestions] = useState<AutoMappingSuggestion[]>([]);
  const [suggestionsModalOpen, setSuggestionsModalOpen] = useState(false);

  // Add mapping modal
  const [addMappingOpen, setAddMappingOpen] = useState(false);
  const [newSourceObj, setNewSourceObj] = useState("");
  const [newTargetObj, setNewTargetObj] = useState("");

  // Validation state
  const [validationRuns, setValidationRuns] = useState<ValidationRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<ValidationRun | null>(null);
  const [summaries, setSummaries] = useState<ValidationSummary[]>([]);
  const [selectedSummary, setSelectedSummary] =
    useState<ValidationSummary | null>(null);
  const [details, setDetails] = useState<ValidationDetail[]>([]);
  const [detailsPage, setDetailsPage] = useState(1);
  const [detailsTotal, setDetailsTotal] = useState(0);

  useEffect(() => {
    if (projectId) loadProject();
  }, [projectId]);

  const loadProject = async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [projRes, mappingsRes, runsRes] = await Promise.all([
        getProject(projectId),
        getObjectMappings(projectId),
        getValidationRuns(projectId),
      ]);
      setProject(projRes.data);
      setObjectMappings(mappingsRes.data);
      setValidationRuns(runsRes.data);
    } finally {
      setLoading(false);
    }
  };

  const loadSchemas = async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [srcRes, tgtRes] = await Promise.all([
        getSourceObjects(projectId),
        getTargetObjects(projectId),
      ]);
      setSourceObjects(srcRes.data);
      setTargetObjects(tgtRes.data);
    } catch {
      message.error("Failed to load schemas. Check connection profiles.");
    } finally {
      setLoading(false);
    }
  };

  const handleAddMapping = async () => {
    if (!projectId || !newSourceObj || !newTargetObj) return;
    await createObjectMapping(projectId, {
      source_object: newSourceObj,
      target_object: newTargetObj,
    });
    message.success("Object mapping created");
    setAddMappingOpen(false);
    loadProject();
  };

  const handleDeleteMapping = async (id: string) => {
    if (!projectId) return;
    await deleteObjectMapping(projectId, id);
    message.success("Deleted");
    loadProject();
  };

  const handleAutoMap = async (mapping: ObjectMapping) => {
    if (!projectId) return;
    setSelectedMapping(mapping);
    try {
      const res = await autoMapFields(projectId, mapping.id);
      setSuggestions(res.data);
      setSuggestionsModalOpen(true);
    } catch {
      message.error("Auto-mapping failed");
    }
  };

  const handleApplySuggestions = async () => {
    if (!projectId || !selectedMapping) return;
    await applySuggestions(projectId, selectedMapping.id, suggestions);
    message.success("Mappings applied");
    setSuggestionsModalOpen(false);
    loadMappingDetails(selectedMapping);
  };

  const loadMappingDetails = async (mapping: ObjectMapping) => {
    if (!projectId) return;
    setSelectedMapping(mapping);
    const [fmRes, mkRes] = await Promise.all([
      getFieldMappings(projectId, mapping.id),
      getMatchKeys(projectId, mapping.id),
    ]);
    setFieldMappings(fmRes.data);
    setMatchKeys(mkRes.data);
  };

  const handleExportMappings = async (
    mappingId: string,
    format: string = "csv"
  ) => {
    if (!projectId) return;
    const res = await exportMappings(projectId, mappingId, format);
    downloadBlob(res.data, `mappings.${format === "excel" ? "xlsx" : "csv"}`);
  };

  // Validation
  const handleRunValidation = async (mode: string = "auto") => {
    if (!projectId) return;
    try {
      const res = await createValidationRun({
        project_id: projectId,
        mode,
      });
      message.success(
        `Validation ${mode === "batch" ? "queued" : "started"}: ${res.data.id}`
      );
      loadProject();
    } catch (err: any) {
      message.error(err.response?.data?.detail || "Failed to start validation");
    }
  };

  const loadRunSummaries = async (run: ValidationRun) => {
    setSelectedRun(run);
    const res = await getValidationSummaries(run.id);
    setSummaries(res.data);
    setSelectedSummary(null);
    setDetails([]);
  };

  const loadDetails = async (
    summary: ValidationSummary,
    page: number = 1,
    statusFilter?: string
  ) => {
    setSelectedSummary(summary);
    const res = await getValidationDetails(
      summary.id,
      page,
      50,
      statusFilter
    );
    setDetails(res.data.items);
    setDetailsTotal(res.data.total);
    setDetailsPage(page);
  };

  const handleExportSummary = async (runId: string) => {
    const res = await exportSummaryReport(runId);
    downloadBlob(res.data, "validation_summary.csv");
  };

  const handleExportDetails = async (summaryId: string) => {
    const res = await exportDetailReport(summaryId);
    downloadBlob(res.data, "validation_details.csv");
  };

  if (!project) return <Spin size="large" style={{ margin: 100 }} />;

  const objectMappingColumns = [
    {
      title: "Source Object",
      dataIndex: "source_object",
      key: "source_object",
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: "Target Object",
      dataIndex: "target_object",
      key: "target_object",
      render: (v: string) => <Tag color="green">{v}</Tag>,
    },
    {
      title: "Actions",
      key: "actions",
      render: (_: unknown, record: ObjectMapping) => (
        <Space>
          <Button size="small" onClick={() => loadMappingDetails(record)}>
            Fields
          </Button>
          <Button
            size="small"
            icon={<ThunderboltOutlined />}
            onClick={() => handleAutoMap(record)}
          >
            Auto-Map
          </Button>
          <Button
            size="small"
            icon={<DownloadOutlined />}
            onClick={() => handleExportMappings(record.id)}
          >
            Export
          </Button>
          <Popconfirm
            title="Delete?"
            onConfirm={() => handleDeleteMapping(record.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const fieldMappingColumns = [
    { title: "Source Field", dataIndex: "source_field", key: "source_field" },
    {
      title: "Source Type",
      dataIndex: "source_field_type",
      key: "source_field_type",
    },
    { title: "Target Field", dataIndex: "target_field", key: "target_field" },
    {
      title: "Target Type",
      dataIndex: "target_field_type",
      key: "target_field_type",
    },
    {
      title: "Confidence",
      dataIndex: "confidence_score",
      key: "confidence_score",
      render: (v: number | null) =>
        v != null ? (
          <Progress
            percent={Math.round(v * 100)}
            size="small"
            status={v >= 0.8 ? "success" : v >= 0.6 ? "normal" : "exception"}
          />
        ) : (
          "-"
        ),
    },
    {
      title: "Status",
      key: "status",
      render: (_: unknown, r: FieldMapping) =>
        r.is_confirmed ? (
          <Tag color="green">Confirmed</Tag>
        ) : (
          <Tag color="orange">Suggested</Tag>
        ),
    },
    {
      title: "",
      key: "actions",
      render: (_: unknown, r: FieldMapping) => (
        <Popconfirm
          title="Remove?"
          onConfirm={async () => {
            if (!projectId || !selectedMapping) return;
            await deleteFieldMapping(projectId, selectedMapping.id, r.id);
            loadMappingDetails(selectedMapping);
          }}
        >
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  const runStatusIcon = (status: string) => {
    switch (status) {
      case "completed":
        return <CheckCircleFilled style={{ color: "#52c41a" }} />;
      case "failed":
        return <CloseCircleFilled style={{ color: "#ff4d4f" }} />;
      case "running":
      case "queued":
        return <SyncOutlined spin style={{ color: "#1890ff" }} />;
      default:
        return <ExclamationCircleFilled style={{ color: "#faad14" }} />;
    }
  };

  return (
    <div>
      <Title level={4}>{project.name}</Title>
      <Text type="secondary">{project.description}</Text>

      <Tabs
        style={{ marginTop: 16 }}
        items={[
          {
            key: "mappings",
            label: "Data Model Mappings",
            children: (
              <div>
                <Card
                  title="Object Mappings"
                  extra={
                    <Space>
                      <Button onClick={loadSchemas} loading={loading}>
                        Load Schemas
                      </Button>
                      <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={() => {
                          if (!sourceObjects.length) {
                            message.info("Load schemas first");
                            return;
                          }
                          setAddMappingOpen(true);
                        }}
                      >
                        Add Mapping
                      </Button>
                    </Space>
                  }
                >
                  <Table
                    dataSource={objectMappings}
                    columns={objectMappingColumns}
                    rowKey="id"
                    size="small"
                  />
                </Card>

                {selectedMapping && (
                  <Card
                    title={`Field Mappings: ${selectedMapping.source_object} → ${selectedMapping.target_object}`}
                    style={{ marginTop: 16 }}
                  >
                    <Table
                      dataSource={fieldMappings}
                      columns={fieldMappingColumns}
                      rowKey="id"
                      size="small"
                      pagination={{ pageSize: 20 }}
                    />

                    <Card
                      title="Match Keys"
                      size="small"
                      style={{ marginTop: 16 }}
                    >
                      {matchKeys.map((mk) => (
                        <Tag
                          key={mk.id}
                          closable
                          onClose={async () => {
                            if (!projectId || !selectedMapping) return;
                            await deleteMatchKey(
                              projectId,
                              selectedMapping.id,
                              mk.id
                            );
                            loadMappingDetails(selectedMapping);
                          }}
                        >
                          {mk.source_field} ↔ {mk.target_field}
                        </Tag>
                      ))}
                      {matchKeys.length === 0 && (
                        <Text type="warning">
                          No match keys configured. Required for validation.
                        </Text>
                      )}
                    </Card>
                  </Card>
                )}
              </div>
            ),
          },
          {
            key: "validation",
            label: "Validation",
            children: (
              <div>
                <Card
                  title="Validation Runs"
                  extra={
                    <Space>
                      <Button
                        type="primary"
                        onClick={() => handleRunValidation("auto")}
                      >
                        Run Validation (Auto)
                      </Button>
                      <Button onClick={() => handleRunValidation("batch")}>
                        Run Batch
                      </Button>
                    </Space>
                  }
                >
                  <Table
                    dataSource={validationRuns}
                    rowKey="id"
                    size="small"
                    columns={[
                      {
                        title: "Status",
                        dataIndex: "status",
                        key: "status",
                        render: (v: string) => (
                          <Space>
                            {runStatusIcon(v)} {v}
                          </Space>
                        ),
                      },
                      { title: "Mode", dataIndex: "mode", key: "mode" },
                      {
                        title: "Created",
                        dataIndex: "created_at",
                        key: "created_at",
                        render: (v: string) =>
                          new Date(v).toLocaleString(),
                      },
                      {
                        title: "Actions",
                        key: "actions",
                        render: (_: unknown, r: ValidationRun) => (
                          <Space>
                            <Button
                              size="small"
                              onClick={() => loadRunSummaries(r)}
                            >
                              View Results
                            </Button>
                            <Button
                              size="small"
                              icon={<DownloadOutlined />}
                              onClick={() => handleExportSummary(r.id)}
                            >
                              Export
                            </Button>
                          </Space>
                        ),
                      },
                    ]}
                  />
                </Card>

                {selectedRun && (
                  <Card
                    title={`Results: Run ${selectedRun.id.slice(0, 8)}...`}
                    style={{ marginTop: 16 }}
                  >
                    <Table
                      dataSource={summaries}
                      rowKey="id"
                      size="small"
                      columns={[
                        {
                          title: "Source",
                          dataIndex: "source_object",
                          key: "source_object",
                        },
                        {
                          title: "Target",
                          dataIndex: "target_object",
                          key: "target_object",
                        },
                        {
                          title: "Source Count",
                          dataIndex: "source_count",
                          key: "source_count",
                        },
                        {
                          title: "Target Count",
                          dataIndex: "target_count",
                          key: "target_count",
                        },
                        {
                          title: "Matched",
                          dataIndex: "matched_count",
                          key: "matched_count",
                          render: (v: number) => (
                            <Text type="success">{v}</Text>
                          ),
                        },
                        {
                          title: "Mismatched",
                          dataIndex: "mismatched_count",
                          key: "mismatched_count",
                          render: (v: number) =>
                            v > 0 ? (
                              <Text type="warning">{v}</Text>
                            ) : (
                              v
                            ),
                        },
                        {
                          title: "Missing in Target",
                          dataIndex: "missing_in_target_count",
                          key: "missing_in_target",
                          render: (v: number) =>
                            v > 0 ? (
                              <Text type="danger">{v}</Text>
                            ) : (
                              v
                            ),
                        },
                        {
                          title: "Match %",
                          dataIndex: "match_percentage",
                          key: "match_pct",
                          render: (v: number) => (
                            <Progress
                              percent={Math.round(v)}
                              size="small"
                              status={
                                v >= 95
                                  ? "success"
                                  : v >= 80
                                  ? "normal"
                                  : "exception"
                              }
                            />
                          ),
                        },
                        {
                          title: "",
                          key: "actions",
                          render: (_: unknown, r: ValidationSummary) => (
                            <Space>
                              <Button
                                size="small"
                                onClick={() => loadDetails(r)}
                              >
                                Details
                              </Button>
                              <Button
                                size="small"
                                icon={<DownloadOutlined />}
                                onClick={() => handleExportDetails(r.id)}
                              />
                            </Space>
                          ),
                        },
                      ]}
                    />
                  </Card>
                )}

                {selectedSummary && (
                  <Card
                    title={`Record Details: ${selectedSummary.source_object} → ${selectedSummary.target_object}`}
                    style={{ marginTop: 16 }}
                    extra={
                      <Select
                        placeholder="Filter by status"
                        allowClear
                        style={{ width: 200 }}
                        onChange={(v) => loadDetails(selectedSummary, 1, v)}
                      >
                        <Select.Option value="missing_in_target">
                          Missing in Target
                        </Select.Option>
                        <Select.Option value="missing_in_source">
                          Missing in Source
                        </Select.Option>
                        <Select.Option value="mismatched">
                          Mismatched
                        </Select.Option>
                      </Select>
                    }
                  >
                    <Table
                      dataSource={details}
                      rowKey="id"
                      size="small"
                      pagination={{
                        current: detailsPage,
                        total: detailsTotal,
                        pageSize: 50,
                        onChange: (p) => loadDetails(selectedSummary, p),
                      }}
                      columns={[
                        {
                          title: "Match Key",
                          dataIndex: "match_key_value",
                          key: "match_key",
                        },
                        {
                          title: "Status",
                          dataIndex: "status",
                          key: "status",
                          render: (v: string) => {
                            const colors: Record<string, string> = {
                              matched: "green",
                              mismatched: "orange",
                              missing_in_target: "red",
                              missing_in_source: "purple",
                            };
                            return <Tag color={colors[v] || "default"}>{v}</Tag>;
                          },
                        },
                        {
                          title: "Field Differences",
                          dataIndex: "field_diffs",
                          key: "diffs",
                          render: (
                            diffs: Record<string, { source: unknown; target: unknown }> | null
                          ) => {
                            if (!diffs) return "-";
                            return Object.entries(diffs).map(
                              ([field, diff]) => (
                                <div key={field} style={{ marginBottom: 4 }}>
                                  <Text strong>{field}: </Text>
                                  <Text type="danger">
                                    {String(diff.source ?? "null")}
                                  </Text>
                                  {" → "}
                                  <Text type="success">
                                    {String(diff.target ?? "null")}
                                  </Text>
                                </div>
                              )
                            );
                          },
                        },
                      ]}
                    />
                  </Card>
                )}
              </div>
            ),
          },
        ]}
      />

      {/* Add Object Mapping Modal */}
      <Modal
        title="Add Object Mapping"
        open={addMappingOpen}
        onCancel={() => setAddMappingOpen(false)}
        onOk={handleAddMapping}
      >
        <div style={{ marginBottom: 16 }}>
          <Text>Source Object (Salesforce)</Text>
          <Select
            showSearch
            style={{ width: "100%", marginTop: 4 }}
            value={newSourceObj || undefined}
            onChange={setNewSourceObj}
            placeholder="Select source object"
            filterOption={(input, option) =>
              (option?.children as unknown as string)
                ?.toLowerCase()
                .includes(input.toLowerCase()) ?? false
            }
          >
            {sourceObjects.map((o) => (
              <Select.Option key={o.name} value={o.name}>
                {o.label} ({o.name})
              </Select.Option>
            ))}
          </Select>
        </div>
        <div>
          <Text>Target Object (Veeva Vault)</Text>
          <Select
            showSearch
            style={{ width: "100%", marginTop: 4 }}
            value={newTargetObj || undefined}
            onChange={setNewTargetObj}
            placeholder="Select target object"
            filterOption={(input, option) =>
              (option?.children as unknown as string)
                ?.toLowerCase()
                .includes(input.toLowerCase()) ?? false
            }
          >
            {targetObjects.map((o) => (
              <Select.Option key={o.name} value={o.name}>
                {o.label} ({o.name})
              </Select.Option>
            ))}
          </Select>
        </div>
      </Modal>

      {/* Auto-Mapping Suggestions Modal */}
      <Modal
        title="Auto-Mapping Suggestions"
        open={suggestionsModalOpen}
        onCancel={() => setSuggestionsModalOpen(false)}
        onOk={handleApplySuggestions}
        okText="Apply All"
        width={800}
      >
        <Table
          dataSource={suggestions}
          rowKey={(r) => `${r.source_field}-${r.target_field}`}
          size="small"
          pagination={false}
          columns={[
            {
              title: "Source Field",
              dataIndex: "source_field",
              key: "source_field",
            },
            {
              title: "Source Type",
              dataIndex: "source_field_type",
              key: "source_type",
            },
            {
              title: "Target Field",
              dataIndex: "target_field",
              key: "target_field",
            },
            {
              title: "Target Type",
              dataIndex: "target_field_type",
              key: "target_type",
            },
            {
              title: "Confidence",
              dataIndex: "confidence_score",
              key: "confidence",
              render: (v: number) => (
                <Progress
                  percent={Math.round(v * 100)}
                  size="small"
                  status={
                    v >= 0.8 ? "success" : v >= 0.6 ? "normal" : "exception"
                  }
                />
              ),
            },
            {
              title: "Reason",
              dataIndex: "match_reason",
              key: "reason",
              render: (v: string) => <Text type="secondary">{v}</Text>,
            },
          ]}
        />
      </Modal>
    </div>
  );
}
