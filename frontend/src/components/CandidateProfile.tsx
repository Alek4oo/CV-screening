/**
 * Профилът на кандидата — това, върху което е сметнат скорът.
 *
 * Показва се до обяснението нарочно: рекрутерът трябва да може да провери с очи
 * дали парсерът е разбрал CV-то правилно, преди да вземе решение по резултата.
 * Затова и суровият текст от OCR е тук, макар и прибран.
 */

import type { Candidate } from "../api/types";
import { Chips } from "./common";

export function CandidateProfileCard({ candidate }: { candidate: Candidate }) {
  const profile = candidate.profile ?? {};
  const experience = profile.experience ?? [];
  const education = profile.education ?? [];

  return (
    <div className="card">
      <h2>Candidate profile</h2>
      <p className="card-note">
        The structured CV the scoring worked on. Protected attributes (gender, age, origin) take no
        part in the ranking and are not shown here.
      </p>

      <dl className="definition-list">
        <dt>Skills</dt>
        <dd>
          <Chips items={profile.skills ?? []} />
        </dd>
        <dt>Languages</dt>
        <dd>
          <Chips items={profile.languages ?? []} />
        </dd>
      </dl>

      {experience.length > 0 && (
        <>
          <h3 style={{ fontSize: 13.5, marginTop: 16, marginBottom: 6 }}>Experience</h3>
          <ul className="experience-list">
            {experience.map((item, index) => (
              <li key={`${item.title ?? ""}-${item.start ?? index}`}>
                <div>
                  <strong>{item.title ?? "Position"}</strong>
                  {item.company ? ` · ${item.company}` : ""}
                </div>
                <div className="when">
                  {item.start ?? "?"} – {item.current ? "present" : (item.end ?? "?")}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      {education.length > 0 && (
        <>
          <h3 style={{ fontSize: 13.5, marginTop: 16, marginBottom: 6 }}>Education</h3>
          <ul className="experience-list">
            {education.map((item, index) => (
              <li key={`${item.degree ?? ""}-${index}`}>
                <div>
                  <strong>{item.degree ?? "Degree"}</strong>
                  {item.institution ? ` · ${item.institution}` : ""}
                </div>
                {item.year && <div className="when">{item.year}</div>}
              </li>
            ))}
          </ul>
        </>
      )}

      {candidate.raw_text && (
        <details className="raw-text" style={{ marginTop: 16 }}>
          <summary>Raw OCR text ({candidate.raw_text.length} characters)</summary>
          <pre>{candidate.raw_text}</pre>
        </details>
      )}
    </div>
  );
}
