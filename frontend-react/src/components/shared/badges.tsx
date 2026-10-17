import type { CheckStatus, JobStatus, MatchStatus, TextOrigin } from "@/services/api/types";
import { Badge } from "@/components/ui/surface";
import { humanize } from "@/lib/format";

const MATCH: Record<MatchStatus, { tone: "success" | "warning" | "neutral"; label: string }> = {
  supported: { tone: "success", label: "Supported" },
  partial: { tone: "warning", label: "Partial" },
  not_documented: { tone: "neutral", label: "Not documented" },
};

export function MatchStatusBadge({ status, own }: { status: MatchStatus; own?: boolean }) {
  const s = MATCH[status];
  return (
    <Badge tone={s.tone}>
      {s.label}
      {own && <span className="opacity-75">· yours</span>}
    </Badge>
  );
}

const JOB_TONE: Record<JobStatus, "neutral" | "primary" | "success" | "warning" | "danger" | "outline"> = {
  saved: "neutral",
  applied: "primary",
  interviewing: "warning",
  offer: "success",
  rejected: "danger",
  withdrawn: "outline",
  archived: "outline",
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  return <Badge tone={JOB_TONE[status]}>{humanize(status)}</Badge>;
}

export function AnalysisBadge({ state }: { state: string }) {
  if (state === "confirmed") return <Badge tone="success">Analysis confirmed</Badge>;
  if (state === "draft") return <Badge tone="warning">Analysis draft</Badge>;
  return <Badge tone="outline">Not analyzed</Badge>;
}

export function VersionStateBadge({ approved, exported }: { approved: boolean; exported?: boolean }) {
  if (exported) return <Badge tone="success">Approved · exported</Badge>;
  if (approved) return <Badge tone="primary">Approved</Badge>;
  return <Badge tone="warning">Draft</Badge>;
}

export function CheckBadge({ status }: { status: CheckStatus }) {
  const tone = status === "pass" ? "success" : status === "warn" ? "warning" : "danger";
  return <Badge tone={tone}>{status === "pass" ? "Pass" : status === "warn" ? "Warning" : "Fail"}</Badge>;
}

const ORIGIN: Record<TextOrigin, string> = {
  verbatim: "From profile",
  rewritten: "AI rewrite (checked)",
  user_edit: "Your edit",
};

export function OriginBadge({ origin }: { origin: TextOrigin }) {
  return <Badge tone={origin === "verbatim" ? "outline" : origin === "rewritten" ? "primary" : "warning"}>{ORIGIN[origin]}</Badge>;
}
