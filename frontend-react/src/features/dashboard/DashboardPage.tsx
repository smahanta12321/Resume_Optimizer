import { ArrowRight, BellRing, Briefcase, CheckCircle2, Circle, FilePlus2, Inbox, ShieldAlert, UserRound } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { Alert, Card, CardBody, CardHeader } from "@/components/ui/surface";
import { JobStatusBadge, VersionStateBadge } from "@/components/shared/badges";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryView } from "@/components/shared/states";
import { formatDate, formatDateTime, pluralize } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useDashboard } from "@/services/api/queries";
import type { Dashboard } from "@/services/api/types";

export function DashboardPage() {
  const dash = useDashboard();
  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Tailor truthful resumes from your verified profile. The app never applies to jobs or contacts recruiters, and it doesn't predict ATS outcomes."
        actions={
          <Button asChild>
            <Link to="/tailor">
              <FilePlus2 /> Tailor a resume
            </Link>
          </Button>
        }
      />
      <QueryView query={dash}>{(d) => (d.profile.state !== "ok" && d.jobs_total === 0 ? <FirstRun d={d} /> : <Overview d={d} />)}</QueryView>
    </>
  );
}

function Step({ done, title, children, action }: { done: boolean; title: string; children: ReactNode; action?: ReactNode }) {
  const Icon = done ? CheckCircle2 : Circle;
  return (
    <li className="flex gap-3 py-4 first:pt-0 last:pb-0">
      <Icon className={cn("mt-0.5 size-5 shrink-0", done ? "text-success" : "text-muted-foreground")} aria-label={done ? "Done" : "To do"} />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="font-medium">{title}</p>
        <p className="text-sm text-muted-foreground">{children}</p>
        {action && <div className="pt-1">{action}</div>}
      </div>
    </li>
  );
}

function FirstRun({ d }: { d: Dashboard }) {
  return (
    <Card className="max-w-2xl">
      <CardHeader title="Get started" description="Three steps to your first tailored, evidence-backed resume." />
      <CardBody>
        {d.profile.state === "unreadable" && (
          <Alert tone="danger" className="mb-4" title="Your saved profile couldn't be read">
            Open Master Profile to import a backup or restore an earlier version.
          </Alert>
        )}
        <ol className="divide-y">
          <Step
            done={false}
            title="Create your master profile"
            action={
              <Button size="sm" asChild>
                <Link to="/profile">
                  <UserRound /> Master profile
                </Link>
              </Button>
            }
          >
            Your experience, projects, skills and education: the only facts a tailored resume may use. Start from scratch, import JSON, or explore
            with the fictional sample.
          </Step>
          <Step done={false} title="Import a job description">
            Paste a posting, upload a file, or try a URL. You review the text before it's saved.
          </Step>
          <Step done={false} title="Tailor, review and export">
            Confirm the requirements, see which ones your evidence supports, generate a draft, approve it, and export DOCX and PDF.
          </Step>
        </ol>
      </CardBody>
    </Card>
  );
}

function Stat({ label, value, to }: { label: string; value: number; to: string }) {
  return (
    <Link to={to} className="group bg-surface px-4 py-3 transition-colors hover:bg-surface-muted/60">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-0.5 flex items-center justify-between text-2xl font-semibold tabular-nums">
        {value}
        <ArrowRight className="size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
      </p>
    </Link>
  );
}

