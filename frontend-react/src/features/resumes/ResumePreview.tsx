import { formatRange } from "@/lib/format";
import type { ResumeContent } from "@/services/api/types";

function Heading({ children }: { children: string }) {
  return <h3 className="mb-1.5 mt-5 border-b border-neutral-300 pb-0.5 text-[0.7rem] font-semibold uppercase tracking-widest text-neutral-600">{children}</h3>;
}

/**
 * Single-column on-screen preview of the resume content. The exported DOCX/PDF are rendered by the
 * backend templates; this is for reading and review, not a pixel match.
 */
export function ResumePreview({ content }: { content: ResumeContent }) {
  const c = content;
  const contact = [c.contact.email, c.contact.phone, c.contact.location, ...c.contact.links.map((l) => l.url)].filter(Boolean);
  return (
    <article
      className="mx-auto max-w-[52rem] rounded-md border bg-white px-6 py-8 text-[0.85rem] leading-relaxed text-neutral-900 shadow-sm sm:px-10"
      aria-label="Resume preview"
    >
      <header className="text-center">
        <h2 className="text-xl font-semibold tracking-tight">{c.contact.full_name}</h2>
        {c.headline && <p className="font-medium text-neutral-700">{c.headline}</p>}
        {contact.length > 0 && <p className="mt-1 break-words text-xs text-neutral-600">{contact.join(" · ")}</p>}
      </header>
      {c.summary.text && (
        <>
          <Heading>Summary</Heading>
          <p>{c.summary.text}</p>
        </>
      )}
      {c.skills.length > 0 && (
        <>
          <Heading>Skills</Heading>
          <p>{c.skills.map((s) => s.name).join(", ")}</p>
        </>
      )}
      {(
        [
          ["Experience", c.experience],
          ["Projects", c.projects],
        ] as const
      ).map(([title, entries]) =>
        entries.length === 0 ? null : (
          <section key={title}>
            <Heading>{title}</Heading>
            <div className="space-y-3">
              {entries.map((e) => (
                <div key={e.evidence_id}>
                  <div className="flex flex-wrap items-baseline justify-between gap-x-4">
                    <p>
                      <strong>{e.title}</strong>
                      {e.organization && <>, {e.organization}</>}
                      {e.location && <span className="text-neutral-600"> · {e.location}</span>}
                    </p>
                    <p className="text-xs text-neutral-600">{formatRange(e.start_date, e.end_date)}</p>
                  </div>
                  <ul className="mt-1 list-disc space-y-0.5 pl-5">
                    {e.bullets.map((b) => (
                      <li key={b.evidence_ids.join(",") + b.text}>{b.text}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </section>
        ),
      )}
      {c.education.length > 0 && (
        <>
          <Heading>Education</Heading>
          <ul className="space-y-1">
            {c.education.map((e) => (
              <li key={e.evidence_id} className="flex flex-wrap justify-between gap-x-4">
                <span>
                  <strong>{e.degree}</strong>
                  {e.field_of_study && <>, {e.field_of_study}</>}, {e.institution}
                </span>
                <span className="text-xs text-neutral-600">{formatRange(e.start_date, e.end_date)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {c.certifications.length > 0 && (
        <>
          <Heading>Certifications</Heading>
          <ul className="list-disc space-y-0.5 pl-5">
            {c.certifications.map((x) => (
              <li key={x.evidence_id}>
                {x.name}
                {x.issuer && <>, {x.issuer}</>}
                {x.issue_date && <> ({x.issue_date})</>}
              </li>
            ))}
          </ul>
        </>
      )}
    </article>
  );
}
