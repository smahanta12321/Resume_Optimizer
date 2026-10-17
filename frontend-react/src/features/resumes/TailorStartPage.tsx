import { Briefcase, ChevronRight, Plus } from "lucide-react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { Badge, Card } from "@/components/ui/surface";
import { AnalysisBadge } from "@/components/shared/badges";
import { PageHeader } from "@/components/shared/PageHeader";
import { EmptyState, QueryView } from "@/components/shared/states";
import { formatDate } from "@/lib/format";
import { useJobs } from "@/services/api/queries";

export function TailorStartPage() {
  const jobs = useJobs();
  return (
    <>
      <PageHeader
        title="Tailor a resume"
        description="Step 1: choose the job description to tailor for. The next steps confirm its requirements, match them to your evidence, and build a draft for your review."
        actions={
          <Button variant="secondary" asChild>
            <Link to="/jobs/new">
              <Plus /> Import a new job
            </Link>
          </Button>
        }
      />
      <QueryView query={jobs}>
        {(list) =>
          list.length === 0 ? (
            <EmptyState
              icon={Briefcase}
              title="Import a job description first"
              action={
                <Button asChild>
                  <Link to="/jobs/new">Import a job</Link>
                </Button>
              }
            />
          ) : (
            <Card>
              <ul className="divide-y">
                {list.map((s) => (
                  <li key={s.job.id}>
                    <Link
                      to={`/jobs/${s.job.id}/tailor`}
                      className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-surface-muted/60 focus-visible:bg-surface-muted/60"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium">{s.display_name}</p>
                        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                          <AnalysisBadge state={s.analysis_state} />
                          {s.has_match_report && <Badge tone="primary">Matched</Badge>}
                          {s.versions > 0 && <Badge tone="outline">{s.versions} version(s)</Badge>}
                          <span>Imported {formatDate(s.job.imported_at)}</span>
                        </div>
                      </div>
                      <ChevronRight className="size-4 text-muted-foreground" aria-hidden />
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )
        }
      </QueryView>
    </>
  );
}
