import { zodResolver } from "@hookform/resolvers/zod";
import { CheckCircle2, ListChecks, Plus, RotateCcw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/form-controls";
import { Alert, Badge, Card, CardBody, CardHeader } from "@/components/ui/surface";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { EmptyState, QueryView } from "@/components/shared/states";
import { UnsavedChangesGuard } from "@/components/shared/UnsavedChanges";
import { formatDateTime, humanize } from "@/lib/format";
import { errorMessage } from "@/services/api/client";
import { api } from "@/services/api/endpoints";
import { useAnalysis, useJobAction } from "@/services/api/queries";
import {
  IMPORTANCES,
  REQUIREMENT_CATEGORIES,
  WORK_ARRANGEMENTS,
  type AnalysisView,
  type Importance,
  type JDAnalysis,
  type Job,
  type Requirement,
  type RequirementCategory,
  type WorkArrangement,
} from "@/services/api/types";

const years = z.number().min(0, "0–60").max(60, "0–60").nullable();
const asYears = (v: unknown) => (v === "" || v === null || v === undefined || Number.isNaN(Number(v)) ? null : Number(v));

const schema = z
  .object({
    title: z.string().trim().max(200),
    company: z.string().trim().max(200),
    location: z.string().trim().max(200),
    work_arrangement: z.enum(WORK_ARRANGEMENTS as [WorkArrangement, ...WorkArrangement[]]),
    experience_min_years: years,
    experience_max_years: years,
    requirements: z.array(
      z
        .object({
          id: z.string().nullable(),
          category: z.enum(REQUIREMENT_CATEGORIES as [RequirementCategory, ...RequirementCategory[]]),
          importance: z.enum(IMPORTANCES as [Importance, ...Importance[]]),
          text: z.string().trim().min(1, "Required"),
          normalized_term: z.string().trim(),
          min_years: years,
          max_years: years,
        })
        .refine((r) => r.min_years === null || r.max_years === null || r.min_years <= r.max_years, {
          message: "Min is above max",
          path: ["max_years"],
        }),
    ),
  })
  .refine((v) => v.experience_min_years === null || v.experience_max_years === null || v.experience_min_years <= v.experience_max_years, {
    message: "Minimum is above maximum",
    path: ["experience_max_years"],
  });
type Values = z.infer<typeof schema>;

function toValues(job: Job, a: JDAnalysis): Values {
  return {
    title: job.title,
    company: job.company,
    location: job.location,
    work_arrangement: a.work_arrangement,
    experience_min_years: a.experience_min_years,
    experience_max_years: a.experience_max_years,
    requirements: a.requirements.map((r) => ({
      id: r.id,
      category: r.category,
      importance: r.importance,
      text: r.text,
      normalized_term: r.normalized_term,
      min_years: r.min_years,
      max_years: r.max_years,
    })),
  };
}

export function AnalysisPanel({ jobId, onConfirmed }: { jobId: string; onConfirmed: () => void }) {
  const view = useAnalysis(jobId);
  const run = useJobAction((replace: boolean) => api.analysis.run(jobId, replace));
  return (
    <QueryView query={view}>
      {(v) =>
        v.analysis === null ? (
          <EmptyState
            icon={ListChecks}
            title="Not analyzed yet"
            action={
              <Button
                loading={run.isPending}
                onClick={() =>
                  run.mutate(false, {
                    onSuccess: (out) =>
                      toast.success(
                        `Found ${out.analysis.requirements.length} requirement(s). Review and correct them.` +
                          (out.filled.length ? ` Filled in blank ${out.filled.join(", ")} from the JD; please check.` : ""),
                      ),
                    onError: (e) => toast.error(errorMessage(e)),
                  })
                }
              >
                Analyze job description
              </Button>
            }
          >
            Deterministic rules turn the posting into structured requirements. No AI service is used and nothing leaves your
            computer. The result is a first draft for you to correct and confirm.
          </EmptyState>
        ) : (
          <ReviewForm view={v as AnalysisView & { analysis: JDAnalysis }} onConfirmed={onConfirmed} />
        )
      }
    </QueryView>
  );
}

function Summary({ analysis }: { analysis: JDAnalysis }) {
  const skills = analysis.requirements.filter((r) => r.category === "skill");
  const exp = [analysis.experience_min_years, analysis.experience_max_years];
  const expLabel =
    exp[0] === null && exp[1] === null ? "—" : exp[1] === null ? `${exp[0]}+ yrs` : exp[0] === null ? `up to ${exp[1]} yrs` : `${exp[0]}–${exp[1]} yrs`;
  const stats = [
    ["Requirements", analysis.requirements.length],
    ["Required skills", skills.filter((r) => r.importance === "required").length],
    ["Preferred skills", skills.filter((r) => r.importance === "preferred").length],
    ["Experience", expLabel],
  ] as const;
  return (
    <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-4">
      {stats.map(([label, value]) => (
        <div key={label} className="bg-surface px-4 py-3">
          <dt className="text-xs text-muted-foreground">{label}</dt>
          <dd className="mt-0.5 text-lg font-semibold tabular-nums">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function ReviewForm({ view, onConfirmed }: { view: AnalysisView & { analysis: JDAnalysis }; onConfirmed: () => void }) {
  const { analysis, job, stale } = view;
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: toValues(job, analysis) });
  const { register, control, handleSubmit, formState, reset } = form;
  // keyName keeps RHF's row key separate from the requirement's own `id`.
  const rows = useFieldArray({ control, name: "requirements", keyName: "_key" });
  const [reanalyze, setReanalyze] = useState(false);
  const readOnly = useMemo(() => new Map<string, Requirement>(analysis.requirements.map((r) => [r.id, r])), [analysis]);

  const save = useJobAction((v: Values) => api.analysis.review(job.id, v));
  const confirm = useJobAction(() => api.analysis.confirm(job.id));
  const rerun = useJobAction(() => api.analysis.run(job.id, true));

  useEffect(() => {
    if (!formState.isDirty) reset(toValues(job, analysis));
  }, [job, analysis, formState.isDirty, reset]);

  const n = (path: Parameters<typeof register>[0]) => register(path, { setValueAs: asYears });
  const e = formState.errors;

  return (
    <div className="space-y-4">
      <UnsavedChangesGuard when={formState.isDirty} />
      {stale ? (
        <Alert tone="warning" title="The job description changed after this analysis">
          Re-analyze it, or review the requirements carefully. It can't be confirmed while out of date.
        </Alert>
      ) : analysis.confirmed_at ? (
        <Alert tone="success">Confirmed {formatDateTime(analysis.confirmed_at)}. Any edit will need re-confirmation.</Alert>
      ) : (
        <Alert tone="info">Draft: correct the details and requirements, save, then confirm.</Alert>
      )}
      {analysis.warnings.map((w) => (
        <Alert key={w} tone="warning">
          {w}
        </Alert>
      ))}
      <Summary analysis={analysis} />

      <form
        noValidate
        onSubmit={handleSubmit((v) =>
          save.mutate(v, {
            onSuccess: (out) => {
              if (out.analysis) reset(toValues(out.job, out.analysis));
              toast.success(out.analysis?.confirmed_at ? "Review saved." : "Review saved. Confirm it when you're satisfied.");
            },
            onError: (err) => toast.error(errorMessage(err)),
          }),
        )}
        className="space-y-4"
      >
        <Card>
          <CardHeader title="Job details" />
          <CardBody className="grid gap-4 sm:grid-cols-3">
            <Field label="Job title">{(p) => <Input {...p} {...register("title")} />}</Field>
            <Field label="Company">{(p) => <Input {...p} {...register("company")} />}</Field>
            <Field label="Location">{(p) => <Input {...p} {...register("location")} />}</Field>
            <Field label="Work arrangement">
              {(p) => (
                <Select {...p} {...register("work_arrangement")}>
                  {WORK_ARRANGEMENTS.map((w) => (
                    <option key={w} value={w}>
                      {humanize(w)}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Experience: minimum years" error={e.experience_min_years?.message}>
              {(p) => <Input {...p} type="number" min={0} max={60} step={0.5} {...n("experience_min_years")} />}
            </Field>
            <Field label="Experience: maximum years" error={e.experience_max_years?.message}>
              {(p) => <Input {...p} type="number" min={0} max={60} step={0.5} {...n("experience_max_years")} />}
            </Field>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title={`Requirements (${rows.fields.length})`}
            description="Edit, add or remove. JD excerpt, confidence and origin are filled in automatically."
            actions={
              <Button
                size="sm"
                variant="secondary"
                onClick={() =>
                  rows.append({ id: null, category: "skill", importance: "required", text: "", normalized_term: "", min_years: null, max_years: null })
                }
              >
                <Plus /> Add requirement
              </Button>
            }
          />
          <ul className="divide-y">
            {rows.fields.map((field, i) => {
              const ro = field.id ? readOnly.get(field.id) : undefined;
              const re = e.requirements?.[i];
              return (
                <li key={field._key} className="grid gap-3 p-4 md:grid-cols-[9rem_8rem_1fr_9rem_5rem_5rem_auto]">
                  <Field label="Category" className="md:[&>label]:sr-only">
                    {(p) => (
                      <Select {...p} {...register(`requirements.${i}.category`)}>
                        {REQUIREMENT_CATEGORIES.map((c) => (
                          <option key={c} value={c}>
                            {humanize(c)}
                          </option>
                        ))}
                      </Select>
                    )}
                  </Field>
                  <Field label="Importance" className="md:[&>label]:sr-only">
                    {(p) => (
                      <Select {...p} {...register(`requirements.${i}.importance`)}>
                        {IMPORTANCES.map((c) => (
                          <option key={c} value={c}>
                            {humanize(c)}
                          </option>
                        ))}
                      </Select>
                    )}
                  </Field>
                  <div className="space-y-1">
                    <Field label="Requirement" className="md:[&>label]:sr-only" error={re?.text?.message}>
                      {(p) => <Input {...p} {...register(`requirements.${i}.text`)} />}
                    </Field>
                    {ro && (
                      <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                        <Badge tone={ro.origin === "user" ? "primary" : "outline"}>{ro.origin === "user" ? "Edited by you" : `Parser · ${Math.round(ro.confidence * 100)}%`}</Badge>
                        {ro.source_excerpt && <span className="line-clamp-1 italic">“{ro.source_excerpt}”</span>}
                      </p>
                    )}
                  </div>
                  <Field label="Normalized term" className="md:[&>label]:sr-only">
                    {(p) => <Input {...p} placeholder="Normalized term" {...register(`requirements.${i}.normalized_term`)} />}
                  </Field>
                  <Field label="Min yrs" className="md:[&>label]:sr-only">
                    {(p) => <Input {...p} type="number" min={0} max={60} placeholder="Min" {...n(`requirements.${i}.min_years`)} />}
                  </Field>
                  <Field label="Max yrs" className="md:[&>label]:sr-only" error={re?.max_years?.message}>
                    {(p) => <Input {...p} type="number" min={0} max={60} placeholder="Max" {...n(`requirements.${i}.max_years`)} />}
                  </Field>
                  <Button variant="ghost" size="icon" aria-label={`Remove requirement ${i + 1}`} onClick={() => rows.remove(i)} className="self-start">
                    <Trash2 />
                  </Button>
                </li>
              );
            })}
            {rows.fields.length === 0 && <li className="p-6 text-center text-sm text-muted-foreground">No requirements. Add the ones the posting asks for.</li>}
          </ul>
        </Card>

        <div className="flex flex-wrap items-center gap-2">
          <Button type="submit" disabled={!formState.isDirty} loading={save.isPending}>
            Save review
          </Button>
          <Button
            variant="secondary"
            disabled={formState.isDirty || stale || Boolean(analysis.confirmed_at)}
            title={formState.isDirty ? "Save your edits first" : undefined}
            loading={confirm.isPending}
            onClick={() =>
              confirm.mutate(undefined, {
                onSuccess: () => {
                  toast.success("Analysis confirmed. Next, compare it with your profile.");
                  onConfirmed();
                },
                onError: (err) => toast.error(errorMessage(err)),
              })
            }
          >
            <CheckCircle2 /> Confirm analysis
          </Button>
          <Button variant="ghost" onClick={() => setReanalyze(true)}>
            <RotateCcw /> Re-analyze from JD text
          </Button>
        </div>
      </form>

      <ConfirmDialog
        open={reanalyze}
        onOpenChange={setReanalyze}
        title="Re-analyze this job?"
        confirmLabel="Discard edits and re-analyze"
        destructive
        loading={rerun.isPending}
        onConfirm={() =>
          rerun.mutate(undefined, {
            onSuccess: (out) => {
              reset(toValues(out.job, out.analysis));
              setReanalyze(false);
              toast.success(`Re-analyzed: ${out.analysis.requirements.length} requirement(s).`);
            },
            onError: (err) => toast.error(errorMessage(err)),
          })
        }
      >
        <p>This replaces the current requirements with a fresh parser draft. Your edits and confirmation will be lost.</p>
      </ConfirmDialog>
    </div>
  );
}
