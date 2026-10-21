import { explain, explainMaybe, type ExplainerKey } from "@pulselens/explain";
import type { CheckResult } from "@pulselens/types";
import { useEffect, useState } from "react";

/** GET /api/sessions/{id}/report (SPEC 6). */
export interface Report {
  status: "none" | "running" | "error" | "done";
  error?: string;
  provisional_thresholds?: boolean;
  qc?: {
    fps: number | null;
    frames: number;
    dropped: number | null;
    acks_ok: number | null;
    pulses: number | null;
    clock_source: string | null;
    browser: string | null;
    face_visible: number | null;
    neck_visible: number | null;
  };
  checks?: CheckResult[];
}

const FAMILIES = ["camera", "optical", "motion", "content", "physiology"] as const;
const STATUS_WORDS = { pass: "Pass", fail: "Fail", abstain: "Not judged", pending: "Pending", running: "Running" } as const;
const pct = (x: number | null | undefined) => (x === null || x === undefined ? "–" : `${Math.round(x * 100)}%`);

async function call(url: string, token: string, method = "GET"): Promise<Report> {
  const r = await fetch(url, { method, headers: { "X-Session-Token": token } });
  if (!r.ok) throw new Error(`${method} ${url} → ${r.status}`);
  return r.json();
}

/** Runs the analysis on the saved session and polls the report every second until it is ready. */
export function useReport(sessionId: string, token: string, pollMs = 1000): Report {
  const [report, setReport] = useState<Report>({ status: "running" });
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const r = await call(`/api/sessions/${sessionId}/report`, token);
        if (!alive) return;
        if (r.status === "running") timer = setTimeout(poll, pollMs);
        else setReport(r);
      } catch (e) {
        if (alive) setReport({ status: "error", error: String(e) });
      }
    };
    call(`/api/sessions/${sessionId}/analyze`, token, "POST").then(poll, (e) => alive && setReport({ status: "error", error: String(e) }));
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [sessionId, token, pollMs]);
  return report;
}

function CheckRow({ c }: { c: CheckResult }) {
  const e = explainMaybe(c.explainer);
  return (
    <details className={`check-row row-${c.status}`} aria-label={e?.title ?? c.check_id}>
      <summary>
        <span className="badge">{STATUS_WORDS[c.status]}</span>
        <span className="check-title">{e?.title ?? c.check_id}</span>
        <span className="check-reason">{c.reason}</span>
      </summary>
      {e?.what && <p>{e.what}</p>}
      {e?.why && (
        <p>
          <span className="tag">Why</span> {e.why}
        </p>
      )}
      {c.status === "abstain" && <p className="muted">{explain("status.abstain").text}</p>}
    </details>
  );
}

/** Lab Record end screen (SPEC 13.3 step 4): QC numbers and a quick status per check, from this session only. */
export function ResultsCard({ report }: { report: Report }) {
  if (report.status === "running") {
    return (
      <section className="card results" aria-label="Results" aria-busy="true">
        <h2>Analysing the recording…</h2>
        <p className="muted">Finding the face in every frame and running each check; this takes about half a minute.</p>
      </section>
    );
  }
  if (report.status !== "done" || !report.qc || !report.checks) {
    return (
      <section className="card results error-card" role="alert" aria-label="Results">
        <h2>Could not analyse this recording</h2>
        <p>{report.error ?? "No analysis yet."}</p>
      </section>
    );
  }
  const { qc, checks } = report;
  const counts = { pass: 0, fail: 0, abstain: 0 };
  for (const c of checks) if (c.status in counts) counts[c.status as keyof typeof counts] += 1;
  return (
    <section className="card results" aria-label="Results">
      <h2>Results</h2>
      <p className="summary">
        <span className="status-pass">{counts.pass} pass</span> · <span className="status-fail">{counts.fail} fail</span> ·{" "}
        <span className="status-abstain">{counts.abstain} not judged</span>
      </p>
      {report.provisional_thresholds && (
        <p className="honesty" role="note">
          <strong>PROVISIONAL THRESHOLDS</strong> {explain("status.provisional").text}
        </p>
      )}
      <dl className="qc" aria-label="Recording quality">
        <div><dt>Frame rate</dt><dd>{qc.fps === null ? "–" : `${qc.fps.toFixed(1)} fps`}</dd></div>
        <div><dt>Frames</dt><dd>{qc.frames}{qc.dropped ? `, ${qc.dropped} dropped` : ""}</dd></div>
        <div><dt>Flashes answered</dt><dd>{qc.acks_ok ?? "–"} of {qc.pulses ?? "–"}</dd></div>
        <div><dt>Face in view</dt><dd>{pct(qc.face_visible)}</dd></div>
        <div><dt>Neck in view</dt><dd>{pct(qc.neck_visible)}</dd></div>
        <div><dt>Browser</dt><dd>{qc.browser ?? "–"}</dd></div>
      </dl>
      {FAMILIES.map((f) => {
        const rows = checks.filter((c) => c.family === f);
        if (!rows.length) return null;
        const fam = explain(`family.${f}` as ExplainerKey);
        return (
          <section key={f} className="family" aria-label={fam.title}>
            <h3>{fam.title}</h3>
            <p className="muted">{fam.text}</p>
            {rows.map((c) => (
              <CheckRow key={c.check_id} c={c} />
            ))}
          </section>
        );
      })}
    </section>
  );
}
