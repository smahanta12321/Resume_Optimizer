import type { EvidenceItem } from "@/services/api/types";

/** Evidence IDs shown with their master-profile labels, so every claim is traceable. */
export function EvidenceChips({ ids, evidence, empty = "No evidence" }: { ids: string[]; evidence?: EvidenceItem[]; empty?: string }) {
  if (ids.length === 0) return <span className="text-xs text-muted-foreground">{empty}</span>;
  const labels = new Map((evidence ?? []).map((e) => [e.id, e.label]));
  return (
    <ul className="flex flex-wrap gap-1">
      {ids.map((id) => {
        const label = labels.get(id);
        return (
          <li
            key={id}
            title={id}
            className="max-w-full truncate rounded border bg-surface-muted/60 px-1.5 py-0.5 text-xs text-muted-foreground"
          >
            {label ?? (evidence ? `(removed) ${id}` : id)}
          </li>
        );
      })}
    </ul>
  );
}
