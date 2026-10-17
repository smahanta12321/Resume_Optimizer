import { zodResolver } from "@hookform/resolvers/zod";
import { ExternalLink, FilePlus2, FileText, ListChecks, Scale, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/form-controls";
import { Alert, Card, CardBody, CardHeader } from "@/components/ui/surface";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AnalysisBadge, JobStatusBadge } from "@/components/shared/badges";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryView } from "@/components/shared/states";
import { UnsavedChangesGuard } from "@/components/shared/UnsavedChanges";
import { formatDateTime, humanize } from "@/lib/format";
import { errorMessage } from "@/services/api/client";
import { api } from "@/services/api/endpoints";
import { useDeleteJob, useJob, useJobAction } from "@/services/api/queries";
import type { Job, JobSummary } from "@/services/api/types";
import { AnalysisPanel } from "./AnalysisPanel";
import { MatchPanel } from "./MatchPanel";
import { JobResumesPanel } from "./JobResumesPanel";
import { jobEditSchema, type JobEditValues } from "./schemas";

const TABS = ["details", "analysis", "match", "resumes"] as const;
type Tab = (typeof TABS)[number];

export function JobDetailPage() {
  const { jobId = "" } = useParams();
  const job = useJob(jobId);
  const [params, setParams] = useSearchParams();
  const tab = (TABS as readonly string[]).includes(params.get("tab") ?? "") ? (params.get("tab") as Tab) : "details";

  return (
    <QueryView query={job}>
      {(s) => (
        <>
          <PageHeader
            title={s.display_name}
            crumbs={[{ label: "Job descriptions", to: "/jobs" }, { label: s.display_name }]}
            description={
              <span className="flex flex-wrap items-center gap-2">
                <JobStatusBadge status={s.job.status} />
                <AnalysisBadge state={s.analysis_state} />
                {s.job.location && <span>{s.job.location}</span>}
                <span>Imported {formatDateTime(s.job.imported_at)} via {s.job.import_method}</span>
              </span>
            }
            actions={<JobActions summary={s} />}
          />
          <Tabs value={tab} onValueChange={(v) => setParams({ tab: v }, { replace: true })}>
            <TabsList>
              <TabsTrigger value="details">
                <FileText /> Details
              </TabsTrigger>
              <TabsTrigger value="analysis">
                <ListChecks /> Requirements
              </TabsTrigger>
              <TabsTrigger value="match">
                <Scale /> Match report
              </TabsTrigger>
              <TabsTrigger value="resumes">
                <FilePlus2 /> Resumes ({s.versions})
              </TabsTrigger>
            </TabsList>
            <TabsContent value="details">
              <DetailsForm job={s.job} />
            </TabsContent>
            <TabsContent value="analysis">
              <AnalysisPanel jobId={s.job.id} onConfirmed={() => setParams({ tab: "match" }, { replace: true })} />
            </TabsContent>
            <TabsContent value="match">
              <MatchPanel jobId={s.job.id} onOpenAnalysis={() => setParams({ tab: "analysis" }, { replace: true })} />
            </TabsContent>
            <TabsContent value="resumes">
              <JobResumesPanel jobId={s.job.id} />
            </TabsContent>
          </Tabs>
        </>
      )}
    </QueryView>
  );
}

function JobActions({ summary }: { summary: JobSummary }) {
  const navigate = useNavigate();
  const [confirm, setConfirm] = useState(false);
  const remove = useDeleteJob();
  return (
    <>
      {summary.job.source_url && (
        <Button variant="secondary" asChild>
          <a href={summary.job.source_url} target="_blank" rel="noreferrer noopener">
            <ExternalLink /> Source
          </a>
        </Button>
      )}
      <Button asChild>
        <Link to={`/jobs/${summary.job.id}/tailor`}>
          <FilePlus2 /> Tailor resume
        </Link>
      </Button>
      <Button variant="ghost" size="icon" aria-label="Delete job" onClick={() => setConfirm(true)}>
        <Trash2 />
      </Button>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Delete this job?"
        confirmLabel="Delete job"
        destructive
        loading={remove.isPending}
        onConfirm={() =>
          remove.mutate(summary.job.id, {
            onSuccess: () => {
              toast.success(`Deleted ${summary.display_name}.`);
              navigate("/jobs");
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      >
        <p>
          This deletes <strong>{summary.display_name}</strong> with its analysis, match report, {summary.versions} resume version(s) and
          any exported files. It can't be undone.
        </p>
      </ConfirmDialog>
    </>
  );
}

function DetailsForm({ job }: { job: Job }) {
  const values = (j: Job): JobEditValues => ({ title: j.title, company: j.company, location: j.location, notes: j.notes, description: j.description });
  const form = useForm<JobEditValues>({ resolver: zodResolver(jobEditSchema), defaultValues: values(job) });
  const { register, handleSubmit, formState, reset } = form;
  const patch = useJobAction((v: JobEditValues) => api.jobs.patch(job.id, v));

  // Pick up changes saved elsewhere (another tab, Streamlit) when the form isn't being edited.
  useEffect(() => {
    if (!formState.isDirty) reset(values(job));
  }, [job, formState.isDirty, reset]);

  return (
    <Card>
      <CardHeader
        title="Job details"
        description="Status and application dates are set on the Application Tracker. Changing the description makes its analysis out of date."
      />
      <CardBody>
        <UnsavedChangesGuard when={formState.isDirty} />
        <form
          className="space-y-4"
          noValidate
          onSubmit={handleSubmit((v) =>
            patch.mutate(v, {
              onSuccess: (saved) => {
                reset(values(saved));
                toast.success("Saved.");
              },
              onError: (e) => toast.error(errorMessage(e)),
            }),
          )}
        >
          {job.import_notes.map((n) => (
            <Alert key={n} tone="warning">
              {n}
            </Alert>
          ))}
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Job title" error={formState.errors.title?.message}>
              {(p) => <Input {...p} {...register("title")} />}
            </Field>
            <Field label="Company" error={formState.errors.company?.message}>
              {(p) => <Input {...p} {...register("company")} />}
            </Field>
            <Field label="Location" error={formState.errors.location?.message}>
              {(p) => <Input {...p} {...register("location")} />}
            </Field>
          </div>
          <Field label="Notes">{(p) => <Textarea {...p} rows={3} {...register("notes")} />}</Field>
          <Field
            label="Job description text"
            hint={`${humanize(job.source_platform)} · ${job.source_label || "no source note"}. Stored as untrusted text, never followed as instructions.`}
            error={formState.errors.description?.message}
          >
            {(p) => <Textarea {...p} rows={18} className="font-mono text-xs" {...register("description")} />}
          </Field>
          <div className="flex gap-2">
            <Button type="submit" disabled={!formState.isDirty} loading={patch.isPending}>
              Save changes
            </Button>
            <Button variant="ghost" disabled={!formState.isDirty} onClick={() => reset(values(job))}>
              Undo changes
            </Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}
