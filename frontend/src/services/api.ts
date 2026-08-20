import axios from "axios";
import type {
  AuthResponse,
  ChecklistReviewResult,
  Connection,
  ConnType,
  GithubCommitResult,
  JiraCommentResult,
  Plan,
  PlanningContext,
  PlanSummary,
} from "../types";

const api = axios.create({ baseURL: "/api" });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// On an expired/invalid token, clear the session and send the user to login.
// Only react to auth failures on authenticated calls (not the login attempt
// itself, which legitimately returns 401 on wrong credentials).
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const url: string = error?.config?.url || "";
    const isAuthAttempt = url.includes("/auth/login") || url.includes("/auth/register");
    if (status === 401 && !isAuthAttempt) {
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      if (window.location.pathname !== "/login") {
        window.location.assign("/login");
      }
    }
    return Promise.reject(error);
  },
);

export const authApi = {
  async register(email: string, password: string, fullName?: string) {
    const { data } = await api.post<AuthResponse>("/auth/register", {
      email,
      password,
      full_name: fullName,
    });
    return data;
  },
  async login(email: string, password: string) {
    const form = new URLSearchParams();
    form.set("username", email);
    form.set("password", password);
    const { data } = await api.post<AuthResponse>("/auth/login", form, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    return data;
  },
};

export const connectionsApi = {
  async list() {
    const { data } = await api.get<Connection[]>("/connections");
    return data;
  },
  async create(payload: {
    name: string;
    conn_type: ConnType;
    config: Record<string, unknown>;
    secrets: Record<string, unknown>;
  }) {
    const { data } = await api.post<Connection>("/connections", payload);
    return data;
  },
  async update(
    id: number,
    payload: {
      name?: string;
      config?: Record<string, unknown>;
      secrets?: Record<string, unknown>;
    },
  ) {
    const { data } = await api.patch<Connection>(`/connections/${id}`, payload);
    return data;
  },
  async remove(id: number) {
    await api.delete(`/connections/${id}`);
  },
  async test(id: number) {
    const { data } = await api.post<{ ok: boolean; detail: string; info: Record<string, unknown> }>(
      `/connections/${id}/test`,
    );
    return data;
  },
};

export const planningApi = {
  async gatherContext(payload: {
    jira_connection_id?: number;
    github_connection_id?: number;
    salesforce_connection_id?: number;
    jira_ticket_id?: string;
    github_repo?: string;
    github_branch?: string;
    sfdx_path?: string;
  }) {
    const { data } = await api.post<PlanningContext>("/planning/context", payload);
    return data;
  },
  async generate(context: PlanningContext) {
    const { data } = await api.post<Plan>("/planning/generate", { context });
    return data;
  },
  async generateWithImages(context: PlanningContext, files: File[]) {
    const form = new FormData();
    form.set("context", JSON.stringify(context));
    files.forEach((f) => form.append("files", f));
    const { data } = await api.post<Plan>(
      "/planning/generate-with-images",
      form,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return data;
  },
  async listPlans() {
    const { data } = await api.get<PlanSummary[]>("/planning/plans");
    return data;
  },
  async getPlan(id: number) {
    const { data } = await api.get<Plan>(`/planning/plans/${id}`);
    return data;
  },
  async refine(id: number, feedback: string) {
    const { data } = await api.post<Plan>(`/planning/plans/${id}/refine`, {
      feedback,
    });
    return data;
  },
  async approve(id: number) {
    const { data } = await api.post<Plan>(`/planning/plans/${id}/approve`);
    return data;
  },
  async deploy(
    id: number,
    salesforceConnectionId: number,
    checkOnly = false,
    selection?: { step_numbers?: number[]; artifact_paths?: string[] },
  ) {
    const { data } = await api.post<Plan>(`/planning/plans/${id}/deploy`, {
      salesforce_connection_id: salesforceConnectionId,
      check_only: checkOnly,
      ...(selection?.step_numbers !== undefined
        ? { step_numbers: selection.step_numbers }
        : {}),
      ...(selection?.artifact_paths !== undefined
        ? { artifact_paths: selection.artifact_paths }
        : {}),
    });
    return data;
  },
  async commitToGithub(
    id: number,
    payload: {
      github_connection_id: number;
      repo?: string;
      branch?: string;
      base_branch?: string;
      metadata_format?: string;
      commit_message?: string;
    },
  ) {
    const { data } = await api.post<GithubCommitResult>(
      `/planning/plans/${id}/commit-github`,
      payload,
    );
    return data;
  },
  async postTestPlanToJira(
    id: number,
    jiraConnectionId: number,
    ticketId?: string,
  ) {
    const { data } = await api.post<JiraCommentResult>(
      `/planning/plans/${id}/post-test-plan-jira`,
      {
        jira_connection_id: jiraConnectionId,
        ...(ticketId ? { ticket_id: ticketId } : {}),
      },
    );
    return data;
  },
  async reviewChecklist(id: number, checklistConnectionId: number) {
    const { data } = await api.post<ChecklistReviewResult>(
      `/planning/plans/${id}/review-checklist`,
      { checklist_connection_id: checklistConnectionId },
    );
    return data;
  },
};

export default api;
