import { zodResolver } from "@hookform/resolvers/zod";
import { Award, BadgeCheck, Briefcase, FlaskConical, FolderGit2, GraduationCap, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useSearchParams } from "react-router";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form-controls";
import { Alert, Badge, Card, CardBody, CardHeader } from "@/components/ui/surface";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryView } from "@/components/shared/states";
import { formatDateTime, formatRange, pluralize } from "@/lib/format";
import { errorMessage } from "@/services/api/client";
import { api } from "@/services/api/endpoints";
import { useProfile, useProfileAction, useSaveProfile } from "@/services/api/queries";
import type { MasterProfile, ProfileView } from "@/services/api/types";
import { ContactForm } from "./ContactForm";
import { ExportAndDeletePanel, HistoryPanel, ImportPanel } from "./DataPanels";
import { AchievementForm, CertificationForm, EducationForm, ExperienceForm, ProjectForm } from "./EntryForms";
import { optionalEmail } from "./schemas";
import { SectionEditor } from "./SectionEditor";
import { useProfileSave } from "./useProfileSave";

const SECTIONS = ["contact", "experience", "projects", "education", "certifications", "achievements", "data", "history"] as const;
type Section = (typeof SECTIONS)[number];

export function ProfilePage() {
  const profile = useProfile();
  return (
    <>
      <PageHeader title="Master profile" description="Your verified source of truth. Tailored resumes may only use facts recorded here." />
      <QueryView query={profile}>{(v) => (v.profile ? <Editor view={v as ProfileView & { profile: MasterProfile }} /> : <Onboarding />)}</QueryView>
    </>
  );
}

