import { zodResolver } from "@hookform/resolvers/zod";
import { Pencil, Plus, Search, Tags, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { useDraft } from "@/hooks/useDraft";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Select } from "@/components/ui/form-controls";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Alert, Badge, Card } from "@/components/ui/surface";
import { Table, TBody, Td, Th, THead, Tr } from "@/components/ui/table";
import { EvidenceChips } from "@/components/shared/EvidenceChips";
import { PageHeader } from "@/components/shared/PageHeader";
import { EmptyState, QueryView } from "@/components/shared/states";
import { useUnsavedChanges } from "@/components/shared/UnsavedChanges";
import { humanize, splitList } from "@/lib/format";
import { useProfile } from "@/services/api/queries";
import { SKILL_CATEGORIES, type EvidenceItem, type MasterProfile, type Skill, type SkillCategory } from "@/services/api/types";
import { skillSchema, type SkillValues } from "@/features/profile/schemas";
import { tempId } from "@/features/profile/SectionEditor";
import { useProfileSave } from "@/features/profile/useProfileSave";

export function SkillsPage() {
  const profile = useProfile();
  return (
    <>
      <PageHeader
        title="Skills library"
        description="Your skills, linked to the evidence that demonstrates them. Aliases are exact alternative names (k8s for Kubernetes), not related concepts."
      />
      <QueryView query={profile}>
        {(v) =>
          v.profile ? (
            <SkillsEditor profile={v.profile} evidence={v.evidence} />
          ) : (
            <EmptyState
              icon={Tags}
              title="Create a master profile first"
              action={
                <Button asChild>
                  <Link to="/profile">Master profile</Link>
                </Button>
              }
            >
              Skills live in your master profile and link to its experience, projects and bullets.
            </EmptyState>
          )
        }
      </QueryView>
    </>
  );
}

function SkillsEditor({ profile, evidence }: { profile: MasterProfile; evidence: EvidenceItem[] }) {
  const { draft, setDraft, dirty, reset } = useDraft<Skill[]>(profile.skills);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<SkillCategory | "all">("all");
  const [editing, setEditing] = useState<Skill | "new" | null>(null);
  const { saveSection, saving } = useProfileSave(profile);
  const unsaved = useUnsavedChanges(dirty);

  const shown = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return draft.filter(
      (s) =>
        (category === "all" || s.category === category) &&
        (!needle || [s.name, ...s.aliases].some((x) => x.toLowerCase().includes(needle))),
    );
  }, [draft, search, category]);

  const withoutEvidence = draft.filter((s) => s.evidence_ids.length === 0).length;

  return (
    <div className="space-y-4">
      {unsaved.prompt}
      {withoutEvidence > 0 && (
        <Alert tone="info">
          {withoutEvidence} skill(s) have no linked evidence. Matching still finds skills mentioned in your entries, but linking makes the
          evidence explicit and traceable.
        </Alert>
      )}
      <Card>
        <div className="flex flex-wrap items-center gap-2 border-b p-3">
          <div className="relative min-w-48 flex-1 sm:max-w-xs">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" aria-hidden />
            <Input className="pl-8" placeholder="Search skills and aliases" aria-label="Search skills" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <Select aria-label="Category" className="w-auto" value={category} onChange={(e) => setCategory(e.target.value as SkillCategory | "all")}>
            <option value="all">All categories</option>
            {SKILL_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {humanize(c)}
              </option>
            ))}
          </Select>
          <Button className="ml-auto" size="sm" onClick={() => setEditing("new")}>
            <Plus /> Add skill
          </Button>
        </div>
        {draft.length === 0 ? (
          <div className="p-4">
            <EmptyState icon={Tags} title="No skills yet" className="border-0">
              Add skills you can demonstrate, and link each to the entries that show it.
            </EmptyState>
          </div>
        ) : shown.length === 0 ? (
          <p className="p-6 text-center text-sm text-muted-foreground">No skills match these filters.</p>
        ) : (
          <Table>
            <THead>
              <tr>
                <Th>Skill</Th>
                <Th>Category</Th>
                <Th className="hidden md:table-cell">Aliases</Th>
                <Th className="hidden lg:table-cell">Evidence</Th>
                <Th className="sr-only">Actions</Th>
              </tr>
            </THead>
            <TBody>
              {shown.map((s) => {
                const isNew = s.id.startsWith("tmp-");
                const changed = !isNew && JSON.stringify(profile.skills.find((x) => x.id === s.id)) !== JSON.stringify(s);
                return (
                  <Tr key={s.id}>
                    <Td>
                      <p className="font-medium">{s.name}</p>
                      <p className="font-mono text-xs text-muted-foreground">{isNew ? "new · unsaved" : changed ? `${s.id} · edited` : s.id}</p>
                    </Td>
                    <Td>
                      <Badge tone="outline">{humanize(s.category)}</Badge>
                    </Td>
                    <Td className="hidden text-muted-foreground md:table-cell">{s.aliases.join(", ") || "—"}</Td>
                    <Td className="hidden max-w-96 lg:table-cell">
                      <EvidenceChips ids={s.evidence_ids} evidence={evidence} empty="Not linked" />
                    </Td>
                    <Td className="whitespace-nowrap text-right">
                      <Button variant="ghost" size="icon-sm" aria-label={`Edit ${s.name}`} onClick={() => setEditing(s)}>
                        <Pencil />
                      </Button>
                      <Button variant="ghost" size="icon-sm" aria-label={`Remove ${s.name}`} onClick={() => setDraft((d) => d.filter((x) => x.id !== s.id))}>
                        <Trash2 />
                      </Button>
                    </Td>
                  </Tr>
                );
              })}
            </TBody>
          </Table>
        )}
        {dirty && (
          <div className="sticky bottom-0 flex flex-wrap items-center justify-between gap-2 border-t bg-surface/95 px-4 py-3 backdrop-blur">
            <p className="text-sm text-muted-foreground">Unsaved changes to your skills.</p>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={reset} disabled={saving}>
                Discard
              </Button>
              <Button loading={saving} onClick={() => saveSection({ skills: draft })}>
                Save skills
              </Button>
            </div>
          </div>
        )}
      </Card>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        {editing !== null && (
          <DialogContent variant="sheet-right" title={editing === "new" ? "Add skill" : `Edit ${editing.name}`}>
            <SkillForm
              initial={editing === "new" ? undefined : editing}
              others={draft.filter((s) => editing === "new" || s.id !== editing.id)}
              evidence={evidence}
              onCancel={() => setEditing(null)}
              onSubmit={(skill) => {
                setDraft((d) => (d.some((x) => x.id === skill.id) ? d.map((x) => (x.id === skill.id ? skill : x)) : [...d, skill]));
                setEditing(null);
              }}
            />
          </DialogContent>
        )}
      </Dialog>
    </div>
  );
}

