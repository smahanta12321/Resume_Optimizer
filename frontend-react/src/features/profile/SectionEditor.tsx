import { ArrowDown, ArrowUp, Pencil, Plus, Trash2, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useDraft } from "@/hooks/useDraft";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Card, CardHeader } from "@/components/ui/surface";
import { EmptyState } from "@/components/shared/states";
import { useUnsavedChanges } from "@/components/shared/UnsavedChanges";

/** New entries carry a temporary id so lists can key them; useProfileSave strips it so the API assigns a real one. */
export const TEMP_PREFIX = "tmp-";
export const tempId = () => `${TEMP_PREFIX}${Math.random().toString(36).slice(2, 10)}`;

/** Deep copy without temporary ids (entries and bullets alike). */
export function withoutTempIds<T>(value: T): T {
  return JSON.parse(JSON.stringify(value), (key, v) => (key === "id" && typeof v === "string" && v.startsWith(TEMP_PREFIX) ? undefined : v)) as T;
}

export interface ItemSummary {
  title: ReactNode;
  subtitle?: ReactNode;
  meta?: ReactNode;
}

interface Props<T extends { id: string }> {
  title: string;
  description?: string;
  icon: LucideIcon;
  noun: string;
  items: T[];
  summarize: (item: T) => ItemSummary;
  renderForm: (props: { initial?: T; onSubmit: (item: T) => void; onCancel: () => void }) => ReactNode;
  onSave: (items: T[], done: () => void) => void;
  saving: boolean;
}

/**
 * Edit a repeated profile section as a draft: add, edit, reorder and delete entries, then save them
 * together as one new profile version.
 */
export function SectionEditor<T extends { id: string }>({ title, description, icon, noun, items, summarize, renderForm, onSave, saving }: Props<T>) {
  const { draft, setDraft, dirty, reset } = useDraft<T[]>(items);
  const [editing, setEditing] = useState<T | "new" | null>(null);
  const unsaved = useUnsavedChanges(dirty);

  const move = (i: number, by: number) =>
    setDraft((d) => {
      const next = [...d];
      const [it] = next.splice(i, 1);
      if (it) next.splice(i + by, 0, it);
      return next;
    });

  const submit = (item: T) => {
    setDraft((d) => (d.some((x) => x.id === item.id) ? d.map((x) => (x.id === item.id ? item : x)) : [...d, item]));
    setEditing(null);
  };

  return (
    <Card>
      {unsaved.prompt}
      <CardHeader
        title={title}
        description={description}
        actions={
          <Button size="sm" variant="secondary" onClick={() => setEditing("new")}>
            <Plus /> Add {noun}
          </Button>
        }
      />
      {draft.length === 0 ? (
        <div className="p-4">
          <EmptyState icon={icon} title={`No ${noun} entries yet`} className="border-0 py-6">
            Add only what you can verify. Resumes may only use facts recorded here.
          </EmptyState>
        </div>
      ) : (
        <ol className="divide-y">
          {draft.map((item, i) => {
            const s = summarize(item);
            const isNew = item.id.startsWith(TEMP_PREFIX);
            const changed = !isNew && JSON.stringify(items.find((x) => x.id === item.id)) !== JSON.stringify(item);
            return (
              <li key={item.id} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">
                    {s.title}
                    {(isNew || changed) && <span className="ml-2 text-xs font-normal text-warning">{isNew ? "new · unsaved" : "edited · unsaved"}</span>}
                  </p>
                  {s.subtitle && <p className="text-sm text-muted-foreground">{s.subtitle}</p>}
                  {s.meta && <div className="mt-1 text-xs text-muted-foreground">{s.meta}</div>}
                </div>
                <div className="flex shrink-0 items-center gap-0.5">
                  <Button variant="ghost" size="icon-sm" aria-label={`Move ${noun} up`} disabled={i === 0} onClick={() => move(i, -1)}>
                    <ArrowUp />
                  </Button>
                  <Button variant="ghost" size="icon-sm" aria-label={`Move ${noun} down`} disabled={i === draft.length - 1} onClick={() => move(i, 1)}>
                    <ArrowDown />
                  </Button>
                  <Button variant="ghost" size="icon-sm" aria-label={`Edit ${noun}`} onClick={() => setEditing(item)}>
                    <Pencil />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Remove ${noun}`}
                    onClick={() => setDraft((d) => d.filter((x) => x.id !== item.id))}
                  >
                    <Trash2 />
                  </Button>
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {dirty && (
        <div className="sticky bottom-0 flex flex-wrap items-center justify-between gap-2 border-t bg-surface/95 px-4 py-3 backdrop-blur">
          <p className="text-sm text-muted-foreground">Unsaved changes. Removed entries also lose their skill evidence links.</p>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={reset} disabled={saving}>
              Discard
            </Button>
            <Button onClick={() => onSave(draft, () => undefined)} loading={saving}>
              Save {title.toLowerCase()}
            </Button>
          </div>
        </div>
      )}
      <Dialog open={editing !== null} onOpenChange={(open) => !open && setEditing(null)}>
        {editing !== null && (
          <DialogContent variant="sheet-right" title={editing === "new" ? `Add ${noun}` : `Edit ${noun}`}>
            {renderForm({ initial: editing === "new" ? undefined : editing, onSubmit: submit, onCancel: () => setEditing(null) })}
          </DialogContent>
        )}
      </Dialog>
    </Card>
  );
}
