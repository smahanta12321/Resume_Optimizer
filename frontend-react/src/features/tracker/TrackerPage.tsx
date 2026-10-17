import { zodResolver } from "@hookform/resolvers/zod";
import { BellRing, ClipboardList, Download, GitMerge, Pencil, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Select, Textarea } from "@/components/ui/form-controls";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Alert, Badge, Card, CardBody, CardHeader } from "@/components/ui/surface";
import { Table, TBody, Td, Th, THead, Tr } from "@/components/ui/table";
import { AnalysisBadge, JobStatusBadge } from "@/components/shared/badges";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { PageHeader } from "@/components/shared/PageHeader";
import { EmptyState, QueryView } from "@/components/shared/states";
import { useDebounced } from "@/hooks/useDebounced";
import { formatDate, formatPercent, humanize, localToday } from "@/lib/format";
import { cn } from "@/lib/utils";
import { errorMessage } from "@/services/api/client";
import { api, type TrackerFilters } from "@/services/api/endpoints";
import { useDuplicates, useJobAction, useJobResumes, useTracker } from "@/services/api/queries";
import { JOB_STATUSES, SOURCE_PLATFORMS, type DuplicatePair, type JobStatus, type SourcePlatform, type TrackerRow } from "@/services/api/types";

const SUMMARY_STATUSES: JobStatus[] = ["saved", "applied", "interviewing", "offer", "rejected"];

