import { useState } from "react";

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/**
 * Local edits on top of server data. While the user has no unsaved edits, newer server data (after a
 * save, or edits made in another window or in Streamlit) replaces the draft; once they start editing,
 * their draft is kept until they save or discard it.
 */
export function useDraft<T>(server: T) {
  const [state, setState] = useState({ base: server, draft: server });
  if (state.base !== server && same(state.draft, state.base)) {
    // Adjusting state while rendering from new props: React's recommended alternative to an effect.
    setState({ base: server, draft: server });
  }
  const draft = state.base !== server && same(state.draft, state.base) ? server : state.draft;
  return {
    draft,
    setDraft: (update: T | ((current: T) => T)) =>
      setState((s) => ({ ...s, draft: typeof update === "function" ? (update as (c: T) => T)(s.draft) : update })),
    dirty: !same(draft, server),
    reset: () => setState({ base: server, draft: server }),
  };
}
