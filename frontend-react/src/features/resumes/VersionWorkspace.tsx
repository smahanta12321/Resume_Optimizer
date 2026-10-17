import { CheckCircle2, Download, Eye, FileCheck2, GitCompareArrows, PencilLine } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input, Textarea } from "@/components/ui/form-controls";
import { Alert, Badge, Card, CardBody, CardHeader } from "@/components/ui/surface";
import { Table, TBody, Td, Th, THead, Tr } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CheckBadge, OriginBadge, VersionStateBadge } from "@/components/shared/badges";
import { EvidenceChips } from "@/components/shared/EvidenceChips";
import { QueryView } from "@/components/shared/states";
import { useUnsavedChanges } from "@/components/shared/UnsavedChanges";
import { formatDateTime, humanize } from "@/lib/format";
import { errorMessage } from "@/services/api/client";
import { api } from "@/services/api/endpoints";
import { useJobAction, useResume, useSettings } from "@/services/api/queries";
import type { BulletEdit, VersionDetail } from "@/services/api/types";
import { ResumePreview } from "./ResumePreview";
import { generatorLabel } from "./VersionTable";

const TABS = ["preview", "changes", "edit", "approve", "export"] as const;
type Tab = (typeof TABS)[number];

/** Review → edit → approve → export for one immutable resume version. */
export function VersionWorkspace({ versionId, onNewVersion }: { versionId: string; onNewVersion: (id: string) => void }) {
  const detail = useResume(versionId);
  const [params, setParams] = useSearchParams();
  const tab = (TABS as readonly string[]).includes(params.get("view") ?? "") ? (params.get("view") as Tab) : "preview";
  const setTab = (v: string) =>
    setParams(
      (p) => {
        p.set("view", v);
        return p;
      },
      { replace: true },
    );

  return (
    <QueryView query={detail}>
      {(d) => (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <VersionStateBadge approved={Boolean(d.version.approved_at)} exported={Boolean(d.export)} />
            <span className="font-mono text-xs">{d.version.id}</span>·<span>{generatorLabel(d.version.generator)}</span>·
            <span>{d.version.target_pages}-page target</span>·<span>{formatDateTime(d.version.created_at)}</span>
            {d.version.parent_id && (
              <>
                ·
                <Link to={`/resumes/${d.version.parent_id}`} className="hover:underline">
                  edited from {d.version.parent_id}
                </Link>
              </>
            )}
          </div>
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="preview">
                <Eye /> Preview
              </TabsTrigger>
              <TabsTrigger value="changes">
                <GitCompareArrows /> Changes & evidence
              </TabsTrigger>
              <TabsTrigger value="edit" disabled={Boolean(d.version.approved_at)}>
                <PencilLine /> Edit
              </TabsTrigger>
              <TabsTrigger value="approve">
                <FileCheck2 /> Checks & approval
                {d.validation && !d.validation.ok && <Badge tone="danger">{d.validation.errors.length}</Badge>}
              </TabsTrigger>
              <TabsTrigger value="export">
                <Download /> Export
              </TabsTrigger>
            </TabsList>
            <TabsContent value="preview">
              {d.version.approved_at && (
                <Alert tone="success" className="mb-3">
                  Approved {formatDateTime(d.version.approved_at)}
                  {d.version.approval_note && `: ${d.version.approval_note}`}
                </Alert>
              )}
              <ResumePreview content={d.version.content} />
            </TabsContent>
            <TabsContent value="changes">
              <ChangesTab d={d} />
            </TabsContent>
            <TabsContent value="edit">
              <EditTab
                key={d.version.id}
                d={d}
                onSaved={(id) => {
                  onNewVersion(id);
                  setTab("approve");
                }}
              />
            </TabsContent>
            <TabsContent value="approve">
              <ApproveTab key={d.version.id} d={d} onApproved={() => setTab("export")} />
            </TabsContent>
            <TabsContent value="export">
              <ExportTab d={d} />
            </TabsContent>
          </Tabs>
        </div>
      )}
    </QueryView>
  );
}

