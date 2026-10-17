import { z } from "zod";
import { splitList } from "@/lib/format";

/** Client-side mirrors of the profile schema rules for field-level feedback. The API validates again. */

const yearMonth = z
  .string()
  .trim()
  .refine((v) => v === "" || /^\d{4}-(0[1-9]|1[0-2])$/.test(v), "Use YYYY-MM, e.g. 2023-07");

export const optionalEmail = z
  .string()
  .trim()
  .refine((v) => v === "" || /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v), "Enter a valid email, or leave it blank.");

const optionalUrl = z
  .string()
  .trim()
  .refine((v) => v === "" || /^https?:\/\/\S+$/i.test(v), "Enter a full http(s) URL, or leave it blank.");

export const metricsText = z.string().refine((v) => {
  if (!v.trim()) return true;
  return v.split(";").every((part) => !part.trim() || /^[^=]+=.+$/.test(part.trim()));
}, "Write metrics as label=value; label=value");

/** "latency reduction=35%; users=2k" -> [{label, value}] */
export function parseMetrics(text: string): { label: string; value: string; source_note: string }[] {
  return text
    .split(";")
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => {
      const i = p.indexOf("=");
      return { label: p.slice(0, i).trim(), value: p.slice(i + 1).trim(), source_note: "" };
    });
}

export function metricsToText(metrics: { label: string; value: string }[]): string {
  return metrics.map((m) => `${m.label}=${m.value}`).join("; ");
}

export const toList = (text: string) => splitList(text);
export const nullIfBlank = (v: string) => (v.trim() === "" ? null : v.trim());

const endAfterStart = (v: { start_date: string; end_date: string }) => !v.start_date || !v.end_date || v.end_date >= v.start_date;
const END_BEFORE_START = { message: "End is before start", path: ["end_date"] };

export const bulletSchema = z.object({
  id: z.string().optional(),
  text: z.string().trim().min(1, "Write the statement, or remove this bullet."),
  skills: z.string(),
  source_note: z.string(),
  metrics: metricsText,
});

export const experienceSchema = z
  .object({
  employer: z.string().trim().min(1, "Required"),
  title: z.string().trim().min(1, "Required"),
  location: z.string(),
  employment_type: z.string(),
  description: z.string(),
  skills: z.string(),
  source_note: z.string(),
  bullets: z.array(bulletSchema),
    start_date: yearMonth,
    end_date: yearMonth,
  })
  .refine(endAfterStart, END_BEFORE_START);
export type ExperienceValues = z.infer<typeof experienceSchema>;

export const projectSchema = z
  .object({
  name: z.string().trim().min(1, "Required"),
  role: z.string(),
  url: optionalUrl,
  related_experience_id: z.string(),
  description: z.string(),
  skills: z.string(),
  source_note: z.string(),
  bullets: z.array(bulletSchema),
    start_date: yearMonth,
    end_date: yearMonth,
  })
  .refine(endAfterStart, END_BEFORE_START);
export type ProjectValues = z.infer<typeof projectSchema>;

export const educationSchema = z
  .object({
  institution: z.string().trim().min(1, "Required"),
  degree: z.string().trim().min(1, "Required"),
  field_of_study: z.string(),
  location: z.string(),
  grade: z.string(),
  source_note: z.string(),
    start_date: yearMonth,
    end_date: yearMonth,
  })
  .refine(endAfterStart, END_BEFORE_START);
export type EducationValues = z.infer<typeof educationSchema>;

export const certificationSchema = z
  .object({
    name: z.string().trim().min(1, "Required"),
    issuer: z.string(),
    issue_date: yearMonth,
    expiry_date: yearMonth,
    credential_url: optionalUrl,
    source_note: z.string(),
  })
  .refine((v) => !v.issue_date || !v.expiry_date || v.expiry_date >= v.issue_date, { message: "Expiry is before issue", path: ["expiry_date"] });
export type CertificationValues = z.infer<typeof certificationSchema>;

export const achievementSchema = z.object({
  title: z.string().trim().min(1, "Required"),
  description: z.string(),
  date: yearMonth,
  source_note: z.string(),
  metrics: metricsText,
});
export type AchievementValues = z.infer<typeof achievementSchema>;

export const contactSchema = z.object({
  full_name: z.string().trim().min(1, "Your name is required"),
  email: optionalEmail,
  phone: z.string(),
  location: z.string(),
  headline: z.string(),
  summary: z.string(),
  links: z.array(z.object({ id: z.string().optional(), label: z.string().trim().min(1, "Label required"), url: z.string().trim().min(1, "URL required") })),
});
export type ContactValues = z.infer<typeof contactSchema>;

export const skillSchema = z.object({
  name: z.string().trim().min(1, "Required").max(100),
  category: z.enum(["language", "framework", "tool", "platform", "concept", "soft", "other"]),
  aliases: z.string(),
  evidence_ids: z.array(z.string()),
});
export type SkillValues = z.infer<typeof skillSchema>;
