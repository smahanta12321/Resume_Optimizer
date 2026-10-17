import { FilePlus2, FileText } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/form-controls";
import { Card } from "@/components/ui/surface";
import { PageHeader } from "@/components/shared/PageHeader";
import { EmptyState, QueryView } from "@/components/shared/states";
import { useAllResumes } from "@/services/api/queries";
import { VersionTable } from "./VersionTable";

type StateFilter = "all" | "draft" | "approved" | "exported";

export function ResumesPage() {
  const resumes = useAllResumes();
  const [state, setState] = useState<StateFilter>("all");
  const shown = useMemo(
    () =>
      (resumes.data ?? []).filter((v) =>
        state === "all" ? true : state === "draft" ? !v.approved_at : state === "approved" ? Boolean(v.approved_at) && !v.exported : v.exported,
      ),
    [resumes.data, state],
  );

  return (
    <>
      <PageHeader
        title="Resume versions"
        description="Every tailored version is immutable. Edits create a new version, and only approved versions can be exported."
        actions={
          <Button asChild>
            <Link to="/tailor">
              <FilePlus2 /> Tailor a resume
            </Link>
          </Button>
        }
      />
      <QueryView query={resumes}>
        {(all) =>
          all.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No resume versions yet"
              action={
                <Button asChild>
                  <Link to="/tailor">Start tailoring</Link>
                </Button>
              }
            >
              Pick a job, confirm its requirements, match them against your profile, and generate a draft from your evidence.
            </EmptyState>
          ) : (
            <Card>
              <div className="flex items-center justify-between gap-3 border-b p-3">
                <p className="text-sm text-muted-foreground">
                  {shown.length} of {all.length} version(s)
                </p>
                <Select aria-label="Filter by state" className="w-auto" value={state} onChange={(e) => setState(e.target.value as StateFilter)}>
                  <option value="all">All states</option>
                  <option value="draft">Drafts</option>
                  <option value="approved">Approved, not exported</option>
                  <option value="exported">Exported</option>
                </Select>
              </div>
              {shown.length === 0 ? (
                <p className="p-6 text-center text-sm text-muted-foreground">No versions in this state.</p>
              ) : (
                <VersionTable versions={shown} showJob />
              )}
            </Card>
          )
        }
      </QueryView>
    </>
  );
}
