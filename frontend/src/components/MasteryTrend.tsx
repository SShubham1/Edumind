import { useMemo, useState } from "react";
import { Plot } from "./Plot";
import { formatDateTime, percent } from "../format";
import type { MasteryHistoryPoint, MasteryRow } from "../types";

interface MasteryTrendProps {
  points: MasteryHistoryPoint[];
  rows: MasteryRow[];
}

interface TrendPoint {
  date: string;
  average: number;
  topics: number;
}

/**
 * Turn sparse per-topic snapshots into one readable series.
 *
 * Imported histories give each topic only one or two snapshots, so drawing a
 * line per topic produces disconnected stubs. Instead, walk the days that have
 * snapshots, forward-fill each topic's latest mastery, and average across the
 * topics attempted so far. That is the number the "overall mastery" card
 * approximates, shown as a trend.
 */
function buildTrend(points: MasteryHistoryPoint[]): TrendPoint[] {
  const byDay = new Map<string, MasteryHistoryPoint[]>();
  for (const point of points) {
    const day = point.created_at.slice(0, 10);
    const bucket = byDay.get(day);
    if (bucket) {
      bucket.push(point);
    } else {
      byDay.set(day, [point]);
    }
  }

  const latest = new Map<number, number>();
  const trend: TrendPoint[] = [];
  for (const day of [...byDay.keys()].sort()) {
    const dayPoints = [...(byDay.get(day) ?? [])].sort((a, b) =>
      a.created_at.localeCompare(b.created_at),
    );
    for (const point of dayPoints) {
      latest.set(point.topic_id, point.mastery);
    }
    const values = [...latest.values()];
    trend.push({
      date: `${day}T00:00:00`,
      average: values.reduce((sum, value) => sum + value, 0) / values.length,
      topics: values.length,
    });
  }
  return trend;
}

export function MasteryTrend({ points, rows }: MasteryTrendProps) {
  const [showTable, setShowTable] = useState(false);

  const topicNames = useMemo(
    () => new Map(rows.map((row) => [row.topic_id, row.topic_name])),
    [rows],
  );

  const trend = useMemo(() => buildTrend(points), [points]);
  const attemptedTopics = useMemo(
    () => new Set(points.map((point) => point.topic_id)).size,
    [points],
  );

  const data = useMemo(
    () => [
      {
        type: "scatter",
        mode: "lines+markers",
        name: "Average mastery",
        x: trend.map((point) => point.date),
        y: trend.map((point) => point.average),
        customdata: trend.map((point) => point.topics),
        line: { color: "#4338ca", width: 2.5 },
        marker: {
          size: 6,
          color: "#4338ca",
          line: { color: "#ffffff", width: 1 },
        },
        fill: "tozeroy",
        fillcolor: "rgba(67, 56, 202, 0.08)",
        hovertemplate:
          "<b>%{x|%d %b %Y}</b><br>Average mastery: %{y:.1%}<br>" +
          "Topics tracked: %{customdata}<extra></extra>",
      },
    ],
    [trend],
  );

  const layout = useMemo(
    () => ({
      margin: { l: 48, r: 16, t: 16, b: 48 },
      yaxis: {
        range: [0, 1],
        tickformat: ".0%",
        gridcolor: "#e2e8f0",
        zeroline: false,
        title: { text: "Average mastery", font: { size: 12 } },
      },
      xaxis: {
        type: "date",
        gridcolor: "#f1f5f9",
        tickformat: "%d %b",
      },
      hovermode: "x",
      showlegend: false,
      font: { family: "Inter, system-ui, sans-serif", size: 12, color: "#334155" },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      height: 340,
    }),
    [],
  );

  if (points.length === 0) {
    return (
      <p className="empty-state">
        No quiz history yet. Submit a quiz result to start the mastery trend.
      </p>
    );
  }

  const first = trend[0];
  const last = trend[trend.length - 1];

  return (
    <div className="chart-block">
      <Plot
        data={data}
        layout={layout}
        ariaLabel={`Line chart of average mastery over ${trend.length} day${
          trend.length === 1 ? "" : "s"
        }, from ${percent(first.average)} to ${percent(last.average)} across ${attemptedTopics} attempted topic${
          attemptedTopics === 1 ? "" : "s"
        }.`}
      />
      <p className="hint">
        Average mastery across the {attemptedTopics} topic
        {attemptedTopics === 1 ? "" : "s"} you have attempted so far, using each
        topic&apos;s latest snapshot on every day with new activity. A topic entering
        the average for the first time can pull the line down.
      </p>
      <button
        type="button"
        className="link-button"
        aria-expanded={showTable}
        aria-controls="trend-data-table"
        onClick={() => setShowTable((value) => !value)}
      >
        {showTable ? "Hide data table" : "View snapshot data"}
      </button>
      {showTable && (
        <div className="table-wrap" id="trend-data-table">
          <table>
            <caption>Mastery snapshots over time, newest first</caption>
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Topic</th>
                <th scope="col">Mastery</th>
                <th scope="col">Source</th>
              </tr>
            </thead>
            <tbody>
              {[...points].reverse().map((point, index) => (
                <tr key={`${point.topic_id}-${point.created_at}-${index}`}>
                  <td>{formatDateTime(point.created_at)}</td>
                  <th scope="row">{topicNames.get(point.topic_id) ?? `Topic ${point.topic_id}`}</th>
                  <td>{percent(point.mastery, 1)}</td>
                  <td>{point.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
