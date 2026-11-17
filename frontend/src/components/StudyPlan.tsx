import { useState } from "react";
import { api } from "../api";
import { formatDateTime } from "../format";
import type { StudyPlan as StudyPlanType } from "../types";

interface StudyPlanProps {
  studentId: number;
  subject?: string | null;
}

export function StudyPlan({ studentId, subject }: StudyPlanProps) {
  const [plan, setPlan] = useState<StudyPlanType | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setLoading(true);
    setError(null);
    try {
      setPlan(await api.generateStudyPlan(studentId, subject));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate a study plan.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="plan-panel">
      <div className="plan-actions">
        <button type="button" className="button primary" onClick={generate} disabled={loading}>
          {loading ? "Generating…" : plan ? "Regenerate plan" : "Generate study plan"}
        </button>
        <p className="hint">
          The language model runs on the server; without an API key a deterministic plan is used.
        </p>
      </div>

      <div aria-live="polite">
        {error && (
          <p className="alert error" role="alert">
            {error}
          </p>
        )}

        {plan && (
          <article className="plan-result">
            <header>
              <span className={`badge ${plan.source === "llm" ? "badge-ai" : "badge-fallback"}`}>
                {plan.source === "llm" ? "AI generated" : "Offline fallback"}
              </span>
              <span className="timestamp">Generated {formatDateTime(plan.generated_at)}</span>
            </header>
            <pre className="plan-text">{plan.plan}</pre>
          </article>
        )}

        {!plan && !error && !loading && (
          <p className="empty-state">
            Generate a short, prioritised plan from the ranked topics above. It refreshes after new
            quiz results are recorded.
          </p>
        )}
      </div>
    </div>
  );
}
