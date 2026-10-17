import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useFieldArray, useForm, type Control, type FieldErrors, type UseFormRegister } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/form-controls";
import type { Achievement, Bullet, Certification, Education, Experience, Project } from "@/services/api/types";
import {
  achievementSchema,
  certificationSchema,
  educationSchema,
  experienceSchema,
  metricsToText,
  nullIfBlank,
  parseMetrics,
  projectSchema,
  toList,
  type AchievementValues,
  type CertificationValues,
  type EducationValues,
  type ExperienceValues,
  type ProjectValues,
} from "./schemas";
import { tempId } from "./SectionEditor";

interface FormProps<T> {
  initial?: T;
  onSubmit: (item: T) => void;
  onCancel: () => void;
}

function Actions({ onCancel, isNew }: { onCancel: () => void; isNew: boolean }) {
  return (
    <div className="sticky bottom-0 -mx-5 -mb-4 flex justify-end gap-2 border-t bg-surface px-5 py-3">
      <Button variant="secondary" onClick={onCancel}>
        Cancel
      </Button>
      <Button type="submit">{isNew ? "Add to draft" : "Update draft"}</Button>
    </div>
  );
}

const MONTH_HINT = "YYYY-MM";

// ---- bullets ------------------------------------------------------------------------

type BulletValues = ExperienceValues["bullets"][number];

const bulletToValues = (b: Bullet): BulletValues => ({
  id: b.id,
  text: b.text,
  skills: b.skills.join(", "),
  source_note: b.source_note,
  metrics: metricsToText(b.verified_metrics),
});

function valuesToBullets(values: BulletValues[], original: Bullet[]): Bullet[] {
  return values.map((v) => {
    const base = original.find((b) => b.id === v.id);
    return {
      ...(base ?? { id: tempId(), verified_metrics: [] }),
      id: v.id ?? tempId(),
      text: v.text.trim(),
      skills: toList(v.skills),
      source_note: v.source_note.trim(),
      verified_metrics: parseMetrics(v.metrics).map((m) => ({
        ...m,
        source_note: base?.verified_metrics.find((x) => x.label === m.label)?.source_note ?? "",
      })),
    };
  });
}

function BulletsField({
  control,
  register,
  errors,
}: {
  control: Control<ExperienceValues> | Control<ProjectValues>;
  register: UseFormRegister<ExperienceValues> | UseFormRegister<ProjectValues>;
  errors?: FieldErrors<ExperienceValues>["bullets"];
}) {
  // Both forms share the same bullets shape; narrow once for the hooks.
  const c = control as Control<ExperienceValues>;
  const r = register as UseFormRegister<ExperienceValues>;
  const rows = useFieldArray({ control: c, name: "bullets", keyName: "_key" });
  return (
    <fieldset className="space-y-3">
      <div className="flex items-center justify-between">
        <legend className="text-sm font-medium">Bullets</legend>
        <Button size="sm" variant="secondary" onClick={() => rows.append({ text: "", skills: "", source_note: "", metrics: "" })}>
          <Plus /> Add bullet
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        One factual statement per bullet. Only include numbers you can verify, and record them as metrics (label=value; label=value) so the
        resume checks accept them.
      </p>
      {rows.fields.length === 0 && <p className="rounded-md border border-dashed p-3 text-center text-sm text-muted-foreground">No bullets yet.</p>}
      <ol className="space-y-3">
        {rows.fields.map((f, i) => (
          <li key={f._key} className="space-y-2 rounded-md border p-3">
            <div className="flex items-start gap-2">
              <Field label={`Bullet ${i + 1}`} className="flex-1" error={errors?.[i]?.text?.message}>
                {(p) => <Textarea {...p} rows={2} {...r(`bullets.${i}.text`)} />}
              </Field>
              <div className="flex flex-col pt-6">
                <Button variant="ghost" size="icon-sm" aria-label="Move bullet up" disabled={i === 0} onClick={() => rows.move(i, i - 1)}>
                  <ArrowUp />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Move bullet down"
                  disabled={i === rows.fields.length - 1}
                  onClick={() => rows.move(i, i + 1)}
                >
                  <ArrowDown />
                </Button>
                <Button variant="ghost" size="icon-sm" aria-label="Remove bullet" onClick={() => rows.remove(i)}>
                  <Trash2 />
                </Button>
              </div>
            </div>
            <div className="grid gap-2 sm:grid-cols-3">
              <Field label="Skills shown" hint="Comma-separated">
                {(p) => <Input {...p} {...r(`bullets.${i}.skills`)} />}
              </Field>
              <Field label="Verified metrics" hint="label=value; …" error={errors?.[i]?.metrics?.message}>
                {(p) => <Input {...p} placeholder="latency reduction=35%" {...r(`bullets.${i}.metrics`)} />}
              </Field>
              <Field label="Source note" hint="Where it can be verified">
                {(p) => <Input {...p} {...r(`bullets.${i}.source_note`)} />}
              </Field>
            </div>
          </li>
        ))}
      </ol>
    </fieldset>
  );
}