function Overview({ d }: { d: Dashboard }) {
  const p = d.profile;
  const pipeline = [
    ["Saved", d.jobs_total],
    ["Requirements analyzed", d.jobs_analyzed],
    ["Matched to evidence", d.jobs_matched],
    ["Approved resume", d.jobs_with_approved_resume],
    ["Exported", d.jobs_exported],
  ] as const;

  return (
    <div className="space-y-6">
      {p.state === "missing" && (
        <Alert tone="warning" title="No master profile yet" action={<Button size="sm" asChild><Link to="/profile">Create it</Link></Button>}>
          Tailored resumes can only use facts from your master profile.
        </Alert>
      )}
      {p.state === "unreadable" && <Alert tone="danger">Your saved profile couldn't be read. Open Master Profile to import a backup or restore a version.</Alert>}
      {p.is_sample && <Alert tone="info">You're using the fictional sample profile. Replace it with your own data before real use.</Alert>}
      {d.captures_waiting > 0 && (
        <Alert
          tone="info"
          title={`${pluralize(d.captures_waiting, "capture")} from the browser extension waiting for review`}
          action={
            <Button size="sm" variant="secondary" asChild>
              <Link to="/jobs/new?source=inbox">
                <Inbox /> Review
              </Link>
            </Button>
          }
        />
      )}
      {d.follow_ups_due.length > 0 && (
        <Alert tone="warning" title="Follow-ups due" action={<Button size="sm" variant="secondary" asChild><Link to="/tracker"><BellRing /> Tracker</Link></Button>}>
          {d.follow_ups_due.map((j) => `${j.display_name} (${formatDate(j.follow_up_on)})`).join("; ")}
        </Alert>
      )}

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border lg:grid-cols-4">
        <Stat label="Saved job descriptions" value={d.jobs_total} to="/jobs" />
        <Stat label="Tailored resume versions" value={d.versions_total} to="/resumes" />
        <Stat label="Applications tracked" value={d.applications_tracked} to="/tracker" />
        <Stat label="Role profiles" value={d.role_profiles.length} to="/roles" />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader title="Master profile" />
          <CardBody className="space-y-3 text-sm">
            {p.state === "ok" ? (
              <>
                <p className="flex items-center gap-2">
                  {p.confirmed_at ? (
                    <>
                      <CheckCircle2 className="size-4 text-success" /> v{p.version} confirmed {formatDate(p.confirmed_at)}
                    </>
                  ) : (
                    <>
                      <ShieldAlert className="size-4 text-warning" /> v{p.version} not confirmed yet
                    </>
                  )}
                </p>
                <p className="text-muted-foreground">
                  {pluralize(p.experience, "experience entry", "experience entries")} · {pluralize(p.projects, "project")} ·{" "}
                  {pluralize(p.skills, "skill")}
                </p>
                {p.warnings > 0 && <p className="text-warning">{pluralize(p.warnings, "quality note")} to review</p>}
                <Button size="sm" variant="secondary" asChild>
                  <Link to="/profile">{p.confirmed_at ? "Open profile" : "Review and confirm"}</Link>
                </Button>
              </>
            ) : (
              <p className="text-muted-foreground">Not available.</p>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Pipeline" description="Jobs at each stage." />
          <CardBody>
            <ul className="space-y-2.5">
              {pipeline.map(([label, n]) => (
                <li key={label} className="space-y-1">
                  <div className="flex justify-between text-sm">
                    <span>{label}</span>
                    <span className="tabular-nums text-muted-foreground">{n}</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-surface-muted" aria-hidden>
                    <div className="h-full bg-primary" style={{ width: d.jobs_total ? `${(n / d.jobs_total) * 100}%` : 0 }} />
                  </div>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Quick actions" />
          <CardBody className="grid gap-2">
            <Button variant="secondary" className="justify-start" asChild>
              <Link to="/jobs/new">
                <Briefcase /> Import a job description
              </Link>
            </Button>
            <Button variant="secondary" className="justify-start" asChild>
              <Link to="/tailor">
                <FilePlus2 /> Tailor a resume
              </Link>
            </Button>
            <Button variant="secondary" className="justify-start" asChild>
              <Link to="/skills">Update skills and evidence</Link>
            </Button>
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Recently updated jobs" actions={<Link className="text-sm text-primary hover:underline" to="/jobs">All jobs</Link>} />
          {d.recent_jobs.length === 0 ? (
            <CardBody className="text-sm text-muted-foreground">No jobs yet.</CardBody>
          ) : (
            <ul className="divide-y">
              {d.recent_jobs.map((j) => (
                <li key={j.id}>
                  <Link to={`/jobs/${j.id}`} className="flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-surface-muted/60">
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">{j.display_name}</span>
                      <span className="text-xs text-muted-foreground">Updated {formatDateTime(j.updated_at)}</span>
                    </span>
                    <JobStatusBadge status={j.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card>
          <CardHeader title="Recent resume versions" actions={<Link className="text-sm text-primary hover:underline" to="/resumes">All versions</Link>} />
          {d.recent_versions.length === 0 ? (
            <CardBody className="text-sm text-muted-foreground">No resume versions yet.</CardBody>
          ) : (
            <ul className="divide-y">
              {d.recent_versions.map((v) => (
                <li key={v.id}>
                  <Link to={`/resumes/${v.id}`} className="flex items-center justify-between gap-3 px-4 py-2.5 hover:bg-surface-muted/60">
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">{v.job_display_name}</span>
                      <span className="text-xs text-muted-foreground">
                        {v.id} · {formatDateTime(v.created_at)}
                      </span>
                    </span>
                    <VersionStateBadge approved={Boolean(v.approved_at)} exported={v.exported} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