function StatusBar({ view }: { view: ProfileView & { profile: MasterProfile } }) {
  const p = view.profile;
  const confirm = useProfileAction(() => api.profile.confirm(p.profile_version));
  const [showNotes, setShowNotes] = useState(false);
  return (
    <div className="space-y-3">
      {p.is_sample && (
        <Alert tone="info" title="You're viewing the fictional sample profile">
          Replace it with your own data (import JSON or edit each section) before generating real resumes.
        </Alert>
      )}
      <Card>
        <CardBody className="flex flex-wrap items-center justify-between gap-3 py-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge tone="outline">Version {p.profile_version}</Badge>
            {p.confirmed_at ? (
              <span className="flex items-center gap-1.5 text-success">
                <ShieldCheck className="size-4" /> Reviewed and confirmed {formatDateTime(p.confirmed_at)}
              </span>
            ) : (
              <span className="text-warning">Not confirmed. Review every section, then confirm.</span>
            )}
            {view.warnings.length > 0 && (
              <button type="button" className="text-muted-foreground underline hover:text-foreground" aria-expanded={showNotes} onClick={() => setShowNotes((s) => !s)}>
                {pluralize(view.warnings.length, "quality note")}
              </button>
            )}
          </div>
          {!p.confirmed_at && (
            <Button
              loading={confirm.isPending}
              onClick={() =>
                confirm.mutate(undefined, {
                  onSuccess: () => toast.success(`Profile version ${p.profile_version} confirmed.`),
                  onError: (e) => toast.error(errorMessage(e)),
                })
              }
            >
              <BadgeCheck /> Confirm profile
            </Button>
          )}
        </CardBody>
        {showNotes && (
          <ul className="space-y-1 border-t px-4 py-3 text-sm">
            {view.warnings.map((w, i) => (
              <li key={i} className="flex flex-wrap gap-2">
                <span>{w.message}</span>
                {w.item_id && <code className="text-xs text-muted-foreground">{w.item_id}</code>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Editor({ view }: { view: ProfileView & { profile: MasterProfile } }) {
  const p = view.profile;
  const [params, setParams] = useSearchParams();
  const section = (SECTIONS as readonly string[]).includes(params.get("section") ?? "") ? (params.get("section") as Section) : "contact";
  const { saveSection, saving } = useProfileSave(p);

  return (
    <div className="space-y-4">
      <StatusBar view={view} />
      <Tabs value={section} onValueChange={(s) => setParams({ section: s }, { replace: true })}>
        <TabsList>
          <TabsTrigger value="contact">Contact & summary</TabsTrigger>
          <TabsTrigger value="experience">Experience ({p.experience.length})</TabsTrigger>
          <TabsTrigger value="projects">Projects ({p.projects.length})</TabsTrigger>
          <TabsTrigger value="education">Education ({p.education.length})</TabsTrigger>
          <TabsTrigger value="certifications">Certifications ({p.certifications.length})</TabsTrigger>
          <TabsTrigger value="achievements">Achievements ({p.achievements.length})</TabsTrigger>
          <TabsTrigger value="data">Import / export</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>
        <TabsContent value="contact">
          <ContactForm profile={p} />
        </TabsContent>
        <TabsContent value="experience">
          <SectionEditor
            title="Experience"
            noun="experience"
            icon={Briefcase}
            items={p.experience}
            saving={saving}
            summarize={(x) => ({
              title: `${x.title} @ ${x.employer}`,
              subtitle: [formatRange(x.start_date, x.end_date), x.location].filter(Boolean).join(" · "),
              meta: `${pluralize(x.bullets.length, "bullet")} · ${x.id}`,
            })}
            renderForm={(f) => <ExperienceForm {...f} />}
            onSave={(items) => saveSection({ experience: items })}
          />
        </TabsContent>
        <TabsContent value="projects">
          <SectionEditor
            title="Projects"
            noun="project"
            icon={FolderGit2}
            items={p.projects}
            saving={saving}
            summarize={(x) => ({
              title: x.name,
              subtitle: [x.role, formatRange(x.start_date, x.end_date)].filter(Boolean).join(" · "),
              meta: `${pluralize(x.bullets.length, "bullet")} · ${x.id}`,
            })}
            renderForm={(f) => <ProjectForm {...f} experience={p.experience} />}
            onSave={(items) => saveSection({ projects: items })}
          />
        </TabsContent>
        <TabsContent value="education">
          <SectionEditor
            title="Education"
            noun="education"
            icon={GraduationCap}
            items={p.education}
            saving={saving}
            summarize={(x) => ({
              title: `${x.degree}${x.field_of_study ? `, ${x.field_of_study}` : ""}`,
              subtitle: [x.institution, formatRange(x.start_date, x.end_date)].filter(Boolean).join(" · "),
            })}
            renderForm={(f) => <EducationForm {...f} />}
            onSave={(items) => saveSection({ education: items })}
          />
        </TabsContent>
        <TabsContent value="certifications">
          <SectionEditor
            title="Certifications"
            noun="certification"
            icon={BadgeCheck}
            items={p.certifications}
            saving={saving}
            summarize={(x) => ({ title: x.name, subtitle: [x.issuer, x.issue_date].filter(Boolean).join(" · ") })}
            renderForm={(f) => <CertificationForm {...f} />}
            onSave={(items) => saveSection({ certifications: items })}
          />
        </TabsContent>
        <TabsContent value="achievements">
          <SectionEditor
            title="Achievements"
            noun="achievement"
            icon={Award}
            items={p.achievements}
            saving={saving}
            summarize={(x) => ({ title: x.title, subtitle: [x.date, x.description].filter(Boolean).join(" · ") })}
            renderForm={(f) => <AchievementForm {...f} />}
            onSave={(items) => saveSection({ achievements: items })}
          />
        </TabsContent>
        <TabsContent value="data" className="space-y-4">
          <ImportPanel currentVersion={p.profile_version} />
          <ExportAndDeletePanel />
        </TabsContent>
        <TabsContent value="history">
          <HistoryPanel profile={p} />
        </TabsContent>
      </Tabs>
      <p className="text-sm text-muted-foreground">
        Skills are managed in the <Link to="/skills" className="underline">Skills Library</Link>.
      </p>
    </div>
  );
}

const createSchema = z.object({ full_name: z.string().trim().min(1, "Your name is required"), email: optionalEmail });

function Onboarding() {
  const save = useSaveProfile();
  const sample = useProfileAction(() => api.profile.loadSample());
  const { register, handleSubmit, formState } = useForm<z.infer<typeof createSchema>>({
    resolver: zodResolver(createSchema),
    defaultValues: { full_name: "", email: "" },
  });
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader title="Create from scratch" description="Start with your name, then add experience, projects and skills you can verify." />
        <CardBody>
          <form
            noValidate
            className="space-y-4"
            onSubmit={handleSubmit((v) =>
              save.mutate(
                { profile: { contact: { full_name: v.full_name, email: v.email } }, expectedVersion: null },
                { onSuccess: () => toast.success("Profile created."), onError: (e) => toast.error(errorMessage(e)) },
              ),
            )}
          >
            <Field label="Full name" required error={formState.errors.full_name?.message}>
              {(p) => <Input {...p} autoComplete="name" {...register("full_name")} />}
            </Field>
            <Field label="Email" error={formState.errors.email?.message}>
              {(p) => <Input {...p} type="email" autoComplete="email" {...register("email")} />}
            </Field>
            <Button type="submit" loading={save.isPending}>
              Create profile
            </Button>
          </form>
        </CardBody>
      </Card>
      <div className="space-y-4">
        <ImportPanel currentVersion={null} />
        <Card>
          <CardHeader title="Try the sample" description="Loads a clearly fictional profile for exploring the app. Replace it before real use." />
          <CardBody>
            <Button
              variant="secondary"
              loading={sample.isPending}
              onClick={() => sample.mutate(undefined, { onSuccess: () => toast.success("Loaded the fictional sample profile."), onError: (e) => toast.error(errorMessage(e)) })}
            >
              <FlaskConical /> Load fictional sample profile
            </Button>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