// ---- experience ---------------------------------------------------------------------

export function ExperienceForm({ initial, onSubmit, onCancel }: FormProps<Experience>) {
  const { register, control, handleSubmit, formState } = useForm<ExperienceValues>({
    resolver: zodResolver(experienceSchema),
    defaultValues: {
      employer: initial?.employer ?? "",
      title: initial?.title ?? "",
      location: initial?.location ?? "",
      employment_type: initial?.employment_type ?? "",
      start_date: initial?.start_date ?? "",
      end_date: initial?.end_date ?? "",
      description: initial?.description ?? "",
      skills: initial?.skills.join(", ") ?? "",
      source_note: initial?.source_note ?? "",
      bullets: initial?.bullets.map(bulletToValues) ?? [],
    },
  });
  const e = formState.errors;
  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={handleSubmit((v) =>
        onSubmit({
          ...(initial ?? { id: tempId() }),
          employer: v.employer.trim(),
          title: v.title.trim(),
          location: v.location.trim(),
          employment_type: v.employment_type.trim(),
          start_date: nullIfBlank(v.start_date),
          end_date: nullIfBlank(v.end_date),
          description: v.description.trim(),
          skills: toList(v.skills),
          source_note: v.source_note.trim(),
          bullets: valuesToBullets(v.bullets, initial?.bullets ?? []),
        }),
      )}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Employer" required error={e.employer?.message}>
          {(p) => <Input {...p} {...register("employer")} />}
        </Field>
        <Field label="Job title" required error={e.title?.message}>
          {(p) => <Input {...p} {...register("title")} />}
        </Field>
        <Field label="Location">{(p) => <Input {...p} {...register("location")} />}</Field>
        <Field label="Employment type" hint="e.g. Full-time">
          {(p) => <Input {...p} {...register("employment_type")} />}
        </Field>
        <Field label="Start" hint={MONTH_HINT} error={e.start_date?.message}>
          {(p) => <Input {...p} type="month" {...register("start_date")} />}
        </Field>
        <Field label="End" hint="Blank = current" error={e.end_date?.message}>
          {(p) => <Input {...p} type="month" {...register("end_date")} />}
        </Field>
      </div>
      <Field label="Description">{(p) => <Textarea {...p} rows={3} {...register("description")} />}</Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Skills used" hint="Comma-separated">
          {(p) => <Input {...p} {...register("skills")} />}
        </Field>
        <Field label="Source note" hint="Where this can be verified">
          {(p) => <Input {...p} {...register("source_note")} />}
        </Field>
      </div>
      <BulletsField control={control} register={register} errors={e.bullets} />
      <Actions onCancel={onCancel} isNew={!initial} />
    </form>
  );
}

// ---- projects -----------------------------------------------------------------------

