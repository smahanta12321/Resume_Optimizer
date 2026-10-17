import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { ClipboardPaste, FileUp, Globe, Inbox, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/form-controls";
import { Alert, Card, CardBody, CardHeader } from "@/components/ui/surface";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FileDrop } from "@/components/shared/FileDrop";
import { PageHeader } from "@/components/shared/PageHeader";
import { EmptyState, QueryView } from "@/components/shared/states";
import { UnsavedChangesGuard } from "@/components/shared/UnsavedChanges";
import { formatDateTime } from "@/lib/format";
import { errorMessage, isApiError } from "@/services/api/client";
import { api } from "@/services/api/endpoints";
import { useCaptures, useJobAction, useSettings } from "@/services/api/queries";
import type { DuplicateView, JobCreateIn, JobDraft } from "@/services/api/types";
import { JD_FILE_RULES, jobReviewSchema, type JobReviewValues } from "./schemas";

const UNTRUSTED =
  "Job descriptions are treated as untrusted text: they are stored and shown, never followed as instructions. Only the text and source URL are saved, not the web page.";

type Source = "paste" | "file" | "url" | "inbox";

export function JobImportPage() {
  const [params] = useSearchParams();
  const [source, setSource] = useState<Source>(params.get("source") === "inbox" ? "inbox" : "paste");
  const [draft, setDraft] = useState<JobDraft | null>(null);

  return (
    <>
      <PageHeader
        title="Import a job description"
        description="Bring in a posting from LinkedIn, Naukri or anywhere else. You review everything before it's saved. The app never applies to jobs for you."
        crumbs={[{ label: "Job descriptions", to: "/jobs" }, { label: "Import" }]}
      />
      {draft ? (
        <ReviewStep draft={draft} onDiscard={() => setDraft(null)} />
      ) : (
        <Card>
          <CardHeader title="1. Choose a source" description="Pasting is the most reliable option: many job sites need sign-in." />
          <CardBody>
            <Tabs value={source} onValueChange={(v) => setSource(v as Source)}>
              <TabsList>
                <TabsTrigger value="paste">
                  <ClipboardPaste /> Paste text
                </TabsTrigger>
                <TabsTrigger value="file">
                  <FileUp /> Upload file
                </TabsTrigger>
                <TabsTrigger value="url">
                  <Globe /> From URL
                </TabsTrigger>
                <TabsTrigger value="inbox">
                  <Inbox /> Browser inbox
                </TabsTrigger>
              </TabsList>
              <TabsContent value="paste">
                <PasteSource onDraft={setDraft} />
              </TabsContent>
              <TabsContent value="file">
                <FileSource onDraft={setDraft} />
              </TabsContent>
              <TabsContent value="url">
                <UrlSource onDraft={setDraft} onPasteInstead={() => setSource("paste")} />
              </TabsContent>
              <TabsContent value="inbox">
                <InboxSource onDraft={setDraft} />
              </TabsContent>
            </Tabs>
          </CardBody>
        </Card>
      )}
    </>
  );
}

// ---- sources ------------------------------------------------------------------------

function PasteSource({ onDraft }: { onDraft: (d: JobDraft) => void }) {
  const [text, setText] = useState("");
  const m = useMutation({ mutationFn: api.jobs.draftFromText, onSuccess: onDraft });
  return (
    <div className="space-y-3">
      <Field label="Job description" error={m.isError ? errorMessage(m.error) : undefined}>
        {(p) => (
          <Textarea {...p} rows={12} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the full job posting here…" />
        )}
      </Field>
      <Button onClick={() => m.mutate(text)} disabled={!text.trim()} loading={m.isPending}>
        Review pasted text
      </Button>
    </div>
  );
}

function FileSource({ onDraft }: { onDraft: (d: JobDraft) => void }) {
  const m = useMutation({ mutationFn: api.jobs.draftFromFile, onSuccess: onDraft });
  return (
    <div className="space-y-3">
      <FileDrop
        rules={JD_FILE_RULES}
        label={m.isPending ? "Extracting text…" : "Upload a job description"}
        hint="Text-based .txt, .md, .pdf or .docx up to 5 MB. Scanned PDFs have no selectable text: paste those instead."
        onFile={(f) => m.mutate(f)}
        disabled={m.isPending}
      />
      {m.isError && <Alert tone="danger">{errorMessage(m.error)}</Alert>}
    </div>
  );
}

