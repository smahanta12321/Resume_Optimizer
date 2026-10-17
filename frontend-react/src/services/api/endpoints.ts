/** Typed functions for every local API route. Paths and shapes come from the backend's OpenAPI schema. */
import { download, request } from "./client";
import type * as T from "./types";

const enc = encodeURIComponent;

export const api = {
  health: (signal?: AbortSignal) => request<T.Health>("/health", { signal }),
  session: (signal?: AbortSignal) => request<{ ok: boolean }>("/session", { signal }),

  settings: {
    get: (signal?: AbortSignal) => request<T.SettingsView>("/settings", { signal }),
    patch: (body: T.SettingsPatch) => request<T.SettingsView>("/settings", { method: "PATCH", json: body }),
  },

  dashboard: (signal?: AbortSignal) => request<T.Dashboard>("/dashboard", { signal }),

  profile: {
    get: (signal?: AbortSignal) => request<T.ProfileView>("/profile", { signal }),
    save: (profile: T.MasterProfile | Record<string, unknown>, expectedVersion: number | null) =>
      request<T.ProfileSaveOut>("/profile", { method: "PUT", json: { profile, expected_version: expectedVersion } }),
    confirm: (expectedVersion: number) =>
      request<T.ProfileView>("/profile/confirm", { method: "POST", json: { expected_version: expectedVersion } }),
    loadSample: () => request<T.ProfileSaveOut>("/profile/sample", { method: "POST" }),
    versions: (signal?: AbortSignal) => request<T.ProfileVersionInfo[]>("/profile/versions", { signal }),
    version: (n: number, signal?: AbortSignal) => request<T.MasterProfile>(`/profile/versions/${n}`, { signal }),
    restore: (n: number, expectedVersion: number | null) =>
      request<T.ProfileSaveOut>(`/profile/versions/${n}/restore`, {
        method: "POST",
        json: { expected_version: expectedVersion },
      }),
    previewImport: (file: Blob) =>
      request<T.ProfileImportPreview>("/profile/import/preview", { method: "POST", raw: file, contentType: "application/json" }),
    exportJson: () => download("/profile/export", "master_profile.json"),
    deleteAll: () => request<void>("/profile", { method: "DELETE", json: { confirm: "DELETE" } }),
  },

  roles: {
    list: (signal?: AbortSignal) => request<T.RoleProfileView[]>("/role-profiles", { signal }),
    create: (body: T.RoleProfileIn) => request<T.RoleProfileView>("/role-profiles", { method: "POST", json: body }),
    update: (id: string, body: T.RoleProfileIn) =>
      request<T.RoleProfileView>(`/role-profiles/${enc(id)}`, { method: "PUT", json: body }),
    duplicate: (id: string, name: string) =>
      request<T.RoleProfileView>(`/role-profiles/${enc(id)}/duplicate`, { method: "POST", json: { name } }),
    remove: (id: string) => request<void>(`/role-profiles/${enc(id)}`, { method: "DELETE" }),
  },

  jobs: {
    list: (signal?: AbortSignal) => request<T.JobSummary[]>("/jobs", { signal }),
    get: (id: string, signal?: AbortSignal) => request<T.JobSummary>(`/jobs/${enc(id)}`, { signal }),
    create: (body: T.JobCreateIn) => request<T.JobCreateOut>("/jobs", { method: "POST", json: body }),
    patch: (id: string, body: T.JobPatchIn) => request<T.Job>(`/jobs/${enc(id)}`, { method: "PATCH", json: body }),
    remove: (id: string) => request<void>(`/jobs/${enc(id)}`, { method: "DELETE" }),
    draftFromText: (text: string) => request<T.JobDraft>("/jobs/drafts/text", { method: "POST", json: { text } }),
    draftFromFile: (file: File) =>
      request<T.JobDraft>("/jobs/drafts/file", { method: "POST", raw: file, query: { filename: file.name } }),
    draftFromUrl: (url: string, signal?: AbortSignal) =>
      request<T.JobDraft>("/jobs/drafts/url", { method: "POST", json: { url }, signal }),
    draftFromCapture: (id: string) => request<T.JobDraft>(`/jobs/drafts/capture/${enc(id)}`, { method: "POST" }),
    captures: (signal?: AbortSignal) => request<T.Capture[]>("/captures", { signal }),
    discardCapture: (id: string) => request<void>(`/captures/${enc(id)}`, { method: "DELETE" }),
  },

  analysis: {
    get: (jobId: string, signal?: AbortSignal) => request<T.AnalysisView>(`/jobs/${enc(jobId)}/analysis`, { signal }),
    run: (jobId: string, replace = false) =>
      request<T.AnalyzeOut>(`/jobs/${enc(jobId)}/analysis`, { method: "POST", json: { replace } }),
    review: (jobId: string, body: T.AnalysisReviewIn) =>
      request<T.AnalysisView>(`/jobs/${enc(jobId)}/analysis`, { method: "PUT", json: body }),
    confirm: (jobId: string) => request<T.AnalysisView>(`/jobs/${enc(jobId)}/analysis/confirm`, { method: "POST" }),
  },

  match: {
    get: (jobId: string, signal?: AbortSignal) => request<T.MatchView>(`/jobs/${enc(jobId)}/match`, { signal }),
    run: (jobId: string) => request<T.MatchRunOut>(`/jobs/${enc(jobId)}/match`, { method: "POST" }),
    setOverride: (jobId: string, requirementId: string, body: T.OverrideIn) =>
      request<T.MatchView>(`/jobs/${enc(jobId)}/match/overrides/${enc(requirementId)}`, { method: "PUT", json: body }),
    clearOverride: (jobId: string, requirementId: string) =>
      request<T.MatchView>(`/jobs/${enc(jobId)}/match/overrides/${enc(requirementId)}`, { method: "DELETE" }),
  },

  resumes: {
    listAll: (signal?: AbortSignal) => request<T.VersionListItem[]>("/resumes", { signal }),
    forJob: (jobId: string, signal?: AbortSignal) =>
      request<T.VersionSummary[]>(`/jobs/${enc(jobId)}/resumes`, { signal }),
    tailoring: (jobId: string, signal?: AbortSignal) =>
      request<T.TailoringOptions>(`/jobs/${enc(jobId)}/tailoring`, { signal }),
    aiPreview: (jobId: string, body: T.GenerateIn) =>
      request<T.AiPreview>(`/jobs/${enc(jobId)}/resumes/ai-preview`, { method: "POST", json: body }),
    generate: (jobId: string, body: T.GenerateIn) =>
      request<T.GenerateOut>(`/jobs/${enc(jobId)}/resumes`, { method: "POST", json: body }),
    get: (id: string, signal?: AbortSignal) => request<T.VersionDetail>(`/resumes/${enc(id)}`, { signal }),
    edit: (id: string, body: T.EditIn) => request<T.EditOut>(`/resumes/${enc(id)}/edits`, { method: "POST", json: body }),
    approve: (id: string, body: T.ApproveIn) =>
      request<T.VersionDetail>(`/resumes/${enc(id)}/approve`, { method: "POST", json: body }),
    exportFiles: (id: string) => request<T.ExportView>(`/resumes/${enc(id)}/export`, { method: "POST" }),
    downloadFile: (id: string, kind: "docx" | "pdf", fallbackName: string) =>
      download(`/resumes/${enc(id)}/files/${kind}`, fallbackName),
  },

  tracker: {
    get: (filters: TrackerFilters, signal?: AbortSignal) =>
      request<T.TrackerView>("/tracker", { query: trackerQuery(filters), signal }),
    update: (jobId: string, body: T.ApplicationIn) =>
      request<T.ApplicationOut>(`/tracker/${enc(jobId)}`, { method: "PATCH", json: body }),
    exportCsv: (filters: TrackerFilters, includeJdText: boolean) =>
      download("/tracker/export.csv", "applications.csv", { ...trackerQuery(filters), include_jd_text: includeJdText }),
    duplicates: (signal?: AbortSignal) => request<T.DuplicatePair[]>("/tracker/duplicates", { signal }),
    merge: (body: T.MergeIn) => request<T.Job>("/tracker/merge", { method: "POST", json: body }),
  },
};

export interface TrackerFilters {
  status: T.JobStatus[];
  platform: T.SourcePlatform[];
  search: string;
  dueOnly: boolean;
}

function trackerQuery(f: TrackerFilters) {
  return { status: f.status, platform: f.platform, search: f.search.trim(), due_only: f.dueOnly || undefined };
}
