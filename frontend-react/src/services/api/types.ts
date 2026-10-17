/**
 * Friendly names for the generated API types (schema.d.ts, from `npm run gen:api`).
 *
 * Pydantic marks fields that have defaults as optional in OpenAPI, but responses always include
 * every field. `Out<T>` makes response types say so; request types keep their optional fields.
 */
import type { components } from "./schema";

type Schemas = components["schemas"];

export type DeepRequired<T> = T extends (infer U)[]
  ? DeepRequired<U>[]
  : T extends object
    ? { [K in keyof T]-?: DeepRequired<T[K]> }
    : T;

type Out<K extends keyof Schemas> = DeepRequired<Schemas[K]>;
type In<K extends keyof Schemas> = Schemas[K];

// ---- stored data (responses) ----
export type MasterProfile = Out<"MasterProfile">;
export type Contact = Out<"Contact">;
export type Experience = Out<"Experience">;
export type Project = Out<"Project">;
export type Bullet = Out<"Bullet">;
export type Skill = Out<"Skill">;
export type Education = Out<"Education">;
export type Certification = Out<"Certification">;
export type Achievement = Out<"Achievement">;
export type VerifiedMetric = Out<"VerifiedMetric">;
export type RoleProfile = Out<"RoleProfile">;
export type Job = Out<"Job">;
export type Capture = Out<"Capture">;
export type JDAnalysis = Out<"JDAnalysis">;
export type Requirement = Out<"Requirement">;
export type ResumeVersion = Out<"ResumeVersion">;
export type ResumeContent = Out<"ResumeContent">;
export type ResumeEntry = Out<"ResumeEntry">;
export type ExportRecord = Out<"ExportRecord">;

// ---- enums ----
export type SkillCategory = Schemas["SkillCategory"];
export type JobStatus = Schemas["JobStatus"];
export type SourcePlatform = Schemas["SourcePlatform"];
export type ImportMethod = Schemas["ImportMethod"];
export type MatchStatus = Schemas["MatchStatus"];
export type RequirementCategory = Schemas["RequirementCategory"];
export type Importance = Schemas["Importance"];
export type WorkArrangement = Schemas["WorkArrangement"];
export type TextOrigin = Schemas["TextOrigin"];
export type TargetLength = Schemas["TargetLength"];
export type CheckStatus = Schemas["CheckStatus"];

// ---- views (responses) ----
export type Health = Out<"Health">;
export type SettingsView = Out<"SettingsView">;
export type SettingsValues = Out<"SettingsValues">;
export type ProviderStatus = Out<"ProviderStatusView">;
export type ProfileView = Out<"ProfileView">;
export type EvidenceItem = Out<"EvidenceItem">;
export type ProfileWarning = Out<"ProfileWarningView">;
export type ProfileSaveOut = Out<"ProfileSaveOut">;
export type ProfileVersionInfo = Out<"ProfileVersionInfo">;
export type ProfileImportPreview = Out<"ProfileImportPreview">;
export type RoleProfileView = Out<"RoleProfileView">;
export type JobDraft = Out<"JobDraft">;
export type JobSummary = Out<"JobSummary">;
export type JobCreateOut = Out<"JobCreateOut">;
/** Sent in the `details.duplicates` of a 409 `duplicate` error from POST /jobs (not a named schema). */
export interface DuplicateView {
  job: Job;
  reason: string;
}
export type AnalysisView = Out<"AnalysisView">;
export type AnalyzeOut = Out<"AnalyzeOut">;
export type MatchView = Out<"MatchView">;
export type MatchRow = Out<"MatchRow">;
export type MatchRunOut = Out<"MatchRunOut">;
export type GroupStats = Out<"GroupStatsView">;
export type Recommendation = Out<"RecommendationView">;
export type TailoringOptions = Out<"TailoringOptions">;
export type AiPreview = Out<"AiPreview">;
export type GenerateOut = Out<"GenerateOut">;
export type VersionSummary = Out<"VersionSummary">;
export type VersionListItem = Out<"VersionListItem">;
export type VersionDetail = Out<"VersionDetail">;
export type ValidationView = Out<"ValidationView">;
export type ChangeRow = Out<"ChangeRowView">;
export type ExportView = Out<"ExportView">;
export type EditOut = Out<"EditOut">;
export type TrackerView = Out<"TrackerView">;
export type TrackerRow = Out<"TrackerRowView">;
export type ApplicationOut = Out<"ApplicationOut">;
export type DuplicatePair = Out<"DuplicatePairView">;
export type Dashboard = Out<"Dashboard">;
export type DashboardJob = Out<"DashboardJob">;

// ---- request bodies ----
export type SettingsPatch = In<"SettingsPatch">;
export type RoleProfileIn = In<"RoleProfileIn">;
export type JobCreateIn = In<"JobCreateIn">;
export type JobPatchIn = In<"JobPatchIn">;
export type AnalysisReviewIn = In<"AnalysisReviewIn">;
export type RequirementRow = In<"RequirementRow">;
export type OverrideIn = In<"OverrideIn">;
export type GenerateIn = In<"GenerateIn">;
export type EditIn = In<"EditIn">;
export type BulletEdit = In<"BulletEdit">;
export type ApproveIn = In<"ApproveIn">;
export type ApplicationIn = In<"ApplicationIn">;
export type MergeIn = In<"MergeIn">;

export const SKILL_CATEGORIES: SkillCategory[] = ["language", "framework", "tool", "platform", "concept", "soft", "other"];
export const JOB_STATUSES: JobStatus[] = ["saved", "applied", "interviewing", "offer", "rejected", "withdrawn", "archived"];
export const SOURCE_PLATFORMS: SourcePlatform[] = ["linkedin", "naukri", "other"];
export const REQUIREMENT_CATEGORIES: RequirementCategory[] = [
  "skill",
  "experience",
  "education",
  "certification",
  "responsibility",
  "qualification",
  "domain",
];
export const IMPORTANCES: Importance[] = ["required", "preferred", "unspecified"];
export const WORK_ARRANGEMENTS: WorkArrangement[] = ["onsite", "hybrid", "remote", "unspecified"];
export const MATCH_STATUSES: MatchStatus[] = ["supported", "partial", "not_documented"];
