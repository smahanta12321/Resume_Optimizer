import { describe, expect, it } from "vitest";
import { formatMonth, formatPercent, formatRange, humanize, localToday, pluralize, splitList } from "./format";
import { captureTokenFromUrl, clearToken, getToken } from "./session";

describe("format", () => {
  it("formats year-months and ranges", () => {
    expect(formatMonth("2022-07")).toMatch(/2022/);
    expect(formatMonth(null, "?")).toBe("?");
    expect(formatMonth("not-a-month")).toBe("not-a-month");
    expect(formatRange("2022-07", null)).toMatch(/– Present$/);
    expect(formatRange(null, null)).toBe("");
  });

  it("formats percentages without inventing values", () => {
    expect(formatPercent(0.5)).toBe("50%");
    expect(formatPercent(null)).toBe("—");
    expect(formatPercent(undefined)).toBe("—");
  });

  it("humanizes, pluralizes and splits lists", () => {
    expect(humanize("not_documented")).toBe("Not documented");
    expect(pluralize(1, "skill")).toBe("1 skill");
    expect(pluralize(2, "entry", "entries")).toBe("2 entries");
    expect(splitList(" a, b ,, c ")).toEqual(["a", "b", "c"]);
  });

  it("returns today's local date", () => {
    expect(localToday()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});

describe("session", () => {
  it("moves #token from the URL into session storage and strips it", () => {
    window.history.replaceState(null, "", "/jobs?tab=x#token=s3cr%2Bt");
    captureTokenFromUrl();
    expect(getToken()).toBe("s3cr+t");
    expect(window.location.hash).toBe("");
    expect(window.location.search).toBe("?tab=x");
    clearToken();
    expect(getToken()).toBeNull();
  });

  it("ignores URLs without a token", () => {
    window.history.replaceState(null, "", "/#section=1");
    captureTokenFromUrl();
    expect(getToken()).toBeNull();
  });
});
