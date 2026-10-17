import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowDown, ArrowUp, Copy, Layers, Pencil, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { Link } from "react-router";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form-controls";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Alert, Badge, Card, CardBody } from "@/components/ui/surface";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { PageHeader } from "@/components/shared/PageHeader";
import { EmptyState, QueryView } from "@/components/shared/states";
import { cn } from "@/lib/utils";
import { errorMessage } from "@/services/api/client";
import { api } from "@/services/api/endpoints";
import { useProfile, useRoleAction, useRoles } from "@/services/api/queries";
import type { MasterProfile, RoleProfile, RoleProfileIn, RoleProfileView } from "@/services/api/types";

interface Option {
  id: string;
  label: string;
  indent?: boolean;
}

function evidenceOptions(p: MasterProfile): Option[] {
  return [
    ...p.experience.flatMap((e) => [
      { id: e.id, label: `${e.title} @ ${e.employer}` },
      ...e.bullets.map((b) => ({ id: b.id, label: b.text, indent: true })),
    ]),
    ...p.projects.flatMap((x) => [{ id: x.id, label: `Project: ${x.name}` }, ...x.bullets.map((b) => ({ id: b.id, label: b.text, indent: true }))]),
  ];
}

export function RolesPage() {
  const roles = useRoles();
  const profile = useProfile();
  const [editing, setEditing] = useState<RoleProfile | "new" | null>(null);

  return (
    <>
      <PageHeader
        title="Role profiles"
        description="A role profile is a named selection and ordering of your verified evidence, used as a starting point when tailoring. It never adds facts."
        actions={
          profile.data?.profile && (
            <Button onClick={() => setEditing("new")}>
              <Plus /> New role profile
            </Button>
          )
        }
      />
      <QueryView query={profile}>
        {(pv) =>
          !pv.profile ? (
            <EmptyState
              icon={Layers}
              title="Create a master profile first"
              action={
                <Button asChild>
                  <Link to="/profile">Master profile</Link>
                </Button>
              }
            />
          ) : (
            <QueryView query={roles}>
              {(list) =>
                list.length === 0 ? (
                  <EmptyState
                    icon={Layers}
                    title="No role profiles yet"
                    action={
                      <Button onClick={() => setEditing("new")}>
                        <Plus /> Create one
                      </Button>
                    }
                  >
                    For example: “ML Engineer” emphasising your model-serving work, or “Data Engineer” leading with pipelines.
                  </EmptyState>
                ) : (
                  <div className="grid gap-3 md:grid-cols-2">
                    {list.map((r) => (
                      <RoleCard key={r.role.id} view={r} profile={pv.profile as MasterProfile} onEdit={() => setEditing(r.role)} />
                    ))}
                  </div>
                )
              }
            </QueryView>
          )
        }
      </QueryView>
      {profile.data?.profile && (
        <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
          {editing !== null && (
            <DialogContent variant="sheet-right" title={editing === "new" ? "New role profile" : `Edit ${editing.name}`}>
              <RoleForm initial={editing === "new" ? undefined : editing} profile={profile.data.profile} onDone={() => setEditing(null)} />
            </DialogContent>
          )}
        </Dialog>
      )}
    </>
  );
}

