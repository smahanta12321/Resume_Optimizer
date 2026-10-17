import { CheckCircle2, CircleSlash, Lock, LogOut } from "lucide-react";
import type { ReactNode } from "react";
import { useDraft } from "@/hooks/useDraft";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Select } from "@/components/ui/form-controls";
import { Alert, Card, CardBody, CardHeader, Kbd } from "@/components/ui/surface";
import { PageHeader } from "@/components/shared/PageHeader";
import { QueryView } from "@/components/shared/states";
import { UnsavedChangesGuard } from "@/components/shared/UnsavedChanges";
import { clearToken } from "@/lib/session";
import { API_ORIGIN, errorMessage } from "@/services/api/client";
import { useSaveSettings, useSettings } from "@/services/api/queries";
import type { SettingsPatch, SettingsValues, SettingsView } from "@/services/api/types";
import { SESSION_KEY } from "@/services/api/queries";

const PROVIDER_LABEL: Record<string, string> = { none: "None (off)", anthropic: "Anthropic", openai: "OpenAI" };

export function SettingsPage() {
  const settings = useSettings();
  return (
    <>
      <PageHeader title="Settings" description="Shared with the Streamlit app: a change here applies there too." />
      <QueryView query={settings}>{(s) => <SettingsForm view={s} />}</QueryView>
    </>
  );
}

function Locked({ reason }: { reason?: string }) {
  if (!reason) return null;
  return (
    <span className="flex items-center gap-1 text-xs text-muted-foreground">
      <Lock className="size-3" aria-hidden /> {reason}
    </span>
  );
}

