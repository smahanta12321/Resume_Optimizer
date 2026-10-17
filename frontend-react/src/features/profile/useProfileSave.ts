import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { errorMessage, isApiError } from "@/services/api/client";
import { keys, useSaveProfile } from "@/services/api/queries";
import type { MasterProfile } from "@/services/api/types";
import { withoutTempIds } from "./SectionEditor";

/**
 * Saves the whole profile with one section replaced, as the Streamlit page does. Each save makes a new
 * immutable version and needs re-confirmation. A version conflict (edited elsewhere meanwhile) is
 * reported, never overwritten.
 */
export function useProfileSave(profile: MasterProfile) {
  const qc = useQueryClient();
  const save = useSaveProfile();

  const saveSection = (patch: Partial<MasterProfile>, opts: { onSaved?: () => void } = {}) =>
    save.mutate(
      { profile: withoutTempIds({ ...profile, ...patch }), expectedVersion: profile.profile_version },
      {
        onSuccess: (out) => {
          if (!out.changed) toast.info("No changes to save.");
          else toast.success(`Saved as profile version ${out.profile.profile_version}. Review and confirm it when you're done.`);
          out.notes.forEach((n) => toast.warning(n));
          opts.onSaved?.();
        },
        onError: (e) => {
          if (isApiError(e, "version_conflict")) {
            toast.error(e.message, {
              duration: Infinity,
              action: { label: "Reload profile", onClick: () => void qc.invalidateQueries({ queryKey: keys.profile }) },
            });
          } else toast.error(errorMessage(e), { duration: 10_000 });
        },
      },
    );

  return { saveSection, saving: save.isPending };
}
