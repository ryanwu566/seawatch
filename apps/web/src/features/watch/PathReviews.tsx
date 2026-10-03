import { useState } from "react";
import { getBaseUrl } from "../../api/client";
import { watchApi, type PathReviewDto } from "./api";
import { fmtClock } from "./lib";

/** Advisory path-analysis agent output for the vessels of the selected alert. It never changes the alert; the analyst accepts or rejects it. */
export function PathReviews({ items }: { items: PathReviewDto[] }) {
  const [decided, setDecided] = useState<Record<string, string>>({});
  const [open, setOpen] = useState<string | null>(null);
  if (!items.length) return null;

  const decide = async (id: string, decision: "accepted" | "rejected") => {
    setDecided((d) => ({ ...d, [id]: decision }));
    try {
      await watchApi.decidePathReview(id, decision);
    } catch {
      setDecided((d) => ({ ...d, [id]: "pending" }));
    }
  };

  return (
    <section aria-label="Path review">
      <h3>Path review (advisory)</h3>
      <p className="wf-fine">
        A reviewer looks at the slow stretches of this research-type vessel and says what the movement looks like. It does not change the alert; your
        decision is stored as a training label.
      </p>
      <ul className="wf-pr">
        {items.map((r) => {
          const dec = decided[r.id] ?? r.decision;
          return (
            <li key={r.id} className={`wf-pr-item ${dec}`}>
              <div className="wf-pr-top">
                <b>{r.category.replace(/_/g, " ")}</b>
                <span>
                  {fmtClock(r.t0)} · {Math.round(r.confidence * 100)}% · {r.reviewer}
                </span>
              </div>
              <div>{r.summary}</div>
              {r.second_reader && (
                <div className="wf-fine">
                  Language-model reader {r.second_reader.agrees ? "agrees" : `disagrees (reads it as ${r.second_reader.category.replace(/_/g, " ")})`}.
                </div>
              )}
              <button type="button" className="wf-link" onClick={() => setOpen(open === r.id ? null : r.id)}>
                {open === r.id ? "hide picture and reasons" : "show picture and reasons"}
              </button>
              {open === r.id && (
                <div>
                  <img className="wf-pr-img" alt={`Track of ${r.name}`} src={`${getBaseUrl()}/detection/path-reviews/${encodeURIComponent(r.id)}/image`} />
                  <ul className="wf-bullets">
                    {r.reasons.map((x) => (
                      <li key={x}>{x}</li>
                    ))}
                  </ul>
                  <p className="wf-fine">{r.caveats.join(" ")}</p>
                </div>
              )}
              <div className="wf-pr-actions">
                <button type="button" disabled={dec === "accepted"} onClick={() => void decide(r.id, "accepted")}>
                  {dec === "accepted" ? "Accepted" : "Agree"}
                </button>
                <button type="button" disabled={dec === "rejected"} onClick={() => void decide(r.id, "rejected")}>
                  {dec === "rejected" ? "Rejected" : "Disagree"}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