export function SkillForm({
  initial,
  others,
  evidence,
  onSubmit,
  onCancel,
}: {
  initial?: Skill;
  others: Skill[];
  evidence: EvidenceItem[];
  onSubmit: (s: Skill) => void;
  onCancel: () => void;
}) {
  const [filter, setFilter] = useState("");
  const { register, control, handleSubmit, formState, setValue, setError } = useForm<SkillValues>({
    resolver: zodResolver(skillSchema),
    defaultValues: {
      name: initial?.name ?? "",
      category: initial?.category ?? "other",
      aliases: initial?.aliases.join(", ") ?? "",
      evidence_ids: initial?.evidence_ids.filter((id) => evidence.some((e) => e.id === id)) ?? [],
    },
  });
  const selected = useWatch({ control, name: "evidence_ids" });
  const shown = evidence.filter((e) => e.label.toLowerCase().includes(filter.trim().toLowerCase()));

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={handleSubmit((v) => {
        const taken = new Set(others.map((s) => s.name.trim().toLowerCase()));
        if (taken.has(v.name.trim().toLowerCase())) {
          setError("name", { message: "You already have a skill with this name." });
          return;
        }
        onSubmit({
          ...(initial ?? { id: tempId() }),
          name: v.name.trim(),
          category: v.category,
          aliases: splitList(v.aliases),
          evidence_ids: v.evidence_ids,
        });
      })}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Skill" required error={formState.errors.name?.message}>
          {(p) => <Input {...p} {...register("name")} />}
        </Field>
        <Field label="Category">
          {(p) => (
            <Select {...p} {...register("category")}>
              {SKILL_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {humanize(c)}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      <Field label="Aliases" hint="Exact alternative names only, comma-separated. A related tool is not an alias.">
        {(p) => <Input {...p} placeholder="k8s" {...register("aliases")} />}
      </Field>
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Evidence ({selected.length} linked)</legend>
        <p className="text-xs text-muted-foreground">Link the experience, projects or bullets that demonstrate this skill.</p>
        <Input placeholder="Filter evidence" aria-label="Filter evidence" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <div className="max-h-72 space-y-1.5 overflow-y-auto rounded-md border p-2">
          {shown.map((e) => (
            <Checkbox
              key={e.id}
              label={<span className="font-normal">{e.label}</span>}
              description={`${e.kind} · ${e.id}`}
              checked={selected.includes(e.id)}
              onChange={(ev) =>
                setValue("evidence_ids", ev.target.checked ? [...selected, e.id] : selected.filter((x) => x !== e.id), { shouldDirty: true })
              }
            />
          ))}
          {shown.length === 0 && <p className="p-2 text-sm text-muted-foreground">No evidence matches.</p>}
        </div>
      </fieldset>
      <div className="sticky bottom-0 -mx-5 -mb-4 flex justify-end gap-2 border-t bg-surface px-5 py-3">
        <Button variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit">{initial ? "Update draft" : "Add to draft"}</Button>
      </div>
    </form>
  );
}
