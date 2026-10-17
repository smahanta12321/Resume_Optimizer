import { useEffect, useRef } from "react";
import { useBlocker } from "react-router";
import { ConfirmDialog } from "./ConfirmDialog";

/**
 * Warns before leaving unsaved edits. In-app navigation (including tab/step changes, which live in
 * the query string) shows a dialog; closing or reloading the tab shows the browser's prompt.
 *
 * Call `allowNextNavigation()` right before navigating after a successful save.
 */
export function useUnsavedChanges(when: boolean) {
  // A short window rather than a one-shot flag: the router may evaluate the blocker more than once.
  const bypassUntil = useRef(0);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    if (Date.now() < bypassUntil.current) return false;
    return when && (currentLocation.pathname !== nextLocation.pathname || currentLocation.search !== nextLocation.search);
  });

  useEffect(() => {
    if (!when) return;
    const handler = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [when]);

  const prompt = (
    <ConfirmDialog
      open={blocker.state === "blocked"}
      onOpenChange={(open) => {
        if (!open && blocker.state === "blocked") blocker.reset();
      }}
      title="Discard unsaved changes?"
      confirmLabel="Leave without saving"
      destructive
      onConfirm={() => blocker.state === "blocked" && blocker.proceed()}
    >
      <p>You have edits here that haven't been saved. They'll be lost if you leave now.</p>
    </ConfirmDialog>
  );

  return {
    prompt,
    allowNextNavigation: () => {
      bypassUntil.current = Date.now() + 1000;
    },
  };
}

export function UnsavedChangesGuard({ when }: { when: boolean }) {
  return useUnsavedChanges(when).prompt;
}