export function ProjectForm({ initial, onSubmit, onCancel, experience }: FormProps<Project> & { experience: Experience[] }) {
  const { register, control, handleSubmit, formState } = useForm<ProjectValues>({
    resolver: zodResolver(projectSchema),
    defaultValues: {
      name: initial?.name ?? "",
      role: initial?.role ?? "",
      url: initial?.url ?? "",
      related_experience_id: initial?.related_experience_id ?? "",
      start_date: initial?.start_date ?? "",
      end_date: initial?.end_date ?? "",
      description: initial?.description ?? "",
      skills: initial?.skills.join(", ") ?? "",
      source_note: initial?.source_note ?? "",
      bullets: initial?.bullets.map(bulletToValues) ?? [],
    },
  });
  const e = formState.errors;
  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={handleSubmit((v) =>
        onSubmit({
          ...(initial ?? { id: tempId() }),
          name: v.name.trim(),
          role: v.role.trim(),
          url: v.url.trim(),
          related_experience_id: v.related_experience_id || null,
          start_date: nullIfBlank(v.start_date),
          end_date: nullIfBlank(v.end_date),
          description: v.description.trim(),
          skills: toList(v.skills),
          source_note: v.source_note.trim(),
          bullets: valuesToBullets(v.bullets, initial?.bullets ?? []),
        }),
      )}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Project name" required error={e.name?.message}>
          {(p) => <Input {...p} {...register("name")} />}
        </Field>
        <Field label="Your role">{(p) => <Input {...p} {...register("role")} />}</Field>
        <Field label="URL" error={e.url?.message}>
          {(p) => <Input {...p} type="url" {...register("url")} />}
        </Field>
        <Field label="Related experience" hint="Only saved experience entries are listed">
          {(p) => (
            <Select {...p} {...register("related_experience_id")}>
              <option value="">None</option>
              {experience
                .filter((x) => !x.id.startsWith("tmp-"))
                .map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.title} @ {x.employer}
                  </option>
                ))}
            </Select>
          )}
        </Field>
        <Field label="Start" hint={MONTH_HINT} error={e.start_date?.message}>
          {(p) => <Input {...p} type="month" {...register("start_date")} />}
        </Field>
        <Field label="End" hint="Blank = ongoing" error={e.end_date?.message}>
          {(p) => <Input {...p} type="month" {...register("end_date")} />}
        </Field>
      </div>
      <Field label="Description">{(p) => <Textarea {...p} rows={3} {...register("description")} />}</Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Skills used" hint="Comma-separated">
          {(p) => <Input {...p} {...register("skills")} />}
        </Field>
        <Field label="Source note">{(p) => <Input {...p} {...register("source_note")} />}</Field>
      </div>
      <BulletsField control={control} register={register} errors={e.bullets} />
      <Actions onCancel={onCancel} isNew={!initial} />
    </form>
  );
}

// ---- education / certifications / achievements -----------------------------------------

export function EducationForm({ initial, onSubmit, onCancel }: FormProps<Education>) {
  const { register, handleSubmit, formState } = useForm<EducationValues>({
    resolver: zodResolver(educationSchema),
    defaultValues: {
      institution: initial?.institution ?? "",
      degree: initial?.degree ?? "",
      field_of_study: initial?.field_of_study ?? "",
      location: initial?.location ?? "",
      grade: initial?.grade ?? "",
      start_date: initial?.start_date ?? "",
      end_date: initial?.end_date ?? "",
      source_note: initial?.source_note ?? "",
    },
  });
  const e = formState.errors;
  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={handleSubmit((v) =>
        onSubmit({
          ...(initial ?? { id: tempId() }),
          institution: v.institution.trim(),
          degree: v.degree.trim(),
          field_of_study: v.field_of_study.trim(),
          location: v.location.trim(),
          grade: v.grade.trim(),
          start_date: nullIfBlank(v.start_date),
          end_date: nullIfBlank(v.end_date),
          source_note: v.source_note.trim(),
        }),
      )}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Institution" required error={e.institution?.message}>
          {(p) => <Input {...p} {...register("institution")} />}
        </Field>
        <Field label="Degree" required error={e.degree?.message}>
          {(p) => <Input {...p} {...register("degree")} />}
        </Field>
        <Field label="Field of study">{(p) => <Input {...p} {...register("field_of_study")} />}</Field>
        <Field label="Location">{(p) => <Input {...p} {...register("location")} />}</Field>
        <Field label="Grade">{(p) => <Input {...p} {...register("grade")} />}</Field>
        <Field label="Source note">{(p) => <Input {...p} {...register("source_note")} />}</Field>
        <Field label="Start" hint={MONTH_HINT} error={e.start_date?.message}>
          {(p) => <Input {...p} type="month" {...register("start_date")} />}
        </Field>
        <Field label="End" hint={MONTH_HINT} error={e.end_date?.message}>
          {(p) => <Input {...p} type="month" {...register("end_date")} />}
        </Field>
      </div>
      <Actions onCancel={onCancel} isNew={!initial} />
    </form>
  );
}