function RoleCard({ view, profile, onEdit }: { view: RoleProfileView; profile: MasterProfile; onEdit: () => void }) {
  const { role, dangling } = view;
  const [dupOpen, setDupOpen] = useState(false);
  const [dupName, setDupName] = useState(`${role.name} (copy)`);
  const [delOpen, setDelOpen] = useState(false);
  const duplicate = useRoleAction(() => api.roles.duplicate(role.id, dupName));
  const remove = useRoleAction(() => api.roles.remove(role.id));
  const skills = new Map(profile.skills.map((s) => [s.id, s.name]));
  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="font-semibold">{role.name}</p>
            {role.target_role && <p className="text-sm text-muted-foreground">Target: {role.target_role}</p>}
          </div>
          <div className="flex">
            <Button variant="ghost" size="icon-sm" aria-label={`Edit ${role.name}`} onClick={onEdit}>
              <Pencil />
            </Button>
            <Button variant="ghost" size="icon-sm" aria-label={`Duplicate ${role.name}`} onClick={() => setDupOpen(true)}>
              <Copy />
            </Button>
            <Button variant="ghost" size="icon-sm" aria-label={`Delete ${role.name}`} onClick={() => setDelOpen(true)}>
              <Trash2 />
            </Button>
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Badge tone="outline">{role.evidence_ids.length} evidence</Badge>
          <Badge tone="outline">{role.skill_ids.length} skills</Badge>
          <Badge tone="outline">{role.target_pages}-page target</Badge>
        </div>
        {role.skill_ids.length > 0 && (
          <p className="line-clamp-2 text-xs text-muted-foreground">{role.skill_ids.map((id) => skills.get(id) ?? id).join(", ")}</p>
        )}
        {dangling.length > 0 && (
          <Alert tone="warning">Some selected items were removed from the master profile. Edit and save to drop them: {dangling.join(", ")}</Alert>
        )}
      </CardBody>
      <ConfirmDialog
        open={dupOpen}
        onOpenChange={setDupOpen}
        title={`Duplicate ${role.name}`}
        confirmLabel="Duplicate"
        loading={duplicate.isPending}
        onConfirm={() =>
          duplicate.mutate(undefined, {
            onSuccess: () => {
              setDupOpen(false);
              toast.success(`Duplicated as ${dupName}.`);
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      >
        <Field label="Name for the copy">{(p) => <Input {...p} value={dupName} onChange={(e) => setDupName(e.target.value)} />}</Field>
      </ConfirmDialog>
      <ConfirmDialog
        open={delOpen}
        onOpenChange={setDelOpen}
        title={`Delete ${role.name}?`}
        confirmLabel="Delete"
        destructive
        loading={remove.isPending}
        onConfirm={() =>
          remove.mutate(undefined, {
            onSuccess: () => {
              setDelOpen(false);
              toast.success(`Deleted ${role.name}.`);
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      >
        <p>Existing resume versions are not affected.</p>
      </ConfirmDialog>
    </Card>
  );
}

const roleSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(100),
  target_role: z.string().trim().max(200),
  evidence_ids: z.array(z.string()),
  skill_ids: z.array(z.string()),
  target_pages: z.union([z.literal(1), z.literal(2)]),
});
type RoleValues = z.infer<typeof roleSchema>;

function RoleForm({ initial, profile, onDone }: { initial?: RoleProfile; profile: MasterProfile; onDone: () => void }) {
  const evidence = evidenceOptions(profile);
  const skills: Option[] = profile.skills.map((s) => ({ id: s.id, label: s.name }));
  const known = new Set([...evidence, ...skills].map((o) => o.id));
  const { register, control, handleSubmit, formState } = useForm<RoleValues>({
    resolver: zodResolver(roleSchema),
    defaultValues: {
      name: initial?.name ?? "",
      target_role: initial?.target_role ?? "",
      // References to removed items are dropped here, as Streamlit does on save.
      evidence_ids: initial?.evidence_ids.filter((id) => known.has(id)) ?? [],
      skill_ids: initial?.skill_ids.filter((id) => known.has(id)) ?? [],
      target_pages: initial?.target_pages ?? 1,
    },
  });
  const save = useRoleAction((body: RoleProfileIn) => (initial ? api.roles.update(initial.id, body) : api.roles.create(body)));

  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={handleSubmit((v) =>
        save.mutate(v, {
          onSuccess: () => {
            toast.success(initial ? `Saved ${v.name}.` : `Created ${v.name}.`);
            onDone();
          },
          onError: (e) => toast.error(errorMessage(e)),
        }),
      )}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name" required error={formState.errors.name?.message}>
          {(p) => <Input {...p} placeholder="e.g. ML Engineer" {...register("name")} />}
        </Field>
        <Field label="Target job title">{(p) => <Input {...p} {...register("target_role")} />}</Field>
      </div>
      <Controller
        control={control}
        name="target_pages"
        render={({ field }) => (
          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">Target length</legend>
            <div className="flex gap-2">
              {([1, 2] as const).map((n) => (
                <label key={n} className={cn("flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-sm", field.value === n && "border-primary bg-primary-soft")}>
                  <input type="radio" checked={field.value === n} onChange={() => field.onChange(n)} className="accent-[var(--primary)]" />
                  {n} page{n > 1 ? "s" : ""}
                </label>
              ))}
            </div>
          </fieldset>
        )}
      />
      <Controller
        control={control}
        name="evidence_ids"
        render={({ field }) => <OrderedPicker label="Evidence to include, in order" options={evidence} value={field.value} onChange={field.onChange} />}
      />
      <Controller
        control={control}
        name="skill_ids"
        render={({ field }) => <OrderedPicker label="Skills to emphasise, in order" options={skills} value={field.value} onChange={field.onChange} />}
      />
      <div className="sticky bottom-0 -mx-5 -mb-4 flex justify-end gap-2 border-t bg-surface px-5 py-3">
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" loading={save.isPending}>
          {initial ? "Save" : "Create"}
        </Button>
      </div>
    </form>
  );
}

/** Choose items and set their order (selection order is the default ordering in drafts). */
function OrderedPicker({ label, options, value, onChange }: { label: string; options: Option[]; value: string[]; onChange: (v: string[]) => void }) {
  const [filter, setFilter] = useState("");
  const byId = new Map(options.map((o) => [o.id, o]));
  const available = options.filter((o) => !value.includes(o.id) && o.label.toLowerCase().includes(filter.trim().toLowerCase()));
  const move = (i: number, by: number) => {
    const next = [...value];
    const [it] = next.splice(i, 1);
    if (it) next.splice(i + by, 0, it);
    onChange(next);
  };
  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium">
        {label} ({value.length})
      </legend>
      {value.length > 0 && (
        <ol className="divide-y rounded-md border">
          {value.map((id, i) => (
            <li key={id} className="flex items-center gap-2 px-2 py-1.5 text-sm">
              <span className="w-5 text-right text-xs tabular-nums text-muted-foreground">{i + 1}</span>
              <span className="min-w-0 flex-1 truncate">{byId.get(id)?.label ?? id}</span>
              <Button variant="ghost" size="icon-sm" aria-label="Move up" disabled={i === 0} onClick={() => move(i, -1)}>
                <ArrowUp />
              </Button>
              <Button variant="ghost" size="icon-sm" aria-label="Move down" disabled={i === value.length - 1} onClick={() => move(i, 1)}>
                <ArrowDown />
              </Button>
              <Button variant="ghost" size="icon-sm" aria-label="Remove" onClick={() => onChange(value.filter((x) => x !== id))}>
                <X />
              </Button>
            </li>
          ))}
        </ol>
      )}
      <Input placeholder="Filter to add…" aria-label={`Filter ${label}`} value={filter} onChange={(e) => setFilter(e.target.value)} />
      <ul className="max-h-48 overflow-y-auto rounded-md border">
        {available.map((o) => (
          <li key={o.id}>
            <button
              type="button"
              onClick={() => onChange([...value, o.id])}
              className={cn("flex w-full items-center gap-2 px-2 py-1.5 text-left text-sm hover:bg-surface-muted", o.indent && "pl-6 text-muted-foreground")}
            >
              <Plus className="size-3.5 shrink-0" aria-hidden />
              <span className="truncate">{o.label}</span>
            </button>
          </li>
        ))}
        {available.length === 0 && <li className="px-2 py-1.5 text-sm text-muted-foreground">Nothing else to add.</li>}
      </ul>
    </fieldset>
  );
}
