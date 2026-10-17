import { useQuery } from "@tanstack/react-query";
import { ShieldAlert, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Select } from "@/components/ui/form-controls";
import { Alert, Card, CardBody, CardHeader } from "@/components/ui/surface";
import { QueryView } from "@/components/shared/states";
import { cn } from "@/lib/utils";
import { errorMessage } from "@/services/api/client";
import { api } from "@/services/api/endpoints";
import { useJobAction, useTailoring } from "@/services/api/queries";
import type { GenerateIn, TailoringOptions, TargetLength } from "@/services/api/types";

export function GenerateStep({ jobId, onGenerated }: { jobId: string; onGenerated: (versionId: string) => void }) {
  const options = useTailoring(jobId);
  return <QueryView query={options}>{(o) => <GenerateForm options={o} jobId={jobId} onGenerated={onGenerated} />}</QueryView>;
}

function GenerateForm({ options, jobId, onGenerated }: { options: TailoringOptions; jobId: string; onGenerated: (id: string) => void }) {
  const [roleId, setRoleId] = useState<string>(options.recommended_role_id ?? "");
  const [pages, setPages] = useState<TargetLength>(1);
  const [useAi, setUseAi] = useState(false);
  const [consent, setConsent] = useState(false);
  const status = options.provider_status;
  const body: GenerateIn = { role_profile_id: roleId || null, target_pages: pages, use_ai: useAi, consent };
  const generate = useJobAction(() => api.resumes.generate(jobId, body));

  // What would be sent to the provider. Fetched only when the user turns AI on; nothing is sent here.
  const preview = useQuery({
    queryKey: ["ai-preview", jobId, roleId, pages],
    queryFn: () => api.resumes.aiPreview(jobId, { role_profile_id: roleId || null, target_pages: pages }),
    enabled: useAi && status.available,
    staleTime: 0,
  });

  const recommended = new Map(options.role_recommendations.map((r) => [r.id, r.score]));

  if (options.blockers.length > 0) {
    return (
      <Alert tone="warning" title="Not ready to generate">
        {options.blockers[0]}
      </Alert>
    );
  }

  return (
    <Card>
      <CardHeader
        title="Generate a draft"
        description="Builds the resume only from your master profile. Every line will cite the evidence behind it. Nothing is exported or sent anywhere until you approve it."
      />
      <CardBody className="space-y-5">
        {options.is_sample_profile && (
          <Alert tone="warning">You're using the fictional sample profile. Replace it with your own data before generating real resumes.</Alert>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Base role profile"
            hint={
              options.role_profiles.length === 0 ? (
                <>
                  None yet. <Link className="underline" to="/roles">Create one</Link> to control which evidence leads.
                </>
              ) : (
                "A named selection and ordering of your evidence. It never adds facts."
              )
            }
          >
            {(p) => (
              <Select {...p} value={roleId} onChange={(e) => setRoleId(e.target.value)}>
                <option value="">None (rank evidence by this job only)</option>
                {options.role_profiles.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                    {r.id === options.recommended_role_id ? " (recommended)" : ""}
                    {recommended.has(r.id) ? ` · covers ${Math.round((recommended.get(r.id) ?? 0) * 100)}%` : ""}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <fieldset className="grid gap-1.5">
            <legend className="mb-1.5 text-sm font-medium">Target length</legend>
            <div className="flex gap-2">
              {([1, 2] as TargetLength[]).map((n) => (
                <label
                  key={n}
                  className={cn("flex flex-1 cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm", pages === n && "border-primary bg-primary-soft")}
                >
                  <input type="radio" name="pages" checked={pages === n} onChange={() => setPages(n)} className="accent-[var(--primary)]" />
                  {n} page{n > 1 ? "s" : ""}
                </label>
              ))}
            </div>
          </fieldset>
        </div>

        <div className="space-y-3 rounded-md border p-4">
          <div className="flex items-start gap-2">
            <Sparkles className="mt-0.5 size-4 text-muted-foreground" aria-hidden />
            <div className="space-y-1 text-sm">
              <p className="font-medium">Wording improvements (optional)</p>
              <p className="text-muted-foreground">{status.message}</p>
            </div>
          </div>
          {status.available && (
            <>
              <Checkbox
                label={`Improve wording with AI (${status.provider}, ${status.model})`}
                description="Rewrites are checked automatically. Any rewrite that adds numbers, skills or tools is discarded and your original wording is kept."
                checked={useAi}
                onChange={(e) => {
                  setUseAi(e.target.checked);
                  setConsent(false);
                }}
              />
              {useAi && (
                <div className="space-y-3">
                  <Alert tone="warning" title={`This sends the text below to ${status.provider}, an external service`}>
                    Your name, contact details and employer names are not included.
                  </Alert>
                  <details className="rounded-md border bg-surface-muted/40" open>
                    <summary className="cursor-pointer px-3 py-2 text-sm font-medium">Exactly what will be sent</summary>
                    <div className="border-t px-3 py-2">
                      <QueryView query={preview}>
                        {(p) => (
                          <pre className="max-h-72 overflow-auto whitespace-pre-wrap text-xs">
                            {p.system}
                            {"\n\n---\n\n"}
                            {p.user}
                          </pre>
                        )}
                      </QueryView>
                    </div>
                  </details>
                  <Checkbox
                    label={`I agree to send this content to ${status.provider}.`}
                    checked={consent}
                    disabled={!preview.isSuccess}
                    onChange={(e) => setConsent(e.target.checked)}
                  />
                </div>
              )}
            </>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button
            disabled={useAi && !consent}
            loading={generate.isPending}
            onClick={() =>
              generate.mutate(undefined, {
                onSuccess: (out) => {
                  if (out.ai_failed) toast.warning(`AI rewriting failed: ${out.ai_failed} The draft keeps your original wording.`);
                  out.notes.forEach((n) => toast.info(n));
                  toast.success(`Created version ${out.version.id}. Review it before approving.`);
                  onGenerated(out.version.id);
                },
                onError: (e) => toast.error(errorMessage(e)),
              })
            }
          >
            Generate draft
          </Button>
          {generate.isPending && useAi && (
            <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <ShieldAlert className="size-4" /> Waiting for {status.provider}. This can take up to a minute.
            </p>
          )}
        </div>
      </CardBody>
    </Card>
  );
}