function SettingsForm({ view }: { view: SettingsView }) {
  const { draft: values, setDraft: setValues, dirty, reset } = useDraft<SettingsValues>(view.saved);
  const save = useSaveSettings();
  const qc = useQueryClient();
  const locked = view.locked as Record<string, string | undefined>;

  const set = <K extends keyof SettingsValues>(key: K, value: SettingsValues[K]) => setValues((v) => ({ ...v, [key]: value }));

  const submit = () => {
    const changes: SettingsPatch = {};
    for (const key of Object.keys(values) as (keyof SettingsValues)[]) {
      if (!locked[key] && values[key] !== view.saved[key]) (changes as Record<string, unknown>)[key] = values[key];
    }
    save.mutate(changes, { onSuccess: () => toast.success("Settings saved."), onError: (e) => toast.error(errorMessage(e)) });
  };

  const status = view.provider_status;

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
      <div className="space-y-4">
        <UnsavedChangesGuard when={dirty} />
        <Section title="Privacy">
          <Checkbox
            label="Local-only mode: never contact any external service"
            description="Turns off URL import and AI rewriting."
            checked={values.local_only}
            disabled={Boolean(locked.local_only)}
            onChange={(e) => set("local_only", e.target.checked)}
          />
          <Locked reason={locked.local_only} />
        </Section>
        <Section title="AI wording improvements (optional)" description="Off by default. Content is sent only after you review it and tick a consent box for each draft.">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Provider" hint={<Locked reason={locked.llm_provider} />}>
              {(p) => (
                <Select {...p} value={values.llm_provider} disabled={Boolean(locked.llm_provider)} onChange={(e) => set("llm_provider", e.target.value)}>
                  {view.llm_providers.map((x) => (
                    <option key={x} value={x}>
                      {PROVIDER_LABEL[x] ?? x}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field
              label="Model"
              hint={locked.llm_model ? <Locked reason={locked.llm_model} /> : "Leave blank for the provider default. OpenAI needs a model."}
            >
              {(p) => (
                <Input
                  {...p}
                  value={values.llm_model}
                  placeholder={view.default_models.anthropic ? `Default for Anthropic: ${view.default_models.anthropic}` : undefined}
                  disabled={Boolean(locked.llm_model)}
                  onChange={(e) => set("llm_model", e.target.value)}
                />
              )}
            </Field>
          </div>
          {values.local_only && values.llm_provider !== "none" && (
            <Alert tone="info">Local-only mode is on, so AI rewriting stays off until you turn it off.</Alert>
          )}
          <p className="text-xs text-muted-foreground">
            API keys are read only from your environment (<Kbd>ANTHROPIC_API_KEY</Kbd>, <Kbd>OPENAI_API_KEY</Kbd> in <Kbd>.env</Kbd>). They are never
            saved, shown, or sent to this page.
          </p>
        </Section>
        <Section title="Resume export">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Template" hint={<Locked reason={locked.template} />}>
              {(p) => (
                <Select {...p} value={values.template} disabled={Boolean(locked.template)} onChange={(e) => set("template", e.target.value)}>
                  {view.templates.map((t) => (
                    <option key={t} value={t}>
                      {t === "classic" ? "Classic" : t === "compact" ? "Compact (tighter spacing)" : t}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Paper size" hint={<Locked reason={locked.page_size} />}>
              {(p) => (
                <Select {...p} value={values.page_size} disabled={Boolean(locked.page_size)} onChange={(e) => set("page_size", e.target.value)}>
                  {view.page_sizes.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
        </Section>
        <Section title="Job import">
          <Checkbox
            label="Allow best-effort import from a job URL"
            description="Fetches only the page you enter, honours robots.txt, and stops at sign-in pages or human checks."
            checked={values.url_import_enabled}
            disabled={Boolean(locked.url_import_enabled) || values.local_only}
            onChange={(e) => set("url_import_enabled", e.target.checked)}
          />
          <Locked reason={locked.url_import_enabled} />
        </Section>
        <Section
          title="Browser extension (optional)"
          description="The local receiver (python -m src.extension_receiver) puts captures from the extension in your review inbox. Pair the extension from the Streamlit Settings page, which shows the pairing token."
        >
          <div className="grid gap-3 sm:grid-cols-[1fr_10rem] sm:items-end">
            <Checkbox
              label="Accept job descriptions from the browser extension"
              checked={values.extension_enabled}
              disabled={Boolean(locked.extension_enabled)}
              onChange={(e) => set("extension_enabled", e.target.checked)}
            />
            <Field label="Receiver port" hint={<Locked reason={locked.extension_port} />}>
              {(p) => (
                <Input
                  {...p}
                  type="number"
                  min={1024}
                  max={65535}
                  value={values.extension_port}
                  disabled={Boolean(locked.extension_port)}
                  onChange={(e) => set("extension_port", Number(e.target.value))}
                />
              )}
            </Field>
          </div>
        </Section>
        <div className="flex gap-2">
          <Button onClick={submit} disabled={!dirty} loading={save.isPending}>
            Save settings
          </Button>
          <Button variant="ghost" disabled={!dirty} onClick={reset}>
            Undo changes
          </Button>
        </div>
      </div>

      <aside className="space-y-4">
        <Card>
          <CardHeader title="Status" />
          <CardBody className="space-y-3 text-sm">
            <StatusLine ok={status.available}>{status.message}</StatusLine>
            {Object.entries(view.keys_detected).map(([env, found]) => (
              <StatusLine key={env} ok={found}>
                <Kbd>{env}</Kbd> {found ? "detected" : "not set"}
              </StatusLine>
            ))}
            {view.values.local_only && <StatusLine ok={false}>Local-only mode is on.</StatusLine>}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Connection" />
          <CardBody className="space-y-3 text-sm">
            <StatusLine ok>
              Connected to <Kbd>{API_ORIGIN}</Kbd>
            </StatusLine>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                clearToken();
                void qc.resetQueries({ queryKey: SESSION_KEY });
              }}
            >
              <LogOut /> Disconnect this tab
            </Button>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="What is stored and sent" />
          <CardBody className="space-y-2 text-xs text-muted-foreground">
            <p>
              <strong className="text-foreground">Stored on this computer only:</strong> profile and versions, role profiles and settings in{" "}
              <Kbd>{view.data_dir}</Kbd>; jobs, analyses, match reports and resume versions in its <Kbd>jobs.sqlite3</Kbd>; exported files in{" "}
              <Kbd>{view.output_dir}</Kbd>.
            </p>
            <p>
              <strong className="text-foreground">Sent only when you trigger it:</strong> URL import fetches the one page you enter. AI rewriting sends
              exactly the preview you approve, never your name, contact details, employer names or the raw JD.
            </p>
            <p>Full data export and “delete everything” are on the Streamlit Settings page.</p>
          </CardBody>
        </Card>
      </aside>
    </div>
  );
}

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader title={title} description={description} />
      <CardBody className="space-y-3">{children}</CardBody>
    </Card>
  );
}

function StatusLine({ ok, children }: { ok: boolean; children: ReactNode }) {
  const Icon = ok ? CheckCircle2 : CircleSlash;
  return (
    <p className="flex gap-2">
      <Icon className={ok ? "mt-0.5 size-4 shrink-0 text-success" : "mt-0.5 size-4 shrink-0 text-muted-foreground"} aria-hidden />
      <span>{children}</span>
    </p>
  );
}
