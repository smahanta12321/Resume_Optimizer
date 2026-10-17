import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderPage } from "@/test/utils";
import type { Skill } from "@/services/api/types";
import { SkillForm } from "./skills/SkillsPage";
import { GenerateStep } from "./resumes/GenerateStep";
import { ResumePreview } from "./resumes/ResumePreview";

afterEach(() => vi.unstubAllGlobals());

const python: Skill = { id: "skill-1", name: "Python", category: "language", aliases: [], evidence_ids: [] };
const evidence = [{ id: "exp-1", kind: "experience", label: "Engineer @ Fictional Co", parent_id: null }];

describe("SkillForm", () => {
  it("rejects a duplicate skill name and only offers backend categories", async () => {
    const onSubmit = vi.fn();
    render(<SkillForm others={[python]} evidence={evidence} onSubmit={onSubmit} onCancel={() => undefined} />);
    const options = Array.from((screen.getByLabelText("Category") as HTMLSelectElement).options).map((o) => o.value);
    expect(options).toEqual(["language", "framework", "tool", "platform", "concept", "soft", "other"]);
    await userEvent.type(screen.getByLabelText(/Skill/), "python");
    await userEvent.click(screen.getByRole("button", { name: "Add to draft" }));
    expect(await screen.findByText("You already have a skill with this name.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("links evidence and splits aliases", async () => {
    const onSubmit = vi.fn();
    render(<SkillForm others={[]} evidence={evidence} onSubmit={onSubmit} onCancel={() => undefined} />);
    await userEvent.type(screen.getByLabelText(/Skill/), "Kubernetes");
    await userEvent.type(screen.getByLabelText("Aliases"), "k8s, kube");
    await userEvent.click(screen.getByLabelText("Engineer @ Fictional Co"));
    await userEvent.click(screen.getByRole("button", { name: "Add to draft" }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ name: "Kubernetes", aliases: ["k8s", "kube"], evidence_ids: ["exp-1"] }));
  });
});

const tailoring = (available: boolean) => ({
  job: { id: "job-1" },
  blockers: [],
  stale_reasons: [],
  role_profiles: [],
  recommended_role_id: null,
  role_recommendations: [],
  provider_status: available
    ? { available: true, message: "AI rewriting available via anthropic.", provider: "anthropic", model: "claude-opus-5-5" }
    : { available: false, message: "AI rewriting is off.", provider: "none", model: "" },
  is_sample_profile: false,
});

describe("GenerateStep", () => {
  it("requires consent after showing exactly what would be sent", async () => {
    const api = mockApi({
      "GET /jobs/job-1/tailoring": () => ({ json: tailoring(true) }),
      "POST /jobs/job-1/resumes/ai-preview": () => ({ json: { provider: "anthropic", model: "m", system: "SYSTEM PROMPT", user: "USER CONTENT" } }),
      "POST /jobs/job-1/resumes": () => ({ status: 201, json: { version: { id: "resume-1" }, notes: [], ai_failed: null } }),
    });
    const onGenerated = vi.fn();
    renderPage(<GenerateStep jobId="job-1" onGenerated={onGenerated} />);
    const user = userEvent.setup();
    await user.click(await screen.findByLabelText(/Improve wording with AI/));
    expect(await screen.findByText(/USER CONTENT/)).toBeInTheDocument();
    const generate = screen.getByRole("button", { name: "Generate draft" });
    expect(generate).toBeDisabled();
    await user.click(screen.getByLabelText(/I agree to send this content/));
    await user.click(generate);
    await vi.waitFor(() => expect(onGenerated).toHaveBeenCalledWith("resume-1"));
    expect(api.calls.find((c) => c.path === "/jobs/job-1/resumes")?.body).toMatchObject({ use_ai: true, consent: true });
  });

  it("generates deterministically without offering AI when no provider is configured", async () => {
    const api = mockApi({
      "GET /jobs/job-1/tailoring": () => ({ json: tailoring(false) }),
      "POST /jobs/job-1/resumes": () => ({ status: 201, json: { version: { id: "resume-2" }, notes: [], ai_failed: null } }),
    });
    renderPage(<GenerateStep jobId="job-1" onGenerated={() => undefined} />);
    expect(await screen.findByText("AI rewriting is off.")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Improve wording with AI/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Generate draft" }));
    await vi.waitFor(() => expect(api.calls.some((c) => c.path === "/jobs/job-1/resumes")).toBe(true));
    expect(api.calls.find((c) => c.path === "/jobs/job-1/resumes")?.body).toMatchObject({ use_ai: false });
  });

  it("shows the backend's blocker instead of a generate button", async () => {
    mockApi({ "GET /jobs/job-1/tailoring": () => ({ json: { ...tailoring(false), blockers: ["The match report is out of date."] } }) });
    renderPage(<GenerateStep jobId="job-1" onGenerated={() => undefined} />);
    expect(await screen.findByText("The match report is out of date.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate draft" })).toBeNull();
  });
});

describe("ResumePreview", () => {
  it("renders only the content it was given", () => {
    render(
      <ResumePreview
        content={{
          contact: { full_name: "Fictional Person", email: "person@example.com", phone: "", location: "", links: [] },
          headline: "",
          summary: { text: "", evidence_ids: [], origin: "verbatim", notes: [] },
          skills: [{ name: "Python", evidence_ids: ["exp-1"] }],
          experience: [
            {
              evidence_id: "exp-1",
              kind: "experience",
              title: "Engineer",
              organization: "Fictional Co",
              location: "",
              start_date: "2021-03",
              end_date: null,
              bullets: [{ evidence_ids: ["b-1"], text: "Built pipelines.", source_text: "Built pipelines.", origin: "verbatim", notes: [] }],
            },
          ],
          projects: [],
          education: [],
          certifications: [],
        }}
      />,
    );
    expect(screen.getByRole("heading", { name: "Fictional Person" })).toBeInTheDocument();
    expect(screen.getByText("Built pipelines.")).toBeInTheDocument();
    expect(screen.queryByText("Summary")).toBeNull();
    expect(screen.queryByText("Projects")).toBeNull();
  });
});
