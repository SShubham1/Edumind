import { useMemo, useState } from "react";
import { Plot } from "./Plot";
import { formatDate, percent } from "../format";
import type { MasteryRow } from "../types";

export function masteryColor(value: number): string {
  if (value < 0.4) return "#D55E00"; // vermillion
  if (value < 0.7) return "#E69F00"; // orange
  return "#009E73"; // bluish green
}

const MAX_BARS = 12;
const LABEL_LIMIT = 34;

function shortLabel(name: string): string {
  return name.length > LABEL_LIMIT
    ? `${name.slice(0, LABEL_LIMIT - 1).trimEnd()}…`
    : name;
}

interface MasteryChartProps {
  rows: MasteryRow[];
  maxBars?: number;
}

export function MasteryChart({ rows, maxBars = MAX_BARS }: MasteryChartProps) {
  const [showTable, setShowTable] = useState(false);

  // Imported subjects can have hundreds of topics, most of which a student has
  // never attempted. Charting them all produces an unreadable wall of bars at
  // the 30% prior, so the chart focuses on attempted topics, weakest first.
  const attempted = useMemo(
    () =>
      rows
        .filter((row) => row.attempts > 0)
        .sort((a, b) => a.mastery - b.mastery || a.topic_name.localeCompare(b.topic_name)),
    [rows],
  );

  const shown = attempted.slice(0, Math.max(maxBars, 1));
  const notStarted = rows.length - attempted.length;

  const data = useMemo(
    () => [
      {
        type: "bar",
        orientation: "h",
        x: shown.map((row) => row.mastery),
        y: shown.map((row) => row.topic_name),
        customdata: shown.map((row) => [row.attempts, row.difficulty]),
        marker: {
          color: shown.map((row) => masteryColor(row.mastery)),
          line: { color: "#0f172a", width: 1 },
        },
        text: shown.map((row) => percent(row.mastery)),
        textposition: "outside",
        cliponaxis: false,
        hovertemplate:
          "<b>%{y}</b><br>Mastery: %{x:.0%}<br>Attempts: %{customdata[0]}<br>" +
          "Difficulty: %{customdata[1]:.2f}<extra></extra>",
      },
    ],
    [shown],
  );

  const layout = useMemo(
    () => ({
      margin: { l: 8, r: 58, t: 8, b: 44 },
      xaxis: {
        range: [0, 1],
        tickformat: ".0%",
        gridcolor: "#e2e8f0",
        zeroline: false,
        title: { text: "Estimated mastery", font: { size: 12 } },
      },
      yaxis: {
        automargin: true,
        autorange: "reversed",
        tickmode: "array",
        tickvals: shown.map((row) => row.topic_name),
        ticktext: shown.map((row) => shortLabel(row.topic_name)),
        tickfont: { size: 11 },
      },
      bargap: 0.32,
      font: { family: "Inter, system-ui, sans-serif", size: 12, color: "#334155" },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      height: Math.max(220, shown.length * 34 + 72),
    }),
    [shown],
  );

  const tableRows = useMemo(
    () =>
      [...rows].sort(
        (a, b) => a.mastery - b.mastery || a.topic_name.localeCompare(b.topic_name),
      ),
    [rows],
  );

  if (rows.length === 0) {
    return <p className="empty-state">No topics yet. Add a topic to begin tracking mastery.</p>;
  }

  return (
    <div className="chart-block">
      {shown.length > 0 ? (
        <Plot
          data={data}
          layout={layout}
          ariaLabel={`Bar chart of the ${shown.length} lowest-mastery topics you have attempted. ${shown
            .map((row) => `${row.topic_name}: ${percent(row.mastery)}`)
            .join(", ")}.`}
        />
      ) : (
        <p className="empty-state">
          No quiz attempts yet, so every topic still sits at the {percent(0.3)} prior.
          Log a quiz result to see topic mastery here.
        </p>
      )}

      {shown.length > 0 && (
        <p className="hint">
          Showing the {shown.length} weakest topic{shown.length === 1 ? "" : "s"} you
          have attempted.
          {attempted.length > shown.length &&
            ` ${attempted.length - shown.length} more attempted topic${
              attempted.length - shown.length === 1 ? "" : "s"
            } are in the table.`}
          {notStarted > 0 &&
            ` ${notStarted} topic${notStarted === 1 ? " has" : "s have"} no attempts yet.`}
        </p>
      )}

      <button
        type="button"
        className="link-button"
        aria-expanded={showTable}
        aria-controls="mastery-data-table"
        onClick={() => setShowTable((value) => !value)}
      >
        {showTable ? "Hide data table" : `View all ${rows.length} topics`}
      </button>
      {showTable && (
        <div className="table-wrap" id="mastery-data-table">
          <table>
            <caption>Estimated mastery per topic, weakest first</caption>
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
              {tableRows.map((row) => (
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
