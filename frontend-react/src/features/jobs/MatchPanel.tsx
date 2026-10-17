import { Info, PencilLine, RefreshCw, Scale } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Select } from "@/components/ui/form-controls";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Alert, Badge, Card, CardBody, CardHeader } from "@/components/ui/surface";
import { Table, TBody, Td, Th, THead, Tr } from "@/components/ui/table";
import { MatchStatusBadge } from "@/components/shared/badges";
import { EvidenceChips } from "@/components/shared/EvidenceChips";
import { EmptyState, QueryView } from "@/components/shared/states";
import { formatDateTime, formatPercent, humanize } from "@/lib/format";
import { cn } from "@/lib/utils";
import { errorMessage } from "@/services/api/client";
import { api } from "@/services/api/endpoints";
import { useJobAction, useMatch } from "@/services/api/queries";
import {
  MATCH_STATUSES,
  REQUIREMENT_CATEGORIES,
  type GroupStats,
  type MatchRow,
  type MatchStatus,
  type MatchView,
  type Recommendation,
  type RequirementCategory,
} from "@/services/api/types";

/** How the matcher found (or didn't find) evidence. Text overlap and related terms are hints to check. */
const MATCH_TYPE_LABEL: Record<string, string> = {
  exact: "Exact term",
  alias: "Recorded alias",
  related: "Related term only",
  text_overlap: "Wording overlap (check it)",
  computed: "From dates or degree",
  none: "No match found",
};

export function MatchPanel({ jobId, onOpenAnalysis }: { jobId: string; onOpenAnalysis?: () => void }) {
  const match = useMatch(jobId);
  const run = useJobAction(() => api.match.run(jobId));
  const runMatching = () =>
    run.mutate(undefined, {
      onSuccess: (out) => {
        toast.success(`Matched ${out.view.rows.length} requirement(s) against profile v${out.view.profile_version}.`);
        out.notes.forEach((n) => toast.warning(n));
      },
      onError: (e) => toast.error(errorMessage(e)),
    });

  return (
    <QueryView query={match}>
      {(v) => {
        if (v.blockers.length > 0) {
          return (
            <Alert
              tone="info"
              title="Matching isn't available yet"
              action={
                onOpenAnalysis && v.profile_version !== null ? (
                  <Button size="sm" variant="secondary" onClick={onOpenAnalysis}>
                    Review requirements
                  </Button>
                ) : v.profile_version === null ? (
                  <Button size="sm" variant="secondary" asChild>
                    <Link to="/profile">Master profile</Link>
                  </Button>
                ) : undefined
              }
            >
              {v.blockers[0]}
            </Alert>
          );
        }
        if (!v.report) {
          return (
            <EmptyState
              icon={Scale}
              title="No match report yet"
              action={
                <Button onClick={runMatching} loading={run.isPending}>
                  Run matching
                </Button>
              }
            >
              Compares the confirmed requirements with your master profile. Each requirement is marked supported, partial or not
              documented, citing the evidence behind it. Nothing is inferred.
            </EmptyState>
          );
        }
        return <Report view={v} jobId={jobId} onRerun={runMatching} rerunning={run.isPending} />;
      }}
    </QueryView>
  );
}