export function CertificationForm({ initial, onSubmit, onCancel }: FormProps<Certification>) {
  const { register, handleSubmit, formState } = useForm<CertificationValues>({
    resolver: zodResolver(certificationSchema),
    defaultValues: {
      name: initial?.name ?? "",
      issuer: initial?.issuer ?? "",
      issue_date: initial?.issue_date ?? "",
      expiry_date: initial?.expiry_date ?? "",
      credential_url: initial?.credential_url ?? "",
      source_note: initial?.source_note ?? "",
    },
  });
  const e = formState.errors;
  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={handleSubmit((v) =>
        onSubmit({
          ...(initial ?? { id: tempId() }),
          name: v.name.trim(),
          issuer: v.issuer.trim(),
          issue_date: nullIfBlank(v.issue_date),
          expiry_date: nullIfBlank(v.expiry_date),
          credential_url: v.credential_url.trim(),
          source_note: v.source_note.trim(),
        }),
      )}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Certification" required error={e.name?.message}>
          {(p) => <Input {...p} {...register("name")} />}
        </Field>
        <Field label="Issuer">{(p) => <Input {...p} {...register("issuer")} />}</Field>
        <Field label="Issued" hint={MONTH_HINT} error={e.issue_date?.message}>
          {(p) => <Input {...p} type="month" {...register("issue_date")} />}
        </Field>
        <Field label="Expires" hint={MONTH_HINT} error={e.expiry_date?.message}>
          {(p) => <Input {...p} type="month" {...register("expiry_date")} />}
        </Field>
        <Field label="Credential URL" error={e.credential_url?.message}>
          {(p) => <Input {...p} type="url" {...register("credential_url")} />}
        </Field>
        <Field label="Source note">{(p) => <Input {...p} {...register("source_note")} />}</Field>
      </div>
      <Actions onCancel={onCancel} isNew={!initial} />
    </form>
  );
}

export function AchievementForm({ initial, onSubmit, onCancel }: FormProps<Achievement>) {
  const { register, handleSubmit, formState } = useForm<AchievementValues>({
    resolver: zodResolver(achievementSchema),
    defaultValues: {
      title: initial?.title ?? "",
      description: initial?.description ?? "",
      date: initial?.date ?? "",
      source_note: initial?.source_note ?? "",
      metrics: metricsToText(initial?.verified_metrics ?? []),
    },
  });
  const e = formState.errors;
  return (
    <form
      noValidate
      className="space-y-4"
      onSubmit={handleSubmit((v) =>
        onSubmit({
          ...(initial ?? { id: tempId() }),
          title: v.title.trim(),
          description: v.description.trim(),
          date: nullIfBlank(v.date),
          source_note: v.source_note.trim(),
          verified_metrics: parseMetrics(v.metrics),
        }),
      )}
    >
      <Field label="Achievement" required error={e.title?.message}>
        {(p) => <Input {...p} {...register("title")} />}
      </Field>
      <Field label="Description">{(p) => <Textarea {...p} rows={3} {...register("description")} />}</Field>
      <div className="grid gap-3 sm:grid-cols-3">
        <Field label="Date" hint={MONTH_HINT} error={e.date?.message}>
          {(p) => <Input {...p} type="month" {...register("date")} />}
        </Field>
        <Field label="Verified metrics" hint="label=value; …" error={e.metrics?.message}>
          {(p) => <Input {...p} {...register("metrics")} />}
        </Field>
        <Field label="Source note">{(p) => <Input {...p} {...register("source_note")} />}</Field>
      </div>
      <Actions onCancel={onCancel} isNew={!initial} />
    </form>
  );
}
