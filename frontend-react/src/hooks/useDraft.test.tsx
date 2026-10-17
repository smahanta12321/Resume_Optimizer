import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useDraft } from "./useDraft";

describe("useDraft", () => {
  it("adopts new server data while there are no local edits", () => {
    const { result, rerender } = renderHook(({ server }) => useDraft(server), { initialProps: { server: ["a"] } });
    expect(result.current.dirty).toBe(false);
    rerender({ server: ["a", "b"] });
    expect(result.current.draft).toEqual(["a", "b"]);
    expect(result.current.dirty).toBe(false);
  });

  it("keeps the user's edits when server data changes underneath", () => {
    const { result, rerender } = renderHook(({ server }) => useDraft(server), { initialProps: { server: ["a"] } });
    act(() => result.current.setDraft((d) => [...d, "mine"]));
    expect(result.current.dirty).toBe(true);
    rerender({ server: ["a", "theirs"] });
    expect(result.current.draft).toEqual(["a", "mine"]);
    expect(result.current.dirty).toBe(true);
    act(() => result.current.reset());
    expect(result.current.draft).toEqual(["a", "theirs"]);
    expect(result.current.dirty).toBe(false);
  });
});
