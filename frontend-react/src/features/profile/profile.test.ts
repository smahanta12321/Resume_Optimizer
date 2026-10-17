import { describe, expect, it } from "vitest";
import { certificationSchema, contactSchema, experienceSchema, metricsToText, parseMetrics, skillSchema } from "./schemas";
import { tempId, withoutTempIds } from "./SectionEditor";

const experience = {
  employer: "Fictional Co",
  title: "Engineer",
  location: "",
  employment_type: "",
  start_date: "2021-03",
  end_date: "",
  description: "",
  skills: "",
  source_note: "",
  bullets: [],
};

describe("profile schemas", () => {
  it("accepts a valid experience entry", () => {
    expect(experienceSchema.safeParse(experience).success).toBe(true);
  });

  it("rejects bad month formats and end before start", () => {
    const bad = experienceSchema.safeParse({ ...experience, start_date: "03/2021" });
    expect(bad.success).toBe(false);
    const reversed = experienceSchema.safeParse({ ...experience, start_date: "2022-01", end_date: "2021-01" });
    expect(reversed.success).toBe(false);
    expect(reversed.error?.issues[0]?.path).toEqual(["end_date"]);
  });

  it("requires employer and title, and non-empty bullets", () => {
    expect(experienceSchema.safeParse({ ...experience, employer: " " }).success).toBe(false);
    const blankBullet = { text: "", skills: "", source_note: "", metrics: "" };
    expect(experienceSchema.safeParse({ ...experience, bullets: [blankBullet] }).success).toBe(false);
  });

  it("validates metrics syntax", () => {
    const bullet = { text: "Cut latency.", skills: "", source_note: "", metrics: "latency=40%" };
    expect(experienceSchema.safeParse({ ...experience, bullets: [bullet] }).success).toBe(true);
    expect(experienceSchema.safeParse({ ...experience, bullets: [{ ...bullet, metrics: "forty percent" }] }).success).toBe(false);
  });

  it("checks contact email and certification dates", () => {
    const contact = { full_name: "A", email: "nope", phone: "", location: "", headline: "", summary: "", links: [] };
    expect(contactSchema.safeParse(contact).success).toBe(false);
    expect(contactSchema.safeParse({ ...contact, email: "" }).success).toBe(true);
    const cert = { name: "X", issuer: "", issue_date: "2023-05", expiry_date: "2022-05", credential_url: "", source_note: "" };
    expect(certificationSchema.safeParse(cert).success).toBe(false);
  });

  it("only allows the backend's skill categories", () => {
    const skill = { name: "Python", category: "language", aliases: "", evidence_ids: [] };
    expect(skillSchema.safeParse(skill).success).toBe(true);
    expect(skillSchema.safeParse({ ...skill, category: "programming" }).success).toBe(false);
  });
});

describe("metrics text", () => {
  it("round-trips label=value pairs", () => {
    const parsed = parseMetrics(" latency reduction = 35% ; users=2k ;");
    expect(parsed).toEqual([
      { label: "latency reduction", value: "35%", source_note: "" },
      { label: "users", value: "2k", source_note: "" },
    ]);
    expect(metricsToText(parsed)).toBe("latency reduction=35%; users=2k");
  });
});

describe("withoutTempIds", () => {
  it("drops temporary ids at any depth and keeps real ones", () => {
    const out = withoutTempIds({
      experience: [{ id: tempId(), bullets: [{ id: tempId(), text: "new" }, { id: "bullet-1", text: "old" }] }, { id: "exp-1", bullets: [] }],
    });
    expect(out.experience[0]).not.toHaveProperty("id");
    expect(out.experience[0]?.bullets[0]).not.toHaveProperty("id");
    expect(out.experience[0]?.bullets[1]?.id).toBe("bullet-1");
    expect(out.experience[1]?.id).toBe("exp-1");
  });
});
