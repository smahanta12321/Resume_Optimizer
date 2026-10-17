import { useNavigate, useParams } from "react-router";
import { PageHeader } from "@/components/shared/PageHeader";
import { useResume } from "@/services/api/queries";
import { VersionWorkspace } from "./VersionWorkspace";

export function ResumeVersionPage() {
  const { versionId = "" } = useParams();
  const navigate = useNavigate();
  const detail = useResume(versionId);
  const jobName = detail.data ? [detail.data.job.title || "Untitled role", detail.data.job.company].filter(Boolean).join(" @ ") : "Resume";
  return (
    <>
      <PageHeader
        title={`Resume for ${jobName}`}
        crumbs={[
          { label: "Resume versions", to: "/resumes" },
          ...(detail.data ? [{ label: jobName, to: `/jobs/${detail.data.job.id}?tab=resumes` }] : []),
          { label: versionId },
        ]}
      />
      <VersionWorkspace versionId={versionId} onNewVersion={(id) => navigate(`/resumes/${id}?view=approve`)} />
    </>
  );
}
