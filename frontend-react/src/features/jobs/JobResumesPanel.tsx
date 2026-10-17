import { FilePlus2, FileText } from "lucide-react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/surface";
import { EmptyState, QueryView } from "@/components/shared/states";
import { VersionTable } from "@/features/resumes/VersionTable";
import { useJobResumes } from "@/services/api/queries";

export function JobResumesPanel({ jobId }: { jobId: string }) {
  const versions = useJobResumes(jobId);
  return (
    <QueryView query={versions}>
      {(list) =>
        list.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="No resume versions for this job"
            action={
              <Button asChild>
                <Link to={`/jobs/${jobId}/tailor`}>
                  <FilePlus2 /> Tailor a resume
                </Link>
              </Button>
            }
          >
            Generate a draft from your verified evidence once the requirements are confirmed and matched.
          </EmptyState>
        ) : (
          <Card>
            <VersionTable versions={list} />
          </Card>
        )
      }
    </QueryView>
  );
}
