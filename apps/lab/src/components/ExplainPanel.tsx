import { explain, type ExplainerKey } from "@pulselens/explain";

/** A stage's explainer, word for word from EXPLAINERS.md (CLAUDE.md rule 5). */
export function ExplainPanel({ k }: { k: ExplainerKey }) {
  const e = explain(k);
  return (
    <section className="explain-panel" aria-label="Stage explanation">
      <h2>{e.title}</h2>
      {e.what && <p data-field="what">{e.what}</p>}
      {e.why && (
        <p className="why">
          <span className="tag">Why</span> <span data-field="why">{e.why}</span>
        </p>
      )}
      {e.read && (
        <p className="read">
          <span className="tag">How to read it</span> <span data-field="read">{e.read}</span>
        </p>
      )}
    </section>
  );
}