export function TrackerPage() {
  const [status, setStatus] = useState<JobStatus[]>([]);
  const [platform, setPlatform] = useState<SourcePlatform | "">("");
  const [search, setSearch] = useState("");
  const [dueOnly, setDueOnly] = useState(false);
  const debounced = useDebounced(search);
  const filters: TrackerFilters = useMemo(
    () => ({ status, platform: platform ? [platform] : [], search: debounced, dueOnly }),
    [status, platform, debounced, dueOnly],
  );
  const tracker = useTracker(filters);
  const [editing, setEditing] = useState<TrackerRow | null>(null);
  const [includeJd, setIncludeJd] = useState(false);
  const [exporting, setExporting] = useState(false);

  return (
    <>
      <PageHeader
        title="Application tracker"
        description="Where you applied and with which resume. You record statuses and dates yourself; the app never applies or contacts anyone for you."
      />
      <QueryView query={tracker}>
        {(t) =>
          t.total === 0 ? (
            <EmptyState
              icon={ClipboardList}
              title="No jobs to track yet"
              action={
                <Button asChild>
                  <Link to="/jobs/new">Import a job</Link>
                </Button>
              }
            />
          ) : (
            <div className="space-y-4">
              {t.follow_ups_due > 0 && (
                <Alert
                  tone="warning"
                  title={`${t.follow_ups_due} follow-up(s) due`}
                  action={
                    <Button size="sm" variant="secondary" onClick={() => setDueOnly(true)}>
                      <BellRing /> Show them
                    </Button>
                  }
                />
              )}
              <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-5">
                {SUMMARY_STATUSES.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setStatus((cur) => (cur.length === 1 && cur[0] === s ? [] : [s]))}
                    className={cn("bg-surface px-4 py-3 text-left transition-colors hover:bg-surface-muted/60", status.length === 1 && status[0] === s && "bg-primary-soft/60")}
                    aria-pressed={status.length === 1 && status[0] === s}
                  >
                    <dt className="text-xs text-muted-foreground">{humanize(s)}</dt>
                    <dd className="text-lg font-semibold tabular-nums">{t.counts[s] ?? 0}</dd>
                  </button>
                ))}
              </dl>

              <Card>
                <div className="flex flex-wrap items-center gap-2 border-b p-3">
                  <div className="relative min-w-48 flex-1 sm:max-w-xs">
                    <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" aria-hidden />
                    <Input
                      className="pl-8"
                      placeholder="Company, role, location, notes"
                      aria-label="Search applications"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                  </div>
                  <Select
                    aria-label="Status"
                    className="w-auto"
                    value={status.length === 1 ? status[0] : ""}
                    onChange={(e) => setStatus(e.target.value ? [e.target.value as JobStatus] : [])}
                  >
                    <option value="">All statuses</option>
                    {JOB_STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {humanize(s)}
                      </option>
                    ))}
                  </Select>
                  <Select aria-label="Platform" className="w-auto" value={platform} onChange={(e) => setPlatform(e.target.value as SourcePlatform | "")}>
                    <option value="">All platforms</option>
                    {SOURCE_PLATFORMS.map((p) => (
                      <option key={p} value={p}>
                        {humanize(p)}
                      </option>
                    ))}
                  </Select>
                  <Checkbox label="Follow-up due" checked={dueOnly} onChange={(e) => setDueOnly(e.target.checked)} />
                  <div className="ml-auto flex items-center gap-2">
                    <Checkbox label="Include JD text" checked={includeJd} onChange={(e) => setIncludeJd(e.target.checked)} />
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={t.rows.length === 0}
                      loading={exporting}
                      onClick={async () => {
                        setExporting(true);
                        try {
                          await api.tracker.exportCsv(filters, includeJd);
                        } catch (e) {
                          toast.error(errorMessage(e));
                        } finally {
                          setExporting(false);
                        }
                      }}
                    >
                      <Download /> CSV
                    </Button>
                  </div>
                </div>
                {t.rows.length === 0 ? (
                  <p className="p-6 text-center text-sm text-muted-foreground">No jobs match these filters.</p>
                ) : (
                  <Table>
                    <THead>
                      <tr>
                        <Th>Role</Th>
                        <Th>Status</Th>
                        <Th className="hidden md:table-cell">Applied</Th>
                        <Th className="hidden md:table-cell">Follow-up</Th>
                        <Th className="hidden lg:table-cell" title="Required-requirement coverage from the match report. An estimate, not an ATS score.">
                          Req. match est.
                        </Th>
                        <Th className="hidden xl:table-cell">Resume</Th>
                        <Th className="sr-only">Actions</Th>
                      </tr>
                    </THead>
                    <TBody>
                      {t.rows.map((r) => (
                        <Tr key={r.job.id}>
                          <Td>
                            <Link to={`/jobs/${r.job.id}`} className="font-medium hover:underline">
                              {r.display_name}
                            </Link>
                            <p className="text-xs text-muted-foreground">{[r.job.location, humanize(r.job.source_platform)].filter(Boolean).join(" · ")}</p>
                          </Td>
                          <Td>
                            <JobStatusBadge status={r.job.status} />
                          </Td>
                          <Td className="hidden whitespace-nowrap md:table-cell">{formatDate(r.job.applied_on)}</Td>
                          <Td className={cn("hidden whitespace-nowrap md:table-cell", r.follow_up_due && "font-medium text-warning")}>
                            {formatDate(r.job.follow_up_on)}
                            {r.follow_up_due && " · due"}
                          </Td>
                          <Td className="hidden lg:table-cell">
                            {r.required_coverage === null ? <AnalysisBadge state={r.analysis_state} /> : formatPercent(r.required_coverage)}
                          </Td>
                          <Td className="hidden text-xs xl:table-cell">
                            <p>
                              {r.approved}/{r.versions} approved
                            </p>
                            {r.resume_label && (
                              <p className="text-muted-foreground">
                                Using {r.resume_label}
                                {r.exported && <Badge tone="success" className="ml-1">exported</Badge>}
                              </p>
                            )}
                          </Td>
                          <Td className="text-right">
                            <Button size="sm" variant="ghost" onClick={() => setEditing(r)} aria-label={`Update ${r.display_name}`}>
                              <Pencil /> <span className="hidden sm:inline">Update</span>
                            </Button>
                          </Td>
                        </Tr>
                      ))}
                    </TBody>
                  </Table>
                )}
              </Card>
              <Duplicates />
            </div>
          )
        }
      </QueryView>
      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        {editing && (
          <DialogContent title={`Update ${editing.display_name}`}>
            <ApplicationForm row={editing} onDone={() => setEditing(null)} />
          </DialogContent>
        )}
      </Dialog>
    </>
  );
}

const today = localToday;

const applicationSchema = z
  .object({
    status: z.enum(JOB_STATUSES as [JobStatus, ...JobStatus[]]),
    applied_on: z.string(),
    follow_up_on: z.string(),
    resume_version_id: z.string(),
    notes: z.string().max(5000),
  })
  .refine((v) => !v.applied_on || v.applied_on <= today(), { message: "Can't be in the future", path: ["applied_on"] });
type ApplicationValues = z.infer<typeof applicationSchema>;