function UrlSource({ onDraft, onPasteInstead }: { onDraft: (d: JobDraft) => void; onPasteInstead: () => void }) {
  const settings = useSettings();
  const [url, setUrl] = useState("");
  const abort = useRef<AbortController | null>(null);
  const m = useMutation({
    mutationFn: (value: string) => {
      abort.current = new AbortController();
      return api.jobs.draftFromUrl(value, abort.current.signal);
    },
    onSuccess: onDraft,
  });

  return (
    <QueryView query={settings}>
      {(s) =>
        !s.values.url_import_enabled ? (
          <Alert tone="info" title="URL import is off">
            {s.values.local_only ? "Local-only mode is on" : "It's switched off"} in Settings. Paste or upload the job description instead.
          </Alert>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Best effort: the app fetches the single public page you enter, respects the site's robots.txt, and stops at
              sign-in pages or human checks. LinkedIn job pages usually need sign-in, so pasting is often more reliable.
            </p>
            <form
              className="flex flex-col gap-2 sm:flex-row"
              onSubmit={(e) => {
                e.preventDefault();
                if (url.trim()) m.mutate(url.trim());
              }}
            >
              <Input
                aria-label="Job page URL"
                type="url"
                placeholder="https://www.naukri.com/job-listings-…"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
              <Button type="submit" disabled={!url.trim()} loading={m.isPending}>
                Fetch page
              </Button>
              {m.isPending && (
                <Button variant="secondary" onClick={() => abort.current?.abort()}>
                  Cancel
                </Button>
              )}
            </form>
            {m.isError && !(m.error instanceof DOMException) && (
              <Alert
                tone="warning"
                title="Couldn't import this page"
                action={
                  <Button size="sm" variant="secondary" onClick={onPasteInstead}>
                    Paste instead
                  </Button>
                }
              >
                {errorMessage(m.error)}
              </Alert>
            )}
          </div>
        )
      }
    </QueryView>
  );
}

