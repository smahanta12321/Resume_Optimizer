import { z } from "zod";

/** Mirrors the API's limits for fast feedback; the API re-validates everything. */
export const MAX_JD_CHARS = 50_000;
export const JD_FILE_RULES = { extensions: [".txt", ".md", ".pdf", ".docx"], maxBytes: 5_000_000 };

const optionalUrl = z
  .string()
  .trim()
  .max(2048)
  .refine((v) => v === "" || /^https?:\/\/\S+$/i.test(v), "Enter a full http(s) URL, or leave it blank.");

export const jobReviewSchema = z.object({
  title: z.string().trim().max(200),
  company: z.string().trim().max(200),
  location: z.string().trim().max(200),
  source_url: optionalUrl,
  source_platform: z.enum(["linkedin", "naukri", "other"]),
  source_label: z.string().trim().max(200),
  text: z
    .string()
    .trim()
    .min(1, "The job description is empty.")
    .max(MAX_JD_CHARS, `Keep it under ${MAX_JD_CHARS.toLocaleString()} characters: paste only the posting itself.`),
});
export type JobReviewValues = z.infer<typeof jobReviewSchema>;

export const jobEditSchema = z.object({
  title: z.string().trim().max(200),
  company: z.string().trim().max(200),
  location: z.string().trim().max(200),
  notes: z.string().max(5000),
  description: jobReviewSchema.shape.text,
});
export type JobEditValues = z.infer<typeof jobEditSchema>;
