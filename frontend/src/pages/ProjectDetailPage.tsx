import React, { useEffect, useRef, useState } from "react";
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
  InputNumber,
  Input,
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
  LoadingOutlined,
  CloudSyncOutlined,
  SwapOutlined,
} from "@ant-design/icons";
import { useParams } from "react-router-dom";
import {
  getProject,
  getSourceObjects,
  getTargetObjects,
  describeSourceObject,
  describeTargetObject,
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
  importMappingSheet,
  createValidationRun,
  cancelValidationRun,
  getValidationRun,
  getValidationRuns,
  createCleanupJob,
  getCleanupJobs,
  getCleanupJob,
  cancelCleanupJob,
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

  // Add match key modal
  const [addMatchKeyOpen, setAddMatchKeyOpen] = useState(false);
  const [newMatchKeySource, setNewMatchKeySource] = useState("");
  const [newMatchKeyTarget, setNewMatchKeyTarget] = useState("");
  const [sourceFields, setSourceFields] = useState<{ name: string; label: string }[]>([]);
  const [targetFields, setTargetFields] = useState<{ name: string; label: string }[]>([]);

  // Validation state
  const [validationRuns, setValidationRuns] = useState<ValidationRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<ValidationRun | null>(null);
  const [summaries, setSummaries] = useState<ValidationSummary[]>([]);
  const [selectedSummary, setSelectedSummary] =
    useState<ValidationSummary | null>(null);
  const [details, setDetails] = useState<ValidationDetail[]>([]);
  const [detailsPage, setDetailsPage] = useState(1);
  const [detailsTotal, setDetailsTotal] = useState(0);

  // Cleanup state
  const [cleanupJobs, setCleanupJobs] = useState<any[]>([]);
  const [cleanupModalOpen, setCleanupModalOpen] = useState(false);
  const [cleanupFilterMode, setCleanupFilterMode] = useState("legacy_crm_id");
  const [cleanupCountryCode, setCleanupCountryCode] = useState("");
  const cleanupPollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Validation run modal
  const [runValidationOpen, setRunValidationOpen] = useState(false);
  const [runValidationMode, setRunValidationMode] = useState("auto");
  const [selectedObjectMappingIds, setSelectedObjectMappingIds] = useState<string[]>([]);
  const [recordLimit, setRecordLimit] = useState<number | null>(null);
  const [dateRangeMonths, setDateRangeMonths] = useState<number | null>(null);
  const [sourceWhereClause, setSourceWhereClause] = useState<string>("");

  // Poll running validation runs every 3 seconds
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const hasRunning = validationRuns.some((r) =>
      ["running", "queued", "pending"].includes(r.status)
    );

    if (hasRunning && !pollingRef.current) {
      pollingRef.current = setInterval(async () => {
        try {
          const runningIds = validationRuns
            .filter((r) => ["running", "queued", "pending"].includes(r.status))
            .map((r) => r.id);

          const results = await Promise.all(
            runningIds.map((id) => getValidationRun(id))
          );

          setValidationRuns((prev) => {
            const updated = [...prev];
            for (const res of results) {
              const idx = updated.findIndex((r) => r.id === res.data.id);
              if (idx >= 0) updated[idx] = res.data;
            }
            return updated;
          });
        } catch {
          // ignore polling errors
        }
      }, 3000);
    }

    if (!hasRunning && pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [validationRuns]);

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

    // Load source and target field schemas for match key selection
    try {
      const [srcSchema, tgtSchema] = await Promise.all([
        describeSourceObject(projectId, mapping.source_object),
        describeTargetObject(projectId, mapping.target_object),
      ]);
      setSourceFields(srcSchema.data.fields.map((f: any) => ({ name: f.name, label: f.label })));
      setTargetFields(tgtSchema.data.fields.map((f: any) => ({ name: f.name, label: f.label })));
    } catch {
      // Non-critical — match key dropdowns will be empty
    }
  };

  const handleAddMatchKey = async () => {
    if (!projectId || !selectedMapping || !newMatchKeySource || !newMatchKeyTarget) return;
    try {
      await createMatchKey(projectId, selectedMapping.id, {
        source_field: newMatchKeySource,
        target_field: newMatchKeyTarget,
        key_order: matchKeys.length,
      });
      message.success("Match key added");
      setAddMatchKeyOpen(false);
      setNewMatchKeySource("");
      setNewMatchKeyTarget("");
      loadMappingDetails(selectedMapping);
    } catch (err: any) {
      message.error(err.response?.data?.detail || "Failed to add match key");
    }
  };

  const handleImportSheet = async (file: File) => {
    if (!projectId) return;
    try {
      const res = await importMappingSheet(projectId, file);
      message.success(res.data.detail);
      loadProject();
    } catch (err: any) {
      message.error(err.response?.data?.detail || "Import failed");
    }
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
  const handleRunValidation = async () => {
    if (!projectId) return;
    try {
      const res = await createValidationRun({
        project_id: projectId,
        mode: runValidationMode,
        object_mapping_ids: selectedObjectMappingIds.length > 0 ? selectedObjectMappingIds : undefined,
        record_limit: recordLimit || undefined,
        date_range_months: dateRangeMonths || undefined,
        source_where_clause: sourceWhereClause.trim() || undefined,
      });
      message.success(
        `Validation ${runValidationMode === "batch" ? "queued" : "started"}: ${res.data.id.slice(0, 8)}...`
      );
      setRunValidationOpen(false);
      setSelectedObjectMappingIds([]);
      setRecordLimit(null);
      setDateRangeMonths(null);
      setSourceWhereClause("");
      loadProject();
    } catch (err: any) {
      message.error(err.response?.data?.detail || "Failed to start validation");
    }
  };

  const handleCancelRun = async (runId: string) => {
    try {
      await cancelValidationRun(runId);
      message.success("Validation run cancelled");
      loadProject();
    } catch (err: any) {
      message.error(err.response?.data?.detail || "Failed to cancel");
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

  // Cleanup handlers
  const loadCleanupJobs = async () => {
    if (!projectId) return;
    try {
      const res = await getCleanupJobs(projectId);
      setCleanupJobs(res.data);
    } catch {
      // ignore
    }
  };

  const handleStartCleanup = async () => {
    if (!projectId) return;
    try {
      await createCleanupJob({
        project_id: projectId,
        filter_mode: cleanupFilterMode,
        country_code: cleanupFilterMode === "country" ? cleanupCountryCode : undefined,
      });
      message.success("Cleanup job started");
      setCleanupModalOpen(false);
      setCleanupCountryCode("");
      loadCleanupJobs();
    } catch (e: any) {
      message.error(e.response?.data?.detail || "Failed to start cleanup");
    }
  };

  const handleCancelCleanup = async (jobId: string) => {
    try {
      await cancelCleanupJob(jobId);
      message.success("Cleanup cancelled");
      loadCleanupJobs();
    } catch (e: any) {
      message.error(e.response?.data?.detail || "Failed to cancel");
    }
  };

  // Poll running cleanup jobs
  useEffect(() => {
    const hasRunning = cleanupJobs.some((j) => j.status === "running");
    if (hasRunning && !cleanupPollingRef.current) {
      cleanupPollingRef.current = setInterval(async () => {
        try {
          const running = cleanupJobs.filter((j) => j.status === "running");
          const results = await Promise.all(running.map((j) => getCleanupJob(j.id)));
          setCleanupJobs((prev) => {
            const updated = [...prev];
            for (const res of results) {
              const idx = updated.findIndex((j) => j.id === res.data.id);
              if (idx >= 0) updated[idx] = res.data;
            }
            return updated;
          });
        } catch { /* ignore */ }
      }, 3000);
    }
    if (!hasRunning && cleanupPollingRef.current) {
      clearInterval(cleanupPollingRef.current);
      cleanupPollingRef.current = null;
    }
    return () => {
      if (cleanupPollingRef.current) {
        clearInterval(cleanupPollingRef.current);
        cleanupPollingRef.current = null;
      }
    };
  }, [cleanupJobs]);

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
      case "cancelled":
        return <ExclamationCircleFilled style={{ color: "#d9d9d9" }} />;
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
                      <Upload
                        accept=".xlsx,.xls,.csv"
                        showUploadList={false}
                        beforeUpload={(file) => {
                          handleImportSheet(file as unknown as File);
                          return false;
                        }}
                      >
                        <Button icon={<UploadOutlined />}>
                          Import Mapping Sheet
                        </Button>
                      </Upload>
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
                      extra={
                        <Button
                          size="small"
                          type="primary"
                          icon={<PlusOutlined />}
                          onClick={() => setAddMatchKeyOpen(true)}
                        >
                          Add Match Key
                        </Button>
                      }
                    >
                      {matchKeys.map((mk) => (
                        <Tag
                          key={mk.id}
                          closable
                          color="blue"
                          style={{ marginBottom: 4 }}
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
                    <Button
                      type="primary"
                      onClick={() => setRunValidationOpen(true)}
                    >
                      New Validation Run
                    </Button>
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
                        width: 120,
                        render: (v: string) => (
                          <Space>
                            {runStatusIcon(v)} {v}
                          </Space>
                        ),
                      },
                      {
                        title: "Progress",
                        key: "progress",
                        width: 320,
                        render: (_: unknown, r: ValidationRun) => {
                          const status = r.status;
                          if (!["running", "queued", "pending"].includes(status)) {
                            if (status === "completed") return <Tag color="green">Done</Tag>;
                            if (status === "failed") return <Tag color="red">Failed</Tag>;
                            if (status === "cancelled") return <Tag color="default">Cancelled</Tag>;
                            return "-";
                          }

                          const phase = r.progress_phase;
                          const total = r.total_objects || 0;
                          const completed = r.completed_objects || 0;
                          const current = r.current_object_name;
                          const objPct = total > 0 ? Math.round((completed / total) * 100) : 0;

                          return (
                            <div style={{ minWidth: 260 }}>
                              {/* Object-level progress */}
                              {total > 0 && (
                                <div style={{ marginBottom: 6 }}>
                                  <Progress
                                    percent={objPct}
                                    size="small"
                                    status="active"
                                    format={() => `Object ${completed + 1} of ${total}`}
                                    style={{ marginBottom: 2 }}
                                  />
                                </div>
                              )}

                              {/* Current object name */}
                              {current && (
                                <div style={{ fontSize: 12, fontWeight: 500, marginBottom: 4 }}>
                                  <SwapOutlined style={{ marginRight: 4, color: "#1890ff" }} />
                                  {current}
                                </div>
                              )}

                              {/* Phase-specific live counters */}
                              {phase === "fetching_source" && (() => {
                                const fetched = r.source_records_fetched;
                                const limit = r.record_limit;
                                const elapsed = r.started_at
                                  ? (Date.now() - new Date(r.started_at).getTime()) / 1000
                                  : 0;
                                const rate = elapsed > 0 ? fetched / elapsed : 0;
                                const eta = limit && rate > 0
                                  ? Math.round((limit - fetched) / rate)
                                  : null;
                                return (
                                  <div style={{ fontSize: 11, color: "#888" }}>
                                    <CloudSyncOutlined spin style={{ marginRight: 4, color: "#1890ff" }} />
                                    Fetching source records...
                                    <span style={{ fontWeight: 600, marginLeft: 4 }}>
                                      {fetched.toLocaleString()}
                                      {limit ? ` / ${limit.toLocaleString()}` : ""} fetched
                                    </span>
                                    {eta !== null && eta > 0 && (
                                      <span style={{ marginLeft: 8, color: "#aaa" }}>
                                        ~{eta < 60 ? `${eta}s` : `${Math.round(eta / 60)}m`} left
                                      </span>
                                    )}
                                  </div>
                                );
                              })()}
                              {phase === "fetching_target" && (() => {
                                const fetched = r.target_records_fetched;
                                const limit = r.record_limit;
                                const elapsed = r.started_at
                                  ? (Date.now() - new Date(r.started_at).getTime()) / 1000
                                  : 0;
                                // Estimate rate from source fetch (similar size expected)
                                const srcRate = r.source_records_fetched > 0 && elapsed > 0
                                  ? r.source_records_fetched / elapsed
                                  : 0;
                                const eta = limit && srcRate > 0
                                  ? Math.round((limit - fetched) / srcRate)
                                  : null;
                                return (
                                  <div style={{ fontSize: 11, color: "#888" }}>
                                    <CloudSyncOutlined spin style={{ marginRight: 4, color: "#52c41a" }} />
                                    Fetching target records...
                                    <span style={{ fontWeight: 600, marginLeft: 4 }}>
                                      {fetched.toLocaleString()}
                                      {limit ? ` / ${limit.toLocaleString()}` : ""} fetched
                                    </span>
                                    <span style={{ marginLeft: 8, color: "#bbb" }}>
                                      (source: {r.source_records_fetched.toLocaleString()})
                                    </span>
                                    {eta !== null && eta > 0 && (
                                      <span style={{ marginLeft: 8, color: "#aaa" }}>
                                        ~{eta < 60 ? `${eta}s` : `${Math.round(eta / 60)}m`} left
                                      </span>
                                    )}
                                  </div>
                                );
                              })()}
                              {phase === "comparing" && (() => {
                                const compared = r.records_compared;
                                const total = r.total_records_to_compare;
                                const pct = total > 0 ? Math.round((compared / total) * 100) : 0;
                                return (
                                  <div style={{ fontSize: 11, color: "#888" }}>
                                    <LoadingOutlined style={{ marginRight: 4, color: "#faad14" }} />
                                    Comparing records... {pct}%
                                    <span style={{ fontWeight: 600, marginLeft: 4 }}>
                                      {compared.toLocaleString()}
                                      {total > 0 && ` / ${total.toLocaleString()}`}
                                    </span>
                                  </div>
                                );
                              })()}
                              {phase === "connecting" && (
                                <div style={{ fontSize: 11, color: "#888" }}>
                                  <SyncOutlined spin style={{ marginRight: 4, color: "#722ed1" }} />
                                  Connecting to source & target systems...
                                </div>
                              )}
                              {phase === "initializing" && (
                                <div style={{ fontSize: 11, color: "#888" }}>
                                  <SyncOutlined spin style={{ marginRight: 4 }} />
                                  Initializing validation run...
                                </div>
                              )}
                              {phase === "running" && (
                                <div style={{ fontSize: 11, color: "#888" }}>
                                  <LoadingOutlined style={{ marginRight: 4 }} />
                                  Processing...
                                </div>
                              )}
                              {!phase && (
                                <div style={{ fontSize: 11, color: "#888" }}>
                                  <SyncOutlined spin style={{ marginRight: 4 }} />
                                  Starting...
                                </div>
                              )}
                            </div>
                          );
                        },
                      },
                      { title: "Mode", dataIndex: "mode", key: "mode" },
                      {
                        title: "Objects",
                        key: "objects",
                        render: (_: unknown, r: ValidationRun) => (
                          <Space direction="vertical" size={0}>
                            <span>{r.object_mapping_ids ? `${r.object_mapping_ids.length} selected` : "All"}</span>
                            {r.source_where_clause && (
                              <Tooltip title={r.source_where_clause}>
                                <Tag color="geekblue" style={{ fontSize: 10, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                  WHERE {r.source_where_clause.length > 25 ? r.source_where_clause.slice(0, 25) + "..." : r.source_where_clause}
                                </Tag>
                              </Tooltip>
                            )}
                            {r.date_range_months && (
                              <Tag color="purple" style={{ fontSize: 10 }}>
                                Last {r.date_range_months} {r.date_range_months === 1 ? "month" : "months"}
                              </Tag>
                            )}
                            {r.record_limit && (
                              <Tag color="blue" style={{ fontSize: 10 }}>
                                Limit: {r.record_limit.toLocaleString()} per object
                              </Tag>
                            )}
                          </Space>
                        ),
                      },
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
                              disabled={["running", "queued", "pending"].includes(r.status)}
                            >
                              View Results
                            </Button>
                            <Button
                              size="small"
                              icon={<DownloadOutlined />}
                              onClick={() => handleExportSummary(r.id)}
                              disabled={["running", "queued", "pending"].includes(r.status)}
                            >
                              Export
                            </Button>
                            {["running", "queued", "pending"].includes(r.status) && (
                              <Popconfirm
                                title="Cancel this validation run?"
                                onConfirm={() => handleCancelRun(r.id)}
                              >
                                <Button size="small" danger>
                                  Cancel
                                </Button>
                              </Popconfirm>
                            )}
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
                          render: (v: number, r: ValidationSummary) => {
                            if (r.status === "failed") {
                              return (
                                <Tooltip title={r.error_message || "Validation failed"}>
                                  <Tag color="red">Error</Tag>
                                </Tooltip>
                              );
                            }
                            if (r.source_count === 0 && r.target_count === 0) {
                              return <Tag color="orange">No data</Tag>;
                            }
                            return (
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
                            );
                          },
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
                        <Select.Option value="matched">
                          Matched
                        </Select.Option>
                        <Select.Option value="mismatched">
                          Mismatched
                        </Select.Option>
                        <Select.Option value="missing_in_target">
                          Missing in Target
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
                      expandable={{
                        expandedRowRender: (record: ValidationDetail) => {
                          const diffs = record.field_diffs;
                          if (!diffs || Object.keys(diffs).length === 0) {
                            return <Text type="secondary">No field data available</Text>;
                          }
                          const entries = Object.entries(diffs) as [string, any][];
                          const mismatches = entries.filter((e) => e[1].diff_type !== "match");
                          const matches = entries.filter((e) => e[1].diff_type === "match");

                          return (
                            <div>
                              {mismatches.length > 0 && (
                                <>
                                  <Text strong style={{ color: "#cf1322", display: "block", marginBottom: 8 }}>
                                    Issues ({mismatches.length})
                                  </Text>
                                  <Table
                                    dataSource={mismatches.map(([field, d]) => ({
                                      key: field,
                                      field,
                                      sourceField: d.source_field || field,
                                      targetField: d.target_field || field,
                                      sourceValue: d.source,
                                      targetValue: d.target,
                                      diffType: d.diff_type,
                                    }))}
                                    size="small"
                                    pagination={false}
                                    columns={[
                                      {
                                        title: "Status",
                                        dataIndex: "diffType",
                                        key: "status",
                                        width: 120,
                                        render: (v: string) => {
                                          const cfg: Record<string, { label: string; color: string }> = {
                                            value_mismatch: { label: "Mismatch", color: "orange" },
                                            missing_attribute: { label: "Missing in Target", color: "red" },
                                            extra_in_target: { label: "Extra in Target", color: "purple" },
                                          };
                                          const c = cfg[v] || { label: v, color: "default" };
                                          return <Tag color={c.color}>{c.label}</Tag>;
                                        },
                                      },
                                      {
                                        title: "Source Field",
                                        dataIndex: "sourceField",
                                        key: "srcField",
                                      },
                                      {
                                        title: "Source Value",
                                        dataIndex: "sourceValue",
                                        key: "srcVal",
                                        render: (v: unknown) => (
                                          <Text style={{ color: "#cf1322" }}>
                                            {v === null || v === undefined ? <i>null</i> : String(v)}
                                          </Text>
                                        ),
                                      },
                                      {
                                        title: "Target Field",
                                        dataIndex: "targetField",
                                        key: "tgtField",
                                      },
                                      {
                                        title: "Target Value",
                                        dataIndex: "targetValue",
                                        key: "tgtVal",
                                        render: (v: unknown) => (
                                          <Text style={{ color: "#cf1322" }}>
                                            {v === null || v === undefined ? <i>null</i> : String(v)}
                                          </Text>
                                        ),
                                      },
                                    ]}
                                  />
                                </>
                              )}
                              {matches.length > 0 && (
                                <>
                                  <Text strong style={{ color: "#389e0d", display: "block", marginTop: mismatches.length > 0 ? 16 : 0, marginBottom: 8 }}>
                                    Matching Attributes ({matches.length})
                                  </Text>
                                  <Table
                                    dataSource={matches.map(([field, d]) => ({
                                      key: field,
                                      sourceField: d.source_field || field,
                                      targetField: d.target_field || field,
                                      sourceValue: d.source,
                                      targetValue: d.target,
                                    }))}
                                    size="small"
                                    pagination={matches.length > 10 ? { pageSize: 10 } : false}
                                    columns={[
                                      {
                                        title: "Source Field",
                                        dataIndex: "sourceField",
                                        key: "srcField",
                                      },
                                      {
                                        title: "Source Value",
                                        dataIndex: "sourceValue",
                                        key: "srcVal",
                                        render: (v: unknown) => (
                                          <Text type="success">
                                            {v === null || v === undefined ? <i>null</i> : String(v)}
                                          </Text>
                                        ),
                                      },
                                      {
                                        title: "Target Field",
                                        dataIndex: "targetField",
                                        key: "tgtField",
                                      },
                                      {
                                        title: "Target Value",
                                        dataIndex: "targetValue",
                                        key: "tgtVal",
                                        render: (v: unknown) => (
                                          <Text type="success">
                                            {v === null || v === undefined ? <i>null</i> : String(v)}
                                          </Text>
                                        ),
                                      },
                                    ]}
                                  />
                                </>
                              )}
                            </div>
                          );
                        },
                        rowExpandable: (record: ValidationDetail) =>
                          record.status !== "missing_in_target",
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
                            };
                            return <Tag color={colors[v] || "default"}>{v.replace(/_/g, " ")}</Tag>;
                          },
                        },
                        {
                          title: "Summary",
                          key: "summary",
                          render: (_: unknown, r: ValidationDetail) => {
                            if (r.status === "missing_in_target") {
                              return <Text type="danger">Record not found in target</Text>;
                            }
                            if (!r.field_diffs) return "-";
                            const entries = Object.values(r.field_diffs) as any[];
                            const matchCount = entries.filter((e) => e.diff_type === "match").length;
                            const mismatchCount = entries.filter((e) => e.diff_type === "value_mismatch").length;
                            const missingCount = entries.filter((e) => e.diff_type === "missing_attribute").length;
                            return (
                              <Space>
                                {matchCount > 0 && <Tag color="green">{matchCount} matched</Tag>}
                                {mismatchCount > 0 && <Tag color="orange">{mismatchCount} mismatched</Tag>}
                                {missingCount > 0 && <Tag color="red">{missingCount} missing</Tag>}
                              </Space>
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
          {
            key: "cleanup",
            label: "Target Cleanup",
            children: (
              <div>
                <Card
                  title="Target Data Cleanup"
                  extra={
                    <Space>
                      <Button onClick={loadCleanupJobs} icon={<SyncOutlined />}>
                        Refresh
                      </Button>
                      <Button
                        type="primary"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => setCleanupModalOpen(true)}
                      >
                        New Cleanup Job
                      </Button>
                    </Space>
                  }
                >
                  <div style={{ marginBottom: 16, padding: 12, background: "#fff7e6", border: "1px solid #ffd591", borderRadius: 6 }}>
                    <Text type="warning" strong>Warning: </Text>
                    <Text type="secondary">
                      Cleanup permanently deletes migrated transactional data from the target Veeva Vault CRM.
                      Records are deleted in dependency order (children first, then parents).
                      Master data (accounts, users, territories, products) is never deleted.
                    </Text>
                  </div>
                  <Table
                    dataSource={cleanupJobs}
                    rowKey="id"
                    size="small"
                    columns={[
                      {
                        title: "Status",
                        dataIndex: "status",
                        key: "status",
                        width: 120,
                        render: (v: string) => {
                          const colors: Record<string, string> = {
                            running: "processing",
                            completed: "success",
                            failed: "error",
                            cancelled: "default",
                          };
                          return <Tag color={colors[v] || "default"}>{v}</Tag>;
                        },
                      },
                      {
                        title: "Progress",
                        key: "progress",
                        width: 300,
                        render: (_: unknown, j: any) => {
                          if (j.status === "completed") return <Tag color="green">Done — {j.records_deleted.toLocaleString()} deleted</Tag>;
                          if (j.status === "failed") return <Tag color="red">Failed</Tag>;
                          if (j.status === "cancelled") return <Tag color="default">Cancelled — {j.records_deleted.toLocaleString()} deleted</Tag>;
                          if (!["running", "pending"].includes(j.status)) return "-";

                          const pct = j.total_steps > 0 ? Math.round((j.completed_steps / j.total_steps) * 100) : 0;
                          return (
                            <div style={{ minWidth: 240 }}>
                              <Progress
                                percent={pct}
                                size="small"
                                status="active"
                                format={() => `${j.completed_steps}/${j.total_steps} objects`}
                              />
                              {j.current_object && (
                                <div style={{ fontSize: 11, color: "#888", marginTop: 2 }}>
                                  <LoadingOutlined style={{ marginRight: 4 }} />
                                  {j.current_object}
                                  {j.current_phase === "querying" && " — finding records..."}
                                  {j.current_phase === "deleting" && " — deleting..."}
                                </div>
                              )}
                              <div style={{ fontSize: 11, color: "#888", marginTop: 2 }}>
                                Found: {j.records_found.toLocaleString()} | Deleted: {j.records_deleted.toLocaleString()}
                              </div>
                            </div>
                          );
                        },
                      },
                      {
                        title: "Filter",
                        key: "filter",
                        render: (_: unknown, j: any) => (
                          <Space direction="vertical" size={0}>
                            <Tag color={j.filter_mode === "country" ? "purple" : "blue"}>
                              {j.filter_mode === "country"
                                ? `Country: ${j.country_code}`
                                : "legacy_crm_id ≠ null"}
                            </Tag>
                          </Space>
                        ),
                      },
                      {
                        title: "Created",
                        dataIndex: "created_at",
                        key: "created_at",
                        render: (v: string) => new Date(v).toLocaleString(),
                      },
                      {
                        title: "Actions",
                        key: "actions",
                        render: (_: unknown, j: any) => (
                          <Space>
                            {j.status === "running" && (
                              <Popconfirm
                                title="Cancel this cleanup job?"
                                onConfirm={() => handleCancelCleanup(j.id)}
                              >
                                <Button size="small" danger>Cancel</Button>
                              </Popconfirm>
                            )}
                            {j.step_results && Object.keys(j.step_results).length > 0 && (
                              <Tooltip title="View per-object results">
                                <Button
                                  size="small"
                                  onClick={() => Modal.info({
                                    title: "Cleanup Results by Object",
                                    width: 700,
                                    content: (
                                      <Table
                                        dataSource={Object.entries(j.step_results).map(([obj, r]: [string, any]) => ({
                                          key: obj,
                                          object: obj,
                                          ...r,
                                        }))}
                                        size="small"
                                        pagination={false}
                                        columns={[
                                          { title: "Object", dataIndex: "object", key: "obj" },
                                          { title: "Step", dataIndex: "step", key: "step", width: 60 },
                                          { title: "Found", dataIndex: "found", key: "found", render: (v: number) => v.toLocaleString() },
                                          { title: "Deleted", dataIndex: "deleted", key: "del", render: (v: number) => v.toLocaleString() },
                                          { title: "Failed", dataIndex: "failed", key: "fail", render: (v: number) => v > 0 ? <Text type="danger">{v}</Text> : "0" },
                                          {
                                            title: "Status",
                                            key: "status",
                                            render: (_: unknown, r: any) => {
                                              if (r.skipped) return <Tag color="orange">Skipped</Tag>;
                                              if (r.failed > 0) return <Tag color="red">Partial</Tag>;
                                              if (r.found === 0) return <Tag>No records</Tag>;
                                              return <Tag color="green">OK</Tag>;
                                            },
                                          },
                                        ]}
                                      />
                                    ),
                                  })}
                                >
                                  Details
                                </Button>
                              </Tooltip>
                            )}
                          </Space>
                        ),
                      },
                    ]}
                  />
                </Card>
              </div>
            ),
          },
        ]}
        onChange={(key) => {
          if (key === "cleanup") loadCleanupJobs();
        }}
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
              String(option?.label || "")
                ?.toLowerCase()
                .includes(input.toLowerCase()) ?? false
            }
          >
            {sourceObjects.map((o) => (
              <Select.Option key={o.name} value={o.name} label={`${o.label} (${o.name})`}>
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
              String(option?.label || "")
                ?.toLowerCase()
                .includes(input.toLowerCase()) ?? false
            }
          >
            {targetObjects.map((o) => (
              <Select.Option key={o.name} value={o.name} label={`${o.label} (${o.name})`}>
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

      {/* New Validation Run Modal */}
      <Modal
        title="New Validation Run"
        open={runValidationOpen}
        onCancel={() => setRunValidationOpen(false)}
        onOk={handleRunValidation}
        okText="Start Validation"
        width={600}
      >
        <div style={{ marginBottom: 16 }}>
          <Text strong>Mode</Text>
          <Select
            style={{ width: "100%", marginTop: 4 }}
            value={runValidationMode}
            onChange={setRunValidationMode}
          >
            <Select.Option value="auto" label="Auto">
              Auto — small objects run inline, large objects run as batch
            </Select.Option>
            <Select.Option value="realtime" label="Real-time">
              Real-time — run all inline (may be slow for large objects)
            </Select.Option>
            <Select.Option value="batch" label="Batch">
              Batch — queue all as background jobs
            </Select.Option>
          </Select>
        </div>
        <div style={{ marginBottom: 16 }}>
          <Text strong>Objects to Validate</Text>
          <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
            Select specific object mappings, or leave empty to validate all.
          </Text>
          <Select
            mode="multiple"
            style={{ width: "100%" }}
            placeholder="All object mappings"
            value={selectedObjectMappingIds}
            onChange={setSelectedObjectMappingIds}
            allowClear
          >
            {objectMappings.map((om) => (
              <Select.Option key={om.id} value={om.id} label={`${om.source_object} → ${om.target_object}`}>
                {om.source_object} → {om.target_object}
              </Select.Option>
            ))}
          </Select>
        </div>
        <div style={{ marginBottom: 16 }}>
          <Text strong>Source WHERE Clause</Text>
          <Tag color="geekblue" style={{ marginLeft: 8 }}>SOQL</Tag>
          <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
            Custom SOQL WHERE condition for source query. Do not include the WHERE keyword.
          </Text>
          <Input.TextArea
            rows={2}
            placeholder="e.g. CreatedDate >= 2024-01-01T00:00:00Z AND OCE__Status__c = 'Submitted'"
            value={sourceWhereClause}
            onChange={(e) => setSourceWhereClause(e.target.value)}
            style={{ fontFamily: "monospace", fontSize: 12 }}
          />
        </div>
        <div style={{ marginBottom: 16 }}>
          <Text strong>Date Range</Text>
          <Tag color="purple" style={{ marginLeft: 8 }}>By CreatedDate</Tag>
          <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
            Only validate records created within the last N months. Leave empty to validate all time.
          </Text>
          <InputNumber
            style={{ width: "100%" }}
            placeholder="All time (no date filter)"
            min={1}
            max={120}
            value={dateRangeMonths}
            onChange={(v) => setDateRangeMonths(v)}
            addonAfter="months"
          />
          <div style={{ marginTop: 8 }}>
            <Space>
              <Button size="small" onClick={() => setDateRangeMonths(3)}>3M</Button>
              <Button size="small" onClick={() => setDateRangeMonths(6)}>6M</Button>
              <Button size="small" onClick={() => setDateRangeMonths(12)}>1Y</Button>
              <Button size="small" onClick={() => setDateRangeMonths(24)}>2Y</Button>
              <Button size="small" onClick={() => setDateRangeMonths(36)}>3Y</Button>
              <Button size="small" onClick={() => setDateRangeMonths(null)}>All</Button>
            </Space>
          </div>
        </div>
        <div>
          <Text strong>Record Limit</Text>
          <Tag color="blue" style={{ marginLeft: 8 }}>Sampling</Tag>
          <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
            Limit records per object for a quick sample validation. Leave empty to validate all records.
          </Text>
          <InputNumber
            style={{ width: "100%" }}
            placeholder="All records (no limit)"
            min={100}
            step={1000}
            value={recordLimit}
            onChange={(v) => setRecordLimit(v)}
            formatter={(v) => v ? `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ",") : ""}
          />
          <div style={{ marginTop: 8 }}>
            <Space>
              <Button size="small" onClick={() => setRecordLimit(1000)}>1K</Button>
              <Button size="small" onClick={() => setRecordLimit(5000)}>5K</Button>
              <Button size="small" onClick={() => setRecordLimit(10000)}>10K</Button>
              <Button size="small" onClick={() => setRecordLimit(50000)}>50K</Button>
              <Button size="small" onClick={() => setRecordLimit(null)}>All</Button>
            </Space>
          </div>
        </div>
      </Modal>

      {/* Add Match Key Modal */}
      <Modal
        title="Add Match Key"
        open={addMatchKeyOpen}
        onCancel={() => setAddMatchKeyOpen(false)}
        onOk={handleAddMatchKey}
        okText="Add"
      >
        <Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
          Match keys define how records are matched between source and target
          systems. For example, map an External ID field from Salesforce to the
          corresponding field in Veeva Vault.
        </Text>
        <div style={{ marginBottom: 16 }}>
          <Text strong>Source Field (Salesforce)</Text>
          <Select
            showSearch
            style={{ width: "100%", marginTop: 4 }}
            value={newMatchKeySource || undefined}
            onChange={setNewMatchKeySource}
            placeholder="Select source match key field"
            filterOption={(input, option) =>
              String(option?.label || "")
                ?.toLowerCase()
                .includes(input.toLowerCase()) ?? false
            }
          >
            {sourceFields.map((f) => (
              <Select.Option key={f.name} value={f.name} label={`${f.label} (${f.name})`}>
                {f.label} ({f.name})
              </Select.Option>
            ))}
          </Select>
        </div>
        <div>
          <Text strong>Target Field (Veeva Vault)</Text>
          <Select
            showSearch
            style={{ width: "100%", marginTop: 4 }}
            value={newMatchKeyTarget || undefined}
            onChange={setNewMatchKeyTarget}
            placeholder="Select target match key field"
            filterOption={(input, option) =>
              String(option?.label || "")
                ?.toLowerCase()
                .includes(input.toLowerCase()) ?? false
            }
          >
            {targetFields.map((f) => (
              <Select.Option key={f.name} value={f.name} label={`${f.label} (${f.name})`}>
                {f.label} ({f.name})
              </Select.Option>
            ))}
          </Select>
        </div>
      </Modal>

      {/* Cleanup Job Modal */}
      <Modal
        title="New Target Cleanup Job"
        open={cleanupModalOpen}
        onCancel={() => setCleanupModalOpen(false)}
        onOk={handleStartCleanup}
        okText="Start Cleanup"
        okButtonProps={{ danger: true }}
      >
        <div style={{ marginBottom: 16, padding: 12, background: "#fff1f0", border: "1px solid #ffa39e", borderRadius: 6 }}>
          <Text type="danger" strong>This will permanently delete records from Veeva Vault CRM. This action cannot be undone.</Text>
        </div>
        <div style={{ marginBottom: 16 }}>
          <Text strong>Filter Mode</Text>
          <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
            Choose how to identify records to delete.
          </Text>
          <Select
            style={{ width: "100%" }}
            value={cleanupFilterMode}
            onChange={setCleanupFilterMode}
          >
            <Select.Option value="legacy_crm_id">
              Legacy CRM ID (legacy_crm_id__v ≠ null)
            </Select.Option>
            <Select.Option value="country">
              By Account Country (country_code__v)
            </Select.Option>
          </Select>
        </div>
        {cleanupFilterMode === "country" && (
          <div style={{ marginBottom: 16 }}>
            <Text strong>Country Code</Text>
            <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
              Enter the country code (e.g., CH, DE, US). All transactional data related to accounts in this country will be deleted.
            </Text>
            <Input
              placeholder="e.g. CH"
              value={cleanupCountryCode}
              onChange={(e) => setCleanupCountryCode(e.target.value.toUpperCase())}
              style={{ width: 200 }}
            />
          </div>
        )}
        <div>
          <Text strong>Deletion Order</Text>
          <Text type="secondary" style={{ display: "block", marginBottom: 8 }}>
            Records are deleted in reverse dependency order: children first, then parents.
            Master data (accounts, users, territories, products) is never deleted.
          </Text>
        </div>
      </Modal>
    </div>
  );
}