function ChangesTab({ d }: { d: VersionDetail }) {
  const c = d.version.content;
  const notes = [...c.experience, ...c.projects].flatMap((e) => e.bullets.filter((b) => b.notes.length).map((b) => ({ title: e.title, b })));
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader title="What changed from your profile" description="Every line, its origin, and the profile evidence it states." />
        {d.changes.length === 0 ? (
          <CardBody className="text-sm text-muted-foreground">No summary or bullets in this version.</CardBody>
        ) : (
          <Table>
            <THead>
              <tr>
                <Th>Where</Th>
                <Th>Change</Th>
                <Th>Original (profile)</Th>
                <Th>In this resume</Th>
                <Th className="hidden xl:table-cell">Evidence</Th>
              </tr>
            </THead>
            <TBody>
              {d.changes.map((r, i) => (
                <Tr key={i}>
                  <Td className="whitespace-nowrap text-xs">
                    <p className="font-medium">{r.section}</p>
                    <p className="text-muted-foreground">{r.item}</p>
                  </Td>
                  <Td>
                    <Badge tone={r.change === "unchanged" ? "outline" : r.change === "rewritten" ? "primary" : "warning"}>{humanize(r.change)}</Badge>
                  </Td>
                  <Td className="min-w-48 text-muted-foreground">{r.original || "—"}</Td>
                  <Td className="min-w-48">{r.final || "—"}</Td>
                  <Td className="hidden max-w-64 text-xs text-muted-foreground xl:table-cell">{r.evidence}</Td>
                </Tr>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
      {(notes.length > 0 || c.summary.notes.length > 0) && (
        <Alert tone="warning" title="Checker notes">
          {c.summary.notes.length > 0 && <p>Summary: {c.summary.notes.join(" ")}</p>}
          {notes.map(({ title, b }, i) => (
            <p key={i}>
              {title}: “{b.text.slice(0, 70)}” — {b.notes.join(" ")}
            </p>
          ))}
        </Alert>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Skills and their evidence" />
          <ul className="divide-y">
            {c.skills.map((s) => (
              <li key={s.name} className="flex flex-col gap-1 px-4 py-2 sm:flex-row sm:items-center sm:justify-between">
                <span className="text-sm font-medium">{s.name}</span>
                <EvidenceChips ids={s.evidence_ids} />
              </li>
            ))}
            {c.skills.length === 0 && <li className="px-4 py-3 text-sm text-muted-foreground">No skills listed.</li>}
          </ul>
        </Card>
        <Card>
          <CardHeader title="Left out" description="What wasn't included, and why." />
          <CardBody>
            {d.version.omitted.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nothing was left out.</p>
            ) : (
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {d.version.omitted.map((o) => (
                  <li key={o}>{o}</li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

type BulletState = Record<string, { include: boolean; text: string }>;
const bulletKey = (entryId: string, evidenceId: string) => `${entryId}::${evidenceId}`;

function EditTab({ d, onSaved }: { d: VersionDetail; onSaved: (id: string) => void }) {
  const c = d.version.content;
  const entries = [...c.experience, ...c.projects];
  const initial = (): BulletState =>
    Object.fromEntries(
      entries.flatMap((e) => e.bullets.map((b) => [bulletKey(e.evidence_id, b.evidence_ids[0] ?? ""), { include: true, text: b.text }])),
    );
  const [summary, setSummary] = useState(c.summary.text);
  const [bullets, setBullets] = useState<BulletState>(initial);
  const edit = useJobAction(() => {
    const list: BulletEdit[] = entries.flatMap((e) =>
      e.bullets.map((b) => {
        const evidenceId = b.evidence_ids[0] ?? "";
        const s = bullets[bulletKey(e.evidence_id, evidenceId)] ?? { include: true, text: b.text };
        return { entry_id: e.evidence_id, evidence_id: evidenceId, include: s.include, text: s.text };
      }),
    );
    return api.resumes.edit(d.version.id, { summary_text: summary, bullets: list });
  });

  const dirty =
    summary !== c.summary.text ||
    entries.some((e) =>
      e.bullets.some((b) => {
        const s = bullets[bulletKey(e.evidence_id, b.evidence_ids[0] ?? "")];
        return s !== undefined && (!s.include || s.text !== b.text);
      }),
    );
  const unsaved = useUnsavedChanges(dirty);

  if (d.version.approved_at) {
    return <Alert tone="info">Approved versions can't change. Generate a new version to make further edits.</Alert>;
  }

  return (
    <div className="space-y-4">
      {unsaved.prompt}
      <Alert tone="info">
        Saving creates a new version; this one stays unchanged. Titles, employers, dates and education come from your master profile
        and are edited there. Edits that add numbers, skills or tools your evidence doesn't show will fail the checks.
      </Alert>
      <Card>
        <CardHeader title="Summary" />
        <CardBody>
          <Field label="Summary text">{(p) => <Textarea {...p} rows={4} value={summary} onChange={(e) => setSummary(e.target.value)} />}</Field>
        </CardBody>
      </Card>
      {entries.map((e) => (
        <Card key={e.evidence_id}>
          <CardHeader title={e.title} description={[e.organization, humanize(e.kind)].filter(Boolean).join(" · ")} />
          <ul className="divide-y">
            {e.bullets.map((b, i) => {
              const k = bulletKey(e.evidence_id, b.evidence_ids[0] ?? "");
              const s = bullets[k] ?? { include: true, text: b.text };
              const set = (patch: Partial<typeof s>) => setBullets((cur) => ({ ...cur, [k]: { ...s, ...patch } }));
              return (
                <li key={k} className="grid gap-2 px-4 py-3 sm:grid-cols-[auto_1fr]">
                  <Checkbox label={<span className="sr-only">Include bullet {i + 1}</span>} checked={s.include} onChange={(ev) => set({ include: ev.target.checked })} />
                  <div className="space-y-1.5">
                    <Textarea
                      aria-label={`Bullet ${i + 1} of ${e.title}`}
                      rows={2}
                      value={s.text}
                      disabled={!s.include}
                      onChange={(ev) => set({ text: ev.target.value })}
                      className={!s.include ? "line-through" : undefined}
                    />
                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      <OriginBadge origin={b.origin} />
                      <span className="font-mono">{b.evidence_ids.join(", ")}</span>
                      {s.text !== b.source_text && s.include && (
                        <button type="button" className="underline hover:text-foreground" onClick={() => set({ text: b.source_text })}>
                          Restore profile wording
                        </button>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>
      ))}
      <div className="flex gap-2">
        <Button
          disabled={!dirty}
          loading={edit.isPending}
          onClick={() =>
            edit.mutate(undefined, {
              onSuccess: (out) => {
                if (!out.changed) {
                  toast.info("No changes to save.");
                  return;
                }
                toast.success(`Saved your edits as version ${out.version.id}. Check it before approving.`);
                unsaved.allowNextNavigation();
                onSaved(out.version.id);
              },
              onError: (err) => toast.error(errorMessage(err)),
            })
          }
        >
          Save as new version
        </Button>
        <Button
          variant="ghost"
          disabled={!dirty}
          onClick={() => {
            setSummary(c.summary.text);
            setBullets(initial());
          }}
        >
          Undo changes
        </Button>
      </div>
    </div>
  );
}

function ApproveTab({ d, onApproved }: { d: VersionDetail; onApproved: () => void }) {
  const [confirmed, setConfirmed] = useState(false);
  const [note, setNote] = useState("");
  const approve = useJobAction(() => api.resumes.approve(d.version.id, { confirm: true, note }));
  const v = d.validation;

  if (!v) {
    return <Alert tone="warning">Checks need your master profile. Create or import it first.</Alert>;
  }
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Estimated length: about {v.estimated_lines} lines for a {d.version.target_pages}-page target. The exact page count is checked at export.
      </p>
      {v.errors.map((e) => (
        <Alert key={e} tone="danger">
          {e}
        </Alert>
      ))}
      {v.warnings.map((w) => (
        <Alert key={w} tone="warning">
          {w}
        </Alert>
      ))}
      {v.info.map((i) => (
        <Alert key={i} tone="info">
          {i}
        </Alert>
      ))}
      {v.ok && v.warnings.length === 0 && <Alert tone="success">All checks passed.</Alert>}

      {d.version.approved_at ? (
        <Alert tone="success" title="Approved">
          {formatDateTime(d.version.approved_at)}
          {d.version.approval_note && `: ${d.version.approval_note}`}
        </Alert>
      ) : !v.ok ? (
        <p className="text-sm">Fix the errors above (edit this version, or update your master profile and generate again) before approving.</p>
      ) : (
        <Card>
          <CardBody className="space-y-3">
            <Checkbox
              label="I have read this resume and its warnings, and everything in it is accurate."
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            <Field label="Approval note" hint="Optional">
              {(p) => <Input {...p} value={note} onChange={(e) => setNote(e.target.value)} />}
            </Field>
            <Button
              disabled={!confirmed}
              loading={approve.isPending}
              onClick={() =>
                approve.mutate(undefined, {
                  onSuccess: () => {
                    toast.success("Approved. You can now export the DOCX and PDF.");
                    onApproved();
                  },
                  onError: (e) => toast.error(errorMessage(e)),
                })
              }
            >
              <CheckCircle2 /> Approve this version
            </Button>
          </CardBody>
        </Card>
      )}
    </div>
  );
}

function ExportTab({ d }: { d: VersionDetail }) {
  const settings = useSettings();
  const exp = useJobAction(() => api.resumes.exportFiles(d.version.id));
  const [downloading, setDownloading] = useState<"docx" | "pdf" | null>(null);

  if (!d.version.approved_at) {
    return <Alert tone="info">Approve this version on Checks & approval before exporting it.</Alert>;
  }
  const record = d.export;
  const get = async (kind: "docx" | "pdf", name: string) => {
    setDownloading(kind);
    try {
      await api.resumes.downloadFile(d.version.id, kind, name);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title="DOCX and PDF"
          description={
            settings.data
              ? `Single-column, ATS-readable “${settings.data.values.template}” template on ${settings.data.values.page_size} paper. Change these in Settings.`
              : undefined
          }
          actions={
            <Button
              variant={record ? "secondary" : "primary"}
              loading={exp.isPending}
              onClick={() =>
                exp.mutate(undefined, {
                  onSuccess: (out) =>
                    out.failed > 0
                      ? toast.error("Exported, but some checks failed. Review them before using these files.")
                      : toast.success("Exported. Review the checks below."),
                  onError: (e) => toast.error(errorMessage(e)),
                })
              }
            >
              {record ? "Export again" : "Export DOCX and PDF"}
            </Button>
          }
        />
        {record && (
          <CardBody className="space-y-4">
            {record.failed > 0 ? (
              <Alert tone="danger">{record.failed} check(s) failed. Don't send these files until the problems are resolved.</Alert>
            ) : record.warnings > 0 ? (
              <Alert tone="warning">{record.warnings} warning(s). Review them before sending.</Alert>
            ) : (
              <Alert tone="success">All export checks passed.</Alert>
            )}
            <div className="flex flex-wrap gap-2">
              {(
                [
                  ["docx", record.docx_available, record.docx_filename],
                  ["pdf", record.pdf_available, record.pdf_filename],
                ] as const
              ).map(([kind, available, name]) =>
                available ? (
                  <Button key={kind} variant="secondary" loading={downloading === kind} onClick={() => void get(kind, name)}>
                    <Download /> Download {kind.toUpperCase()}
                  </Button>
                ) : (
                  <Alert key={kind} tone="warning">
                    The {kind.toUpperCase()} file is no longer on disk. Export again.
                  </Alert>
                ),
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              PDF: {record.record.pdf_pages ?? "?"} page(s), {record.record.renderer}, {record.record.page_size}
              {record.record.pdf_font && `, font ${record.record.pdf_font}`}. Exported {formatDateTime(record.record.created_at)}.
            </p>
          </CardBody>
        )}
      </Card>
      {record && (
        <Card>
          <CardHeader title="Export checks" description="Text extraction, page count, empty sections and layout, checked on the real files." />
          <Table>
            <THead>
              <tr>
                <Th>Result</Th>
                <Th>File</Th>
                <Th>Check</Th>
                <Th>Detail</Th>
              </tr>
            </THead>
            <TBody>
              {record.record.checks.map((c, i) => (
                <Tr key={i}>
                  <Td>
                    <CheckBadge status={c.status} />
                  </Td>
                  <Td className="text-xs uppercase">{c.file}</Td>
                  <Td>{c.name}</Td>
                  <Td className="text-muted-foreground">{c.detail}</Td>
                </Tr>
              ))}
            </TBody>
          </Table>
        </Card>
      )}
    </div>
  );
}
