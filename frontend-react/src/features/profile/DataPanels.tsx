import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, History, RotateCcw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/form-controls";
import { Alert, Card, CardBody, CardHeader } from "@/components/ui/surface";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { FileDrop } from "@/components/shared/FileDrop";
import { EmptyState, QueryView } from "@/components/shared/states";
import { formatDateTime } from "@/lib/format";
import { errorMessage } from "@/services/api/client";
import { api } from "@/services/api/endpoints";
import { useProfileAction, useProfileVersions, useSaveProfile } from "@/services/api/queries";
import type { MasterProfile, ProfileImportPreview } from "@/services/api/types";

const JSON_RULES = { extensions: [".json"], maxBytes: 1_000_000 };

/** Import a profile JSON: validated by the API first, then saved as a new version only on request. */
export function ImportPanel({ currentVersion }: { currentVersion: number | null }) {
  const [preview, setPreview] = useState<ProfileImportPreview | null>(null);
  const check = useMutation({ mutationFn: api.profile.previewImport, onSuccess: setPreview });
  const save = useSaveProfile();
  return (
    <Card>
      <CardHeader title="Import profile JSON" description="Importing saves a new version. Earlier versions stay in History." />
      <CardBody className="space-y-3">
        <FileDrop rules={JSON_RULES} label="Choose a profile JSON file" hint="JSON only, up to 1 MB." onFile={(f) => check.mutate(f)} disabled={check.isPending} />
        {check.isError && <Alert tone="danger">{errorMessage(check.error)}</Alert>}
        {preview && (
          <Alert
            tone="success"
            title={`Valid profile for ${preview.full_name}`}
            action={
              <Button
                size="sm"
                loading={save.isPending}
                onClick={() =>
                  save.mutate(
                    { profile: preview.profile, expectedVersion: currentVersion },
                    {
                      onSuccess: (out) => {
                        toast.success(`Imported as profile version ${out.profile.profile_version}. Review and confirm it.`);
                        out.notes.forEach((n) => toast.warning(n));
                        setPreview(null);
                      },
                      onError: (e) => toast.error(errorMessage(e)),
                    },
                  )
                }
              >
                Save as new version
              </Button>
            }
          >
            {preview.experience} experience, {preview.projects} projects, {preview.skills} skills.
            {preview.is_sample && " This file is marked as fictional sample data."}
          </Alert>
        )}
      </CardBody>
    </Card>
  );
}

export function ExportAndDeletePanel() {
  const [confirm, setConfirm] = useState(false);
  const remove = useProfileAction(() => api.profile.deleteAll());
  const [exporting, setExporting] = useState(false);
  return (
    <Card>
      <CardHeader title="Export and delete" />
      <CardBody className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">Download the current profile as JSON, for backup or to move it.</p>
          <Button
            variant="secondary"
            loading={exporting}
            onClick={async () => {
              setExporting(true);
              try {
                await api.profile.exportJson();
              } catch (e) {
                toast.error(errorMessage(e));
              } finally {
                setExporting(false);
              }
            }}
          >
            <Download /> Download profile JSON
          </Button>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
          <p className="text-sm text-muted-foreground">Permanently remove the master profile, all its versions, and role profiles from this computer.</p>
          <Button variant="danger" onClick={() => setConfirm(true)}>
            Delete profile data
          </Button>
        </div>
        <ConfirmDialog
          open={confirm}
          onOpenChange={setConfirm}
          title="Delete all profile data?"
          confirmLabel="Delete profile data"
          destructive
          typeToConfirm="DELETE"
          loading={remove.isPending}
          onConfirm={() =>
            remove.mutate(undefined, {
              onSuccess: () => {
                setConfirm(false);
                toast.success("All profile data deleted.");
              },
              onError: (e) => toast.error(errorMessage(e)),
            })
          }
        >
          <p>This removes your master profile, every saved version, and your role profiles. Jobs and resumes are kept. It can't be undone.</p>
        </ConfirmDialog>
      </CardBody>
    </Card>
  );
}

export function HistoryPanel({ profile }: { profile: MasterProfile }) {
  const versions = useProfileVersions();
  const [selected, setSelected] = useState<number | null>(null);
  const snapshot = useQuery({
    queryKey: ["profile", "version", selected],
    queryFn: ({ signal }) => api.profile.version(selected as number, signal),
    enabled: selected !== null,
  });
  const restore = useProfileAction((n: number) => api.profile.restore(n, profile.profile_version));
  return (
    <QueryView query={versions}>
      {(list) =>
        list.length === 0 ? (
          <EmptyState icon={History} title="No saved versions" />
        ) : (
          <Card>
            <CardHeader title="Version history" description="Every save creates an immutable snapshot. Restoring copies a snapshot into a new version." />
            <CardBody className="space-y-4">
              <Select aria-label="Version" value={selected ?? ""} onChange={(e) => setSelected(e.target.value ? Number(e.target.value) : null)}>
                <option value="">Choose a version…</option>
                {list.map((v) => (
                  <option key={v.version} value={v.version} disabled={!v.readable}>
                    v{v.version} · {v.readable ? formatDateTime(v.updated_at) : "unreadable"}
                    {v.version === profile.profile_version ? " · current" : ""}
                  </option>
                ))}
              </Select>
              {selected !== null && (
                <QueryView query={snapshot}>
                  {(snap) => (
                    <div className="space-y-3">
                      <p className="text-sm text-muted-foreground">
                        v{snap.profile_version}: {snap.contact.full_name}, {snap.experience.length} experience, {snap.projects.length} projects,{" "}
                        {snap.skills.length} skills.
                      </p>
                      <details className="rounded-md border">
                        <summary className="cursor-pointer px-3 py-2 text-sm">View contents</summary>
                        <pre className="max-h-80 overflow-auto border-t p-3 text-xs">{JSON.stringify(snap, null, 2)}</pre>
                      </details>
                      <Button
                        variant="secondary"
                        disabled={selected === profile.profile_version}
                        loading={restore.isPending}
                        onClick={() =>
                          restore.mutate(snap.profile_version, {
                            onSuccess: () => toast.success(`Restored v${snap.profile_version} as a new version. Review and confirm it.`),
                            onError: (e) => toast.error(errorMessage(e)),
                          })
                        }
                      >
                        <RotateCcw /> Restore v{selected} as a new version
                      </Button>
                    </div>
                  )}
                </QueryView>
              )}
            </CardBody>
          </Card>
        )
      }
    </QueryView>
  );
}
