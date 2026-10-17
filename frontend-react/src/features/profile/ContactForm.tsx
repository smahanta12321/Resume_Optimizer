import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Trash2 } from "lucide-react";
import { useEffect } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/form-controls";
import { Card, CardBody, CardHeader } from "@/components/ui/surface";
import { UnsavedChangesGuard } from "@/components/shared/UnsavedChanges";
import type { MasterProfile } from "@/services/api/types";
import { contactSchema, type ContactValues } from "./schemas";
import { tempId } from "./SectionEditor";
import { useProfileSave } from "./useProfileSave";

const toValues = (p: MasterProfile): ContactValues => ({
  full_name: p.contact.full_name,
  email: p.contact.email,
  phone: p.contact.phone,
  location: p.contact.location,
  headline: p.headline,
  summary: p.summary,
  links: p.contact.links.map((l) => ({ id: l.id, label: l.label, url: l.url })),
});

export function ContactForm({ profile }: { profile: MasterProfile }) {
  const { saveSection, saving } = useProfileSave(profile);
  const { register, control, handleSubmit, formState, reset } = useForm<ContactValues>({
    resolver: zodResolver(contactSchema),
    defaultValues: toValues(profile),
  });
  const links = useFieldArray({ control, name: "links", keyName: "_key" });
  const e = formState.errors;

  useEffect(() => {
    if (!formState.isDirty) reset(toValues(profile));
  }, [profile, formState.isDirty, reset]);

  return (
    <Card>
      <UnsavedChangesGuard when={formState.isDirty} />
      <CardHeader title="Contact and summary" description="Only include statements in your summary that the entries below support." />
      <CardBody>
        <form
          noValidate
          className="space-y-4"
          onSubmit={handleSubmit((v) =>
            saveSection(
              {
                headline: v.headline.trim(),
                summary: v.summary.trim(),
                contact: {
                  full_name: v.full_name.trim(),
                  email: v.email.trim(),
                  phone: v.phone.trim(),
                  location: v.location.trim(),
                  links: v.links.map((l) => ({ id: l.id ?? tempId(), label: l.label.trim(), url: l.url.trim() })),
                },
              },
              { onSaved: () => reset(v) },
            ),
          )}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Full name" required error={e.full_name?.message}>
              {(p) => <Input {...p} autoComplete="name" {...register("full_name")} />}
            </Field>
            <Field label="Email" error={e.email?.message}>
              {(p) => <Input {...p} type="email" autoComplete="email" {...register("email")} />}
            </Field>
            <Field label="Phone">{(p) => <Input {...p} type="tel" autoComplete="tel" {...register("phone")} />}</Field>
            <Field label="Location">{(p) => <Input {...p} {...register("location")} />}</Field>
          </div>
          <Field label="Headline" hint="e.g. “Data Engineer · Python, SQL, Airflow”">
            {(p) => <Input {...p} {...register("headline")} />}
          </Field>
          <Field label="Summary">{(p) => <Textarea {...p} rows={5} {...register("summary")} />}</Field>
          <fieldset className="space-y-2">
            <div className="flex items-center justify-between">
              <legend className="text-sm font-medium">Links</legend>
              <Button size="sm" variant="secondary" onClick={() => links.append({ label: "", url: "" })}>
                <Plus /> Add link
              </Button>
            </div>
            {links.fields.map((f, i) => (
              <div key={f._key} className="grid gap-2 sm:grid-cols-[12rem_1fr_auto]">
                <Field label="Label" className="sm:[&>label]:sr-only" error={e.links?.[i]?.label?.message}>
                  {(p) => <Input {...p} placeholder="LinkedIn" {...register(`links.${i}.label`)} />}
                </Field>
                <Field label="URL" className="sm:[&>label]:sr-only" error={e.links?.[i]?.url?.message}>
                  {(p) => <Input {...p} placeholder="https://…" {...register(`links.${i}.url`)} />}
                </Field>
                <Button variant="ghost" size="icon" aria-label={`Remove link ${i + 1}`} onClick={() => links.remove(i)}>
                  <Trash2 />
                </Button>
              </div>
            ))}
          </fieldset>
          <div className="flex gap-2">
            <Button type="submit" disabled={!formState.isDirty} loading={saving}>
              Save contact and summary
            </Button>
            <Button variant="ghost" disabled={!formState.isDirty} onClick={() => reset(toValues(profile))}>
              Undo changes
            </Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}
