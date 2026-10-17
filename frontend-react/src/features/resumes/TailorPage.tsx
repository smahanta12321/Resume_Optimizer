import { Check } from "lucide-react";
import type { ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/form-controls";
import { Alert, Card, CardBody } from "@/components/ui/surface";
import { PageHeader } from "@/components/shared/PageHeader";
import { LoadingRows, QueryView } from "@/components/shared/states";
import { AnalysisPanel } from "@/features/jobs/AnalysisPanel";
import { MatchPanel } from "@/features/jobs/MatchPanel";
import { cn } from "@/lib/utils";
import { formatDateTime } from "@/lib/format";
import { useAnalysis, useJob, useJobResumes, useMatch } from "@/services/api/queries";
import { GenerateStep } from "./GenerateStep";
import { VersionWorkspace } from "./VersionWorkspace";
import { generatorLabel } from "./VersionTable";

const STEPS = [
  { id: "requirements", label: "Confirm requirements" },
  { id: "match", label: "Match evidence" },
  { id: "generate", label: "Generate draft" },
  { id: "review", label: "Review, approve & export" },
] as const;
type StepId = (typeof STEPS)[number]["id"];

/**
 * The guided tailoring workflow. Progress comes from what's saved in the backend, so leaving and
 * coming back (or going back a step) never loses work.
 */
export function TailorPage() {
  const { jobId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const job = useJob(jobId);
  const analysis = useAnalysis(jobId);
  const match = useMatch(jobId);
  const versions = useJobResumes(jobId);

  const loading = job.isPending || analysis.isPending || match.isPending || versions.isPending;
  const done: Record<StepId, boolean> = {
    requirements: Boolean(analysis.data?.analysis?.confirmed_at) && !analysis.data?.stale,
    match: Boolean(match.data?.report) && (match.data?.stale_reasons.length ?? 1) === 0,
    generate: (versions.data?.length ?? 0) > 0,
    review: Boolean(versions.data?.some((v) => v.exported)),
  };
  const firstOpen = STEPS.find((s) => !done[s.id])?.id ?? "review";
  const requested = params.get("step") as StepId | null;
  const step: StepId = requested && STEPS.some((s) => s.id === requested) ? requested : firstOpen;
  const go = (id: StepId, extra: Record<string, string> = {}) => setParams({ step: id, ...extra });

  const versionId = params.get("version") ?? versions.data?.[0]?.id;

  return (
    <QueryView query={job}>
      {(s) => (
        <>
          <PageHeader
            title="Tailor a resume"
            crumbs={[
              { label: "Tailor", to: "/tailor" },
              { label: s.display_name, to: `/jobs/${s.job.id}` },
            ]}
            description={
              <>
                For <strong>{s.display_name}</strong>. Tailoring may reorder, emphasise or rephrase your verified facts. It never adds
                qualifications, metrics, skills or experience.
              </>
            }
          />
          <ol className="mb-6 grid gap-2 sm:grid-cols-4" aria-label="Progress">
            {STEPS.map((st, i) => (
              <li key={st.id}>
                <button
                  type="button"
                  onClick={() => go(st.id, versionId && st.id === "review" ? { version: versionId } : {})}
                  aria-current={step === st.id ? "step" : undefined}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-md border px-3 py-2 text-left text-sm transition-colors hover:bg-surface-muted/60",
                    step === st.id && "border-primary bg-primary-soft/60",
                  )}
                >
                  <span
                    className={cn(
                      "grid size-6 shrink-0 place-items-center rounded-full border text-xs font-semibold",
                      done[st.id] ? "border-success bg-success text-white" : step === st.id ? "border-primary text-primary" : "text-muted-foreground",
                    )}
                  >
                    {done[st.id] ? <Check className="size-3.5" aria-label="done" /> : i + 1}
                  </span>
                  <span className={cn("font-medium", step !== st.id && "text-muted-foreground")}>{st.label}</span>
                </button>
              </li>
            ))}
          </ol>

          {loading ? (
            <LoadingRows />
          ) : (
            <>
              {step === "requirements" && (
                <StepFrame
                  next={done.requirements && <Button onClick={() => go("match")}>Continue to matching</Button>}
                >
                  <AnalysisPanel jobId={jobId} onConfirmed={() => go("match")} />
                </StepFrame>
              )}
              {step === "match" && (
                <StepFrame
                  back={<Button variant="secondary" onClick={() => go("requirements")}>Back</Button>}
                  next={done.match && <Button onClick={() => go("generate")}>Continue to generate</Button>}
                >
                  <MatchPanel jobId={jobId} onOpenAnalysis={() => go("requirements")} />
                </StepFrame>
              )}
              {step === "generate" && (
                <StepFrame
                  back={<Button variant="secondary" onClick={() => go("match")}>Back</Button>}
                  next={
                    done.generate && (
                      <Button variant="secondary" onClick={() => go("review")}>
                        Review existing versions
                      </Button>
                    )
                  }
                >
                  <GenerateStep jobId={jobId} onGenerated={(id) => go("review", { version: id })} />
                </StepFrame>
              )}
              {step === "review" &&
                (!versionId ? (
                  <Alert tone="info" action={<Button size="sm" onClick={() => go("generate")}>Generate a draft</Button>}>
                    No resume version for this job yet.
                  </Alert>
                ) : (
                  <div className="space-y-4">
                    {(versions.data?.length ?? 0) > 1 && (
                      <Card>
                        <CardBody className="py-3">
                          <Field label="Version">
                            {(p) => (
                              <Select {...p} value={versionId} onChange={(e) => go("review", { version: e.target.value })}>
                                {versions.data?.map((v) => (
                                  <option key={v.id} value={v.id}>
                                    {v.id} · {formatDateTime(v.created_at)} · {generatorLabel(v.generator)}
                                    {v.approved_at ? " · approved" : " · draft"}
                                    {v.parent_id ? ` · edited from ${v.parent_id}` : ""}
                                  </option>
                                ))}
                              </Select>
                            )}
                          </Field>
                        </CardBody>
                      </Card>
                    )}
                    <VersionWorkspace versionId={versionId} onNewVersion={(id) => go("review", { version: id, view: "approve" })} />
                    <div className="flex flex-wrap gap-2">
                      <Button variant="secondary" onClick={() => go("generate")}>
                        Generate another version
                      </Button>
                      <Button variant="ghost" asChild>
                        <Link to="/tracker">Record the application in the tracker</Link>
                      </Button>
                    </div>
                  </div>
                ))}
            </>
          )}
        </>
      )}
    </QueryView>
  );
}

function StepFrame({ children, back, next }: { children: ReactNode; back?: ReactNode; next?: ReactNode }) {
  return (
    <div className="space-y-4">
      {children}
      {(back || next) && (
        <div className="flex flex-wrap justify-between gap-2 border-t pt-4">
          <div>{back}</div>
          <div>{next}</div>
        </div>
      )}
    </div>
  );
}