function InboxSource({ onDraft }: { onDraft: (d: JobDraft) => void }) {
  const captures = useCaptures();
  const review = useMutation({ mutationFn: api.jobs.draftFromCapture, onSuccess: onDraft, onError: (e) => toast.error(errorMessage(e)) });
  const discard = useJobAction(api.jobs.discardCapture);
  return (
    <QueryView query={captures}>
      {(list) =>
        list.length === 0 ? (
          <EmptyState icon={Inbox} title="Nothing captured">
            The optional browser extension sends a posting you're viewing here for review. Turn it on and pair it in the Streamlit
            Settings page; setup steps are in <code>browser_extension/README.md</code>.
          </EmptyState>
        ) : (
          <ul className="divide-y rounded-md border">
            {list.map((c) => (
              <li key={c.id} className="flex flex-col gap-3 p-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0 space-y-1">
                  <p className="font-medium">{[c.title || c.page_title || "Untitled", c.company].filter(Boolean).join(" · ")}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatDateTime(c.received_at)} · {c.method}
                    {c.url && <> · <span className="break-all">{c.url}</span></>}
                  </p>
                  <p className="line-clamp-2 text-sm text-muted-foreground">{c.text}</p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button size="sm" onClick={() => review.mutate(c.id)} loading={review.isPending && review.variables === c.id}>
                    Review
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label="Discard capture"
                    onClick={() => discard.mutate(c.id, { onSuccess: () => toast.success("Capture discarded.") })}
                  >
                    <Trash2 />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )
      }
    </QueryView>
  );
}

// ---- review & save --------------------------------------------------------------------

function ReviewStep({ draft, onDiscard }: { draft: JobDraft; onDiscard: () => void }) {
  const navigate = useNavigate();
  const [duplicates, setDuplicates] = useState<DuplicateView[] | null>(null);
  const [savedJobId, setSavedJobId] = useState<string | null>(null);
  // Navigate after the save commits, so the unsaved-changes guard is already off.
  useEffect(() => {
    if (savedJobId) navigate(`/jobs/${savedJobId}?tab=analysis`);
  }, [savedJobId, navigate]);
  const form = useForm<JobReviewValues>({
    resolver: zodResolver(jobReviewSchema),
    defaultValues: {
      title: draft.title,
      company: draft.company,
      location: draft.location,
      source_url: draft.source_url,
      source_platform: draft.suggested_platform,
      source_label: draft.source_label,
      text: draft.text,
    },
  });
  const { register, handleSubmit, formState } = form;
  const errors = formState.errors;

  const create = useJobAction(api.jobs.create);

  const body = (values: JobReviewValues): JobCreateIn => ({
    ...values,
    method: draft.method,
    source_notes: draft.source_notes,
    capture_id: draft.capture_id,
  });

  const save = (values: JobReviewValues, mode: JobCreateIn["on_duplicate"], mergeInto?: string) =>
    create.mutate(
      { ...body(values), on_duplicate: mode, merge_into_id: mergeInto },
      {
        onSuccess: (out) => {
          toast.success(out.merged ? "Updated the saved job. Its status and notes were kept." : "Job saved. Next, analyze its requirements.");
          setSavedJobId(out.job.id);
        },
        onError: (e) => {
          if (isApiError(e, "duplicate")) {
            setDuplicates(((e.details as { duplicates?: DuplicateView[] })?.duplicates ?? []) as DuplicateView[]);
          } else toast.error(errorMessage(e));
        },
      },
    );

  const notes = [...draft.source_notes, ...draft.text_notes];

  return (
    <>
      <UnsavedChangesGuard when={!savedJobId} />
      {duplicates ? (
        <Card>
          <CardHeader title="2. Possible duplicate" description="This looks like a job you already saved." />
          <CardBody className="space-y-4">
            <ul className="space-y-1 text-sm">
              {duplicates.map((d) => (
                <li key={d.job.id}>
                  <strong>{[d.job.title || "Untitled role", d.job.company].filter(Boolean).join(" @ ")}</strong>{" "}
                  <span className="text-muted-foreground">(imported {formatDateTime(d.job.imported_at)}): {d.reason}</span>
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap gap-2">
              <Button
                loading={create.isPending}
                onClick={handleSubmit((v) => save(v, "merge", duplicates[0]?.job.id))}
              >
                Update the saved job with this import
              </Button>
              <Button variant="secondary" onClick={handleSubmit((v) => save(v, "separate"))} disabled={create.isPending}>
                Save as a separate job
              </Button>
              <Button variant="ghost" onClick={() => setDuplicates(null)}>
                Back to review
              </Button>
            </div>
          </CardBody>
        </Card>
      ) : (
        <Card>
          <CardHeader title="2. Review and save" description={UNTRUSTED} />
          <CardBody>
            <form className="space-y-4" onSubmit={handleSubmit((v) => save(v, "check"))} noValidate>
              {notes.map((n) => (
                <Alert key={n} tone="warning">
                  {n}
                </Alert>
              ))}
              <div className="grid gap-4 sm:grid-cols-3">
                <Field label="Job title" error={errors.title?.message}>
                  {(p) => <Input {...p} {...register("title")} />}
                </Field>
                <Field label="Company" error={errors.company?.message}>
                  {(p) => <Input {...p} {...register("company")} />}
                </Field>
                <Field label="Location / work arrangement" error={errors.location?.message}>
                  {(p) => <Input {...p} {...register("location")} />}
                </Field>
              </div>
              <div className="grid gap-4 sm:grid-cols-[2fr_1fr_1fr]">
                <Field label="Source URL" hint="Optional" error={errors.source_url?.message}>
                  {(p) => <Input {...p} type="url" {...register("source_url")} />}
                </Field>
                <Field label="Platform">
                  {(p) => (
                    <Select {...p} {...register("source_platform")}>
                      <option value="linkedin">LinkedIn</option>
                      <option value="naukri">Naukri</option>
                      <option value="other">Other</option>
                    </Select>
                  )}
                </Field>
                <Field label="Source note" hint="Optional, e.g. “saved jobs”">
                  {(p) => <Input {...p} {...register("source_label")} />}
                </Field>
              </div>
              <Field label="Job description text" hint="Edit to remove unrelated content (menus, other postings)." error={errors.text?.message}>
                {(p) => <Textarea {...p} rows={16} className="font-mono text-xs" {...register("text")} />}
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button type="submit" loading={create.isPending}>
                  Save job
                </Button>
                <Button variant="ghost" onClick={onDiscard}>
                  Discard draft
                </Button>
              </div>
            </form>
          </CardBody>
        </Card>
      )}
    </>
  );
}
