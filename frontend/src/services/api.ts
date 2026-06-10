import axios from "axios";

const api = axios.create({
  baseURL: "/api",
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default api;

// Auth
export const login = (username: string, password: string) =>
  api.post("/auth/login", { username, password });

export const register = (data: {
  username: string;
  email: string;
  password: string;
  full_name?: string;
}) => api.post("/auth/register", data);

// Connections
export const getConnections = () => api.get("/connections");
export const createConnection = (data: Record<string, unknown>) =>
  api.post("/connections", data);
export const updateConnection = (id: string, data: Record<string, unknown>) =>
  api.put(`/connections/${id}`, data);
export const deleteConnection = (id: string) =>
  api.delete(`/connections/${id}`);
export const testConnection = (id: string) =>
  api.post(`/connections/${id}/test`);

// Projects
export const getProjects = () => api.get("/projects");
export const createProject = (data: Record<string, unknown>) =>
  api.post("/projects", data);
export const getProject = (id: string) => api.get(`/projects/${id}`);
export const deleteProject = (id: string) => api.delete(`/projects/${id}`);

// Schema
export const getSourceObjects = (projectId: string) =>
  api.get(`/projects/${projectId}/schema/source`);
export const getTargetObjects = (projectId: string) =>
  api.get(`/projects/${projectId}/schema/target`);
export const describeSourceObject = (projectId: string, objectName: string) =>
  api.get(`/projects/${projectId}/schema/source/${objectName}`);
export const describeTargetObject = (projectId: string, objectName: string) =>
  api.get(`/projects/${projectId}/schema/target/${objectName}`);

// Object Mappings
export const getObjectMappings = (projectId: string) =>
  api.get(`/projects/${projectId}/object-mappings`);
export const createObjectMapping = (
  projectId: string,
  data: { source_object: string; target_object: string }
) => api.post(`/projects/${projectId}/object-mappings`, data);
export const deleteObjectMapping = (projectId: string, mappingId: string) =>
  api.delete(`/projects/${projectId}/object-mappings/${mappingId}`);

// Auto-mapping
export const autoMapFields = (projectId: string, mappingId: string) =>
  api.post(`/projects/${projectId}/object-mappings/${mappingId}/auto-map`);
export const applySuggestions = (
  projectId: string,
  mappingId: string,
  suggestions: unknown[]
) =>
  api.post(
    `/projects/${projectId}/object-mappings/${mappingId}/apply-suggestions`,
    suggestions
  );

// Field Mappings
export const getFieldMappings = (projectId: string, mappingId: string) =>
  api.get(`/projects/${projectId}/object-mappings/${mappingId}/field-mappings`);
export const createFieldMapping = (
  projectId: string,
  mappingId: string,
  data: Record<string, unknown>
) =>
  api.post(
    `/projects/${projectId}/object-mappings/${mappingId}/field-mappings`,
    data
  );
export const deleteFieldMapping = (
  projectId: string,
  mappingId: string,
  fieldMappingId: string
) =>
  api.delete(
    `/projects/${projectId}/object-mappings/${mappingId}/field-mappings/${fieldMappingId}`
  );

// Match Keys
export const getMatchKeys = (projectId: string, mappingId: string) =>
  api.get(`/projects/${projectId}/object-mappings/${mappingId}/match-keys`);
export const createMatchKey = (
  projectId: string,
  mappingId: string,
  data: Record<string, unknown>
) =>
  api.post(
    `/projects/${projectId}/object-mappings/${mappingId}/match-keys`,
    data
  );
export const deleteMatchKey = (
  projectId: string,
  mappingId: string,
  keyId: string
) =>
  api.delete(
    `/projects/${projectId}/object-mappings/${mappingId}/match-keys/${keyId}`
  );

// Export/Import
export const exportMappings = (
  projectId: string,
  mappingId: string,
  format: string = "csv"
) =>
  api.get(
    `/projects/${projectId}/object-mappings/${mappingId}/export?format=${format}`,
    { responseType: "blob" }
  );
export const importMappings = (
  projectId: string,
  mappingId: string,
  file: File
) => {
  const formData = new FormData();
  formData.append("file", file);
  return api.post(
    `/projects/${projectId}/object-mappings/${mappingId}/import`,
    formData
  );
};

// Validation
export const createValidationRun = (data: {
  project_id: string;
  object_mapping_ids?: string[];
  mode?: string;
}) => api.post("/validation/runs", data);
export const getValidationRuns = (projectId?: string) =>
  api.get("/validation/runs", { params: { project_id: projectId } });
export const getValidationRun = (runId: string) =>
  api.get(`/validation/runs/${runId}`);
export const getValidationSummaries = (runId: string) =>
  api.get(`/validation/runs/${runId}/summaries`);
export const getValidationDetails = (
  summaryId: string,
  page: number = 1,
  pageSize: number = 50,
  statusFilter?: string
) =>
  api.get(`/validation/summaries/${summaryId}/details`, {
    params: { page, page_size: pageSize, status_filter: statusFilter },
  });

// Export reports
export const exportSummaryReport = (runId: string, format: string = "csv") =>
  api.get(`/validation/runs/${runId}/export/summary?format=${format}`, {
    responseType: "blob",
  });
export const exportDetailReport = (
  summaryId: string,
  format: string = "csv",
  statusFilter?: string
) =>
  api.get(`/validation/summaries/${summaryId}/export/details`, {
    params: { format, status_filter: statusFilter },
    responseType: "blob",
  });
