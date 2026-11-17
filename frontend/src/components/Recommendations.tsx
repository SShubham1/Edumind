import { masteryColor } from "./MasteryChart";
import { percent } from "../format";
import type { Recommendation } from "../types";

const CONTRIBUTION_LABELS: Record<string, string> = {
  low_mastery: "Low mastery",
  revision: "Revision urgency",
  difficulty: "Topic difficulty",
  recent_weakness: "Recent weakness",
};

interface RecommendationsProps {
  recommendations: Recommendation[];
}

export function Recommendations({ recommendations }: RecommendationsProps) {
  if (recommendations.length === 0) {
    return <p className="empty-state">No recommendations yet. Log a quiz result first.</p>;
  }

  const maxScore = Math.max(...recommendations.map((item) => item.score), 0.0001);

  return (
    <ol className="recommendation-list">
      {recommendations.map((item, index) => {
        const contributions = Object.entries(item.contributions);
        return (
          <li key={item.topic_id} className="recommendation">
            <div className="recommendation-head">
              <span className="rank-badge" aria-hidden="true">
                {index + 1}
              </span>
              <div className="recommendation-title">
                <h3>{item.topic_name}</h3>
                <p className="reason">{item.reason}</p>
              </div>
              <span className="score-pill" title="Priority score">
                {item.score.toFixed(2)}
              </span>
            </div>

            <div className="score-track" aria-hidden="true">
              <span
                className="score-fill"
                style={{ width: `${Math.max(6, (item.score / maxScore) * 100)}%` }}
              />
            </div>

            <div className="recommendation-meta">
              <span>
                Mastery{" "}
                <strong style={{ color: masteryColor(item.mastery) }}>
                  {percent(item.mastery)}
                </strong>
              </span>
              <details>
                <summary>Why this rank</summary>
                <dl className="contributions">
                  {contributions.map(([key, value]) => (
                    <div key={key} className="contribution-row">
                      <dt>{CONTRIBUTION_LABELS[key] ?? key}</dt>
                      <dd>
                        <span className="mini-track" aria-hidden="true">
                          <span
                            className="mini-fill"
                            style={{ width: `${Math.min(100, value * 250)}%` }}
                          />
                        </span>
                        {value.toFixed(2)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </details>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
