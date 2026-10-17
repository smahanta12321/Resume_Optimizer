import { Briefcase, Inbox, Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form-controls";
import { Alert, Badge, Card } from "@/components/ui/surface";
import { Table, TBody, Td, Th, THead, Tr } from "@/components/ui/table";
import { AnalysisBadge, JobStatusBadge } from "@/components/shared/badges";
import { PageHeader } from "@/components/shared/PageHeader";
import { EmptyState, QueryView } from "@/components/shared/states";
import { formatDate } from "@/lib/format";
import { useCaptures, useJobs } from "@/services/api/queries";
import type { JobSummary } from "@/services/api/types";

export function JobsPage() {
  const jobs = useJobs();
  const captures = useCaptures();
  const [search, setSearch] = useState("");
  const navigate = useNavigate();

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return jobs.data ?? [];
    return (jobs.data ?? []).filter((j) =>
      [j.job.title, j.job.company, j.job.location].join(" ").toLowerCase().includes(needle),
    );
  }, [jobs.data, search]);

  return (
    <>
      <PageHeader
        title="Job descriptions"
        description="Imported postings, their reviewed requirements, and how your evidence matches them."
        actions={
          <Button asChild>
            <Link to="/jobs/new">
              <Plus /> Import a job
            </Link>
          </Button>
        }
      />
      {(captures.data?.length ?? 0) > 0 && (
        <Alert
          tone="info"
          className="mb-4"
          title={`${captures.data?.length} capture(s) from the browser extension waiting for review`}
          action={
            <Button size="sm" variant="secondary" asChild>
              <Link to="/jobs/new?source=inbox">
                <Inbox /> Review
              </Link>
            </Button>
          }
        />
      )}
      <QueryView query={jobs}>
        {(data) =>
          data.length === 0 ? (
            <EmptyState
              icon={Briefcase}
              title="No job descriptions yet"
              action={
                <Button asChild>
                  <Link to="/jobs/new">
                    <Plus /> Import your first job
                  </Link>
                </Button>
              }
            >
              Paste a posting, upload a file, or try a URL. You review everything before it's saved.
            </EmptyState>
          ) : (
            <Card>
              <div className="border-b p-3">
                <div className="relative max-w-sm">
                  <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" aria-hidden />
                  <Input
                    className="pl-8"
                    placeholder="Search title, company, location"
                    aria-label="Search jobs"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
              </div>
              {filtered.length === 0 ? (
                <p className="p-6 text-center text-sm text-muted-foreground">No jobs match “{search}”.</p>
              ) : (
                <Table>
                  <THead>
                    <tr>
                      <Th>Role</Th>
                      <Th className="hidden md:table-cell">Progress</Th>
                      <Th>Status</Th>
                      <Th className="hidden sm:table-cell">Imported</Th>
                    </tr>
                  </THead>
                  <TBody>
                    {filtered.map((s) => (
                      <JobRow key={s.job.id} summary={s} onOpen={() => navigate(`/jobs/${s.job.id}`)} />
                    ))}
                  </TBody>
                </Table>
              )}
            </Card>
          )
        }
      </QueryView>
    </>
  );
}

function JobRow({ summary: s, onOpen }: { summary: JobSummary; onOpen: () => void }) {
  return (
    <Tr className="cursor-pointer" onClick={onOpen}>
      <Td>
        <Link to={`/jobs/${s.job.id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>
          {s.display_name}
        </Link>
        <p className="text-xs text-muted-foreground">{[s.job.location, s.job.source_platform !== "other" && s.job.source_platform].filter(Boolean).join(" · ") || "—"}</p>
      </Td>
      <Td className="hidden md:table-cell">
        <div className="flex flex-wrap gap-1">
          <AnalysisBadge state={s.analysis_state} />
          {s.has_match_report && <Badge tone="primary">Matched</Badge>}
          {s.versions > 0 && (
            <Badge tone="outline">
              {s.approved_versions}/{s.versions} resumes approved
            </Badge>
          )}
        </div>
      </Td>
      <Td>
        <JobStatusBadge status={s.job.status} />
      </Td>
      <Td className="hidden whitespace-nowrap text-muted-foreground sm:table-cell">{formatDate(s.job.imported_at)}</Td>
    </Tr>
  );
}