function ApplicationForm({ row, onDone }: { row: TrackerRow; onDone: () => void }) {
  const versions = useJobResumes(row.job.id);
  const { register, handleSubmit, formState } = useForm<ApplicationValues>({
    resolver: zodResolver(applicationSchema),
    defaultValues: {
      status: row.job.status,
      applied_on: row.job.applied_on ?? "",
      follow_up_on: row.job.follow_up_on ?? "",
      resume_version_id: row.job.resume_version_id ?? "",
      notes: row.job.notes,
    },
  });
  const save = useJobAction((v: ApplicationValues) =>
    api.tracker.update(row.job.id, {
      status: v.status,
      applied_on: v.applied_on || null,
      follow_up_on: v.follow_up_on || null,
      resume_version_id: v.resume_version_id || null,
      notes: v.notes,
    }),
  );
  const sorted = [...(versions.data ?? [])].sort((a, b) => Number(Boolean(b.approved_at)) - Number(Boolean(a.approved_at)));

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={handleSubmit((v) =>
        save.mutate(v, {
          onSuccess: (out) => {
            toast.success(`Saved ${row.display_name}.`);
            out.info.forEach((n) => toast.info(n));
            onDone();
          },
          onError: (e) => toast.error(errorMessage(e)),
        }),
      )}
    >
      {row.job.source_url && (
        <p className="text-sm">
          Source:{" "}
          <a className="break-all text-primary underline" href={row.job.source_url} target="_blank" rel="noreferrer noopener">
            {row.job.source_url}
          </a>
        </p>
      )}
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Status">
          {(p) => (
            <Select {...p} {...register("status")}>
              {JOB_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {humanize(s)}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Applied on" error={formState.errors.applied_on?.message}>
          {(p) => <Input {...p} type="date" max={today()} {...register("applied_on")} />}
        </Field>
        <Field label="Follow up on">{(p) => <Input {...p} type="date" {...register("follow_up_on")} />}</Field>
      </div>
      <Field label="Resume used" hint={versions.isPending ? "Loading versions…" : sorted.length === 0 ? "No resume versions for this job yet." : undefined}>
        {(p) => (
          <Select {...p} {...register("resume_version_id")} disabled={versions.isPending}>
            <option value="">None</option>
            {sorted.map((v) => (
              <option key={v.id} value={v.id}>
                {v.id} · {formatDate(v.created_at)} · {v.approved_at ? "approved" : "draft"}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Notes">{(p) => <Textarea {...p} rows={4} {...register("notes")} />}</Field>
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" loading={save.isPending}>
          Save
        </Button>
      </div>
    </form>
  );
}

function Duplicates() {
  const pairs = useDuplicates();
  if (!pairs.data || pairs.data.length === 0) return null;
  return (
    <Card>
      <CardHeader
        title={`Possible duplicates (${pairs.data.length})`}
        description="Merging keeps the record you choose, fills its blank details from the other, appends the other's notes, then deletes the other. Nothing is merged automatically."
      />
      <CardBody className="space-y-4">
        {pairs.data.map((p) => (
          <DuplicateRow key={`${p.first.id}-${p.second.id}`} pair={p} />
        ))}
      </CardBody>
    </Card>
  );
}

function DuplicateRow({ pair }: { pair: DuplicatePair }) {
  const [keepFirst, setKeepFirst] = useState(true);
  const [open, setOpen] = useState(false);
  const keep = keepFirst ? pair.first : pair.second;
  const drop = keepFirst ? pair.second : pair.first;
  const loss = keepFirst ? pair.loss_if_second_dropped : pair.loss_if_first_dropped;
  const merge = useJobAction(() => api.tracker.merge({ keep_id: keep.id, drop_id: drop.id }));
  const name = (j: typeof keep) => [j.title || "Untitled role", j.company].filter(Boolean).join(" @ ");
  return (
    <div className="space-y-2 rounded-md border p-3 text-sm">
      <p>
        <strong>{name(pair.first)}</strong> and <strong>{name(pair.second)}</strong>: {pair.reason}.
      </p>
      <fieldset className="flex flex-wrap gap-3">
        <legend className="sr-only">Record to keep</legend>
        {[pair.first, pair.second].map((j, i) => (
          <label key={j.id} className="flex items-center gap-2">
            <input type="radio" checked={keepFirst === (i === 0)} onChange={() => setKeepFirst(i === 0)} className="accent-[var(--primary)]" />
            Keep {name(j)} ({formatDate(j.imported_at)}, {humanize(j.status)})
          </label>
        ))}
      </fieldset>
      <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
        <GitMerge /> Merge…
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Merge these jobs?"
        confirmLabel="Merge"
        destructive
        loading={merge.isPending}
        onConfirm={() =>
          merge.mutate(undefined, {
            onSuccess: (j) => {
              setOpen(false);
              toast.success(`Merged into ${name(j)}.`);
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      >
        <p>
          Keeps <strong>{name(keep)}</strong> and deletes <strong>{name(drop)}</strong>.
        </p>
        {loss.length > 0 && <Alert tone="warning">The deleted record's {loss.join(", ").replace(/its /g, "")} will be removed.</Alert>}
      </ConfirmDialog>
    </div>
  );
}
