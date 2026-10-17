import { Link } from "react-router";
import { Table, TBody, Td, Th, THead, Tr } from "@/components/ui/table";
import { VersionStateBadge } from "@/components/shared/badges";
import { formatDateTime } from "@/lib/format";
import type { VersionSummary } from "@/services/api/types";

export function generatorLabel(generator: string): string {
  if (generator === "deterministic") return "From profile";
  if (generator === "user_edit") return "Your edit";
  if (generator.startsWith("llm:")) return `AI wording (${generator.slice(4)})`;
  return generator;
}

export function VersionTable({ versions, showJob }: { versions: (VersionSummary & { job_display_name?: string })[]; showJob?: boolean }) {
  return (
    <Table>
      <THead>
        <tr>
          <Th>Version</Th>
          {showJob && <Th>Job</Th>}
          <Th className="hidden sm:table-cell">Source</Th>
          <Th>State</Th>
          <Th className="hidden md:table-cell">Created</Th>
        </tr>
      </THead>
      <TBody>
        {versions.map((v) => (
          <Tr key={v.id}>
            <Td>
              <Link to={`/resumes/${v.id}`} className="font-mono text-xs font-medium text-primary hover:underline">
                {v.id}
              </Link>
              {v.parent_id && <p className="text-xs text-muted-foreground">edited from {v.parent_id}</p>}
            </Td>
            {showJob && (
              <Td>
                <Link to={`/jobs/${v.job_id}`} className="hover:underline">
                  {v.job_display_name}
                </Link>
              </Td>
            )}
            <Td className="hidden text-muted-foreground sm:table-cell">
              {generatorLabel(v.generator)} · {v.target_pages}p
            </Td>
            <Td>
              <VersionStateBadge approved={Boolean(v.approved_at)} exported={v.exported} />
            </Td>
            <Td className="hidden whitespace-nowrap text-muted-foreground md:table-cell">{formatDateTime(v.created_at)}</Td>
          </Tr>
        ))}
      </TBody>
    </Table>
  );
}
