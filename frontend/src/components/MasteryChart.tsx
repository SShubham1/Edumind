import { useMemo, useState } from "react";
import { Plot } from "./Plot";
import { formatDate, percent } from "../format";
import type { MasteryRow } from "../types";

export function masteryColor(value: number): string {
  if (value < 0.4) return "#D55E00"; // vermillion
  if (value < 0.7) return "#E69F00"; // orange
  return "#009E73"; // bluish green
}

interface MasteryChartProps {
  rows: MasteryRow[];
}

export function MasteryChart({ rows }: MasteryChartProps) {
  const [showTable, setShowTable] = useState(false);

  const data = useMemo(
    () => [
      {
        type: "bar",
        x: rows.map((row) => row.topic_name),
        y: rows.map((row) => row.mastery),
        customdata: rows.map((row) => row.difficulty),
        marker: {
          color: rows.map((row) => masteryColor(row.mastery)),
          line: { color: "#0f172a", width: 1 },
        },
        text: rows.map((row) => percent(row.mastery)),
        textposition: "outside",
        cliponaxis: false,
        hovertemplate:
          "<b>%{x}</b><br>Mastery: %{y:.0%}<br>Difficulty: %{customdata:.2f}<extra></extra>",
      },
    ],
    [rows],
  );

  const layout = useMemo(
    () => ({
      margin: { l: 48, r: 16, t: 16, b: 72 },
      yaxis: {
        range: [0, 1],
        tickformat: ".0%",
        gridcolor: "#e2e8f0",
        zeroline: false,
        title: { text: "Estimated mastery", font: { size: 12 } },
      },
      xaxis: {
        automargin: true,
        tickangle: rows.length > 4 ? -20 : 0,
      },
      bargap: 0.35,
      font: { family: "Inter, system-ui, sans-serif", size: 12, color: "#334155" },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      height: 320,
    }),
    [rows.length],
  );

  if (rows.length === 0) {
    return <p className="empty-state">No topics yet. Add a topic to begin tracking mastery.</p>;
  }

  return (
    <div className="chart-block">
      <Plot
        data={data}
        layout={layout}
        ariaLabel={`Bar chart of estimated mastery per topic. ${rows
          .map((row) => `${row.topic_name}: ${percent(row.mastery)}`)
          .join(", ")}.`}
      />
      <button
        type="button"
        className="link-button"
        aria-expanded={showTable}
        aria-controls="mastery-data-table"
        onClick={() => setShowTable((value) => !value)}
      >
        {showTable ? "Hide data table" : "View data table"}
      </button>
      {showTable && (
        <div className="table-wrap" id="mastery-data-table">
          <table>
            <caption>Estimated mastery per topic</caption>
            <thead>
              <tr>
                <th scope="col">Topic</th>
                <th scope="col">Mastery</th>
                <th scope="col">Attempts</th>
                <th scope="col">Difficulty</th>
                <th scope="col">Last attempt</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.topic_id}>
                  <th scope="row">{row.topic_name}</th>
                  <td>{percent(row.mastery, 1)}</td>
                  <td>{row.attempts}</td>
                  <td>{row.difficulty.toFixed(2)}</td>
                  <td>{formatDate(row.last_attempt_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