function Report({ view, jobId, onRerun, rerunning }: { view: MatchView; jobId: string; onRerun: () => void; rerunning: boolean }) {
  const [statuses, setStatuses] = useState<MatchStatus[]>(MATCH_STATUSES);
  const [category, setCategory] = useState<RequirementCategory | "all">("all");
  const [editing, setEditing] = useState<MatchRow | null>(null);
  const summary = view.summary;
  const report = view.report;

  const rows = useMemo(
    () => view.rows.filter((r) => statuses.includes(r.status) && (category === "all" || r.requirement.category === category)),
    [view.rows, statuses, category],
  );

  return (
    <div className="space-y-4">
      {!view.profile_confirmed && (
        <Alert tone="warning">
          Profile v{view.profile_version} hasn't been confirmed. The report uses it as-is; review and confirm it on{" "}
          <Link className="underline" to="/profile">
            Master Profile
          </Link>{" "}
          so the report rests on checked facts.
        </Alert>
      )}
      {view.stale_reasons.length > 0 && (
        <Alert
          tone="warning"
          title="This report is out of date"
          action={
            <Button size="sm" onClick={onRerun} loading={rerunning}>
              <RefreshCw /> Re-run
            </Button>
          }
        >
          {view.stale_reasons.join(" ")} Your judgements are kept when you re-run.
        </Alert>
      )}

      {summary && <CoverageSummary groups={summary.groups} overall={summary.overall} overrides={summary.overrides} formula={summary.formula} />}

      <Card>
        <CardHeader
          title="Requirements"
          description={report && `Matched against profile v${report.profile_version} on ${formatDateTime(report.updated_at)} using ${report.matcher}.`}
          actions={
            view.stale_reasons.length === 0 && (
              <Button size="sm" variant="secondary" onClick={onRerun} loading={rerunning}>
                <RefreshCw /> Re-run matching
              </Button>
            )
          }
        />
        <div className="flex flex-wrap items-center gap-4 border-b px-4 py-3">
          <fieldset className="flex flex-wrap gap-3">
            <legend className="sr-only">Status</legend>
            {MATCH_STATUSES.map((s) => (
              <Checkbox
                key={s}
                label={humanize(s)}
                checked={statuses.includes(s)}
                onChange={(e) => setStatuses((cur) => (e.target.checked ? [...cur, s] : cur.filter((x) => x !== s)))}
              />
            ))}
          </fieldset>
          <Select
            aria-label="Category"
            className="w-auto"
            value={category}
            onChange={(e) => setCategory(e.target.value as RequirementCategory | "all")}
          >
            <option value="all">All categories</option>
            {REQUIREMENT_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {humanize(c)}
              </option>
            ))}
          </Select>
        </div>
        {rows.length === 0 ? (
          <p className="p-6 text-center text-sm text-muted-foreground">No requirements match these filters.</p>
        ) : (
          <Table>
            <THead>
              <tr>
                <Th>Status</Th>
                <Th>Requirement</Th>
                <Th className="hidden lg:table-cell">Evidence</Th>
                <Th className="sr-only">Actions</Th>
              </tr>
            </THead>
            <TBody>
              {rows.map((r) => (
                <Tr key={r.requirement.id}>
                  <Td className="whitespace-nowrap">
                    <MatchStatusBadge status={r.status} own={r.has_override} />
                  </Td>
                  <Td className="min-w-64">
                    <p className="font-medium">{r.requirement.text}</p>
                    <p className="mt-0.5 flex flex-wrap gap-1.5 text-xs text-muted-foreground">
                      <span>{humanize(r.requirement.importance)}</span>·<span>{humanize(r.requirement.category)}</span>·
                      <span>{r.has_override ? "Your judgement" : (MATCH_TYPE_LABEL[r.match_type] ?? humanize(r.match_type))}</span>
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">{r.has_override ? r.override_note || "Set by you." : r.explanation}</p>
                    <div className="mt-2 lg:hidden">
                      <EvidenceChips ids={r.evidence_ids} evidence={view.evidence} />
                    </div>
                  </Td>
                  <Td className="hidden max-w-80 lg:table-cell">
                    <EvidenceChips ids={r.evidence_ids} evidence={view.evidence} />
                  </Td>
                  <Td className="text-right">
                    <Button size="sm" variant="ghost" onClick={() => setEditing(r)} aria-label={`Correct result for ${r.requirement.text}`}>
                      <PencilLine /> <span className="hidden sm:inline">Correct</span>
                    </Button>
                  </Td>
                </Tr>
              ))}
            </TBody>
          </Table>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader title="Gaps" description="Required or preferred, with no documented evidence." />
          <CardBody>
            {view.gaps.length === 0 ? (
              <p className="text-sm text-muted-foreground">Every required and preferred requirement has some documented evidence.</p>
            ) : (
              <>
                <ul className="space-y-1.5 text-sm">
                  {view.gaps.map((g) => (
                    <li key={g.id} className="flex gap-2">
                      <Badge tone={g.importance === "required" ? "danger" : "warning"}>{humanize(g.importance)}</Badge>
                      <span>{g.text}</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-xs text-muted-foreground">
                  These won't appear in a tailored resume. If you do have this experience, add it to your master profile with real evidence
                  and re-run matching. Otherwise, leave it out.
                </p>
              </>
            )}
          </CardBody>
        </Card>
        <Recommendations
          title="Base role profile"
          items={view.role_recommendations}
          empty={view.has_role_profiles ? "None of your role profiles include evidence for the matched requirements." : "No role profiles yet."}
        />
        <Recommendations title="Most relevant projects" items={view.project_recommendations} empty="No projects support the matched requirements." />
      </div>

      {editing && <OverrideDialog jobId={jobId} row={editing} view={view} onClose={() => setEditing(null)} />}
    </div>
  );
}

export function CoverageSummary({
  groups,
  overall,
  overrides,
  formula,
}: {
  groups: Record<string, GroupStats>;
  overall: number | null;
  overrides: number;
  formula: string;
}) {
  const [showFormula, setShowFormula] = useState(false);
  const cell = (label: string, g: GroupStats | undefined) => (
    <div className="bg-surface px-4 py-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-lg font-semibold tabular-nums">{formatPercent(g?.coverage)}</dd>
      {g && g.total > 0 && (
        <>
          <CoverageBar g={g} />
          <p className="mt-1 text-xs text-muted-foreground">
            {g.supported} supported · {g.partial} partial · {g.not_documented} not documented
          </p>
        </>
      )}
    </div>
  );
  return (
    <div className="space-y-2">
      <dl className="grid gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-2 lg:grid-cols-4">
        {cell("Required coverage", groups.required)}
        {cell("Preferred coverage", groups.preferred)}
        <div className="bg-surface px-4 py-3">
          <dt className="text-xs text-muted-foreground">Overall coverage (weighted)</dt>
          <dd className="mt-0.5 text-lg font-semibold tabular-nums">{formatPercent(overall)}</dd>
        </div>
        <div className="bg-surface px-4 py-3">
          <dt className="text-xs text-muted-foreground">Your judgements</dt>
          <dd className="mt-0.5 text-lg font-semibold tabular-nums">{overrides}</dd>
        </div>
      </dl>
      <button
        type="button"
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        aria-expanded={showFormula}
        onClick={() => setShowFormula((s) => !s)}
      >
        <Info className="size-3.5" /> Match estimate, not an ATS score. How is this calculated?
      </button>
      {showFormula && <p className="rounded-md border bg-surface-muted/50 px-3 py-2 text-xs text-muted-foreground">{formula.replace(/\*\*/g, "")}</p>}
    </div>
  );
}

function CoverageBar({ g }: { g: GroupStats }) {
  const pct = (n: number) => `${(n / g.total) * 100}%`;
  return (
    <div className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-surface-muted" aria-hidden>
      <div className="bg-success" style={{ width: pct(g.supported) }} />
      <div className="bg-warning" style={{ width: pct(g.partial) }} />
    </div>
  );
}

function Recommendations({ title, items, empty }: { title: string; items: Recommendation[]; empty: string }) {
  return (
    <Card>
      <CardHeader title={title} description="Share of evidenced requirement weight each one covers (required ×3, preferred ×2)." />
      <CardBody>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{empty}</p>
        ) : (
          <ul className="space-y-3">
            {items.map((r) => (
              <li key={r.id} className="space-y-1">
                <div className="flex items-baseline justify-between gap-2 text-sm">
                  <span className="font-medium">{r.name}</span>
                  <span className="tabular-nums text-muted-foreground">{formatPercent(r.score)}</span>
                </div>
                <p className="line-clamp-2 text-xs text-muted-foreground">{r.covered.join(", ")}</p>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}

function OverrideDialog({ jobId, row, view, onClose }: { jobId: string; row: MatchRow; view: MatchView; onClose: () => void }) {
  const [status, setStatus] = useState<MatchStatus>(row.status);
  const [evidence, setEvidence] = useState<string[]>(row.evidence_ids.filter((id) => view.evidence.some((e) => e.id === id)));
  const [note, setNote] = useState(row.override_note);
  const [filter, setFilter] = useState("");
  const save = useJobAction(() => api.match.setOverride(jobId, row.requirement.id, { status, evidence_ids: evidence, note }));
  const clear = useJobAction(() => api.match.clearOverride(jobId, row.requirement.id));
  const needsEvidence = status !== "not_documented" && evidence.length === 0;
  const shown = view.evidence.filter((e) => e.label.toLowerCase().includes(filter.trim().toLowerCase()));

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        title="Correct a result"
        description={row.requirement.text}
        footer={
          <>
            {row.has_override && (
              <Button
                variant="ghost"
                className="mr-auto"
                loading={clear.isPending}
                onClick={() =>
                  clear.mutate(undefined, {
                    onSuccess: () => {
                      toast.success("Cleared. The matcher's result applies again.");
                      onClose();
                    },
                    onError: (e) => toast.error(errorMessage(e)),
                  })
                }
              >
                Clear my judgement
              </Button>
            )}
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button
              disabled={needsEvidence}
              loading={save.isPending}
              onClick={() =>
                save.mutate(undefined, {
                  onSuccess: () => {
                    toast.success("Saved your judgement.");
                    onClose();
                  },
                  onError: (e) => toast.error(errorMessage(e)),
                })
              }
            >
              Save judgement
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Supported and partial must cite at least one item from your profile. If the evidence isn't there yet, add it to the master
            profile first.
          </p>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Status</legend>
            <div className="flex flex-wrap gap-2">
              {MATCH_STATUSES.map((s) => (
                <label
                  key={s}
                  className={cn(
                    "flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-sm",
                    status === s && "border-primary bg-primary-soft",
                  )}
                >
                  <input type="radio" name="status" value={s} checked={status === s} onChange={() => setStatus(s)} className="accent-[var(--primary)]" />
                  {humanize(s)}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Evidence ({evidence.length} selected)</legend>
            <Input placeholder="Filter evidence" aria-label="Filter evidence" value={filter} onChange={(e) => setFilter(e.target.value)} />
            <div className="max-h-56 space-y-1.5 overflow-y-auto rounded-md border p-2">
              {shown.map((e) => (
                <Checkbox
                  key={e.id}
                  label={<span className="font-normal">{e.label}</span>}
                  description={`${e.kind} · ${e.id}`}
                  checked={evidence.includes(e.id)}
                  onChange={(ev) => setEvidence((cur) => (ev.target.checked ? [...cur, e.id] : cur.filter((x) => x !== e.id)))}
                />
              ))}
              {shown.length === 0 && <p className="p-2 text-sm text-muted-foreground">No evidence matches.</p>}
            </div>
            {needsEvidence && <p className="text-xs text-warning">Select at least one evidence item for {humanize(status).toLowerCase()}.</p>}
          </fieldset>
          <Field label="Note (why)">{(p) => <Input {...p} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
        </div>
      </DialogContent>
    </Dialog>
  );
}
