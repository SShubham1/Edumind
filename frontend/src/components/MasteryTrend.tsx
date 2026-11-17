import { useMemo, useState } from "react";
import { Plot } from "./Plot";
import { formatDateTime, percent } from "../format";
import type { MasteryHistoryPoint, MasteryRow } from "../types";

const PALETTE = [
  "#0072B2",
  "#D55E00",
  "#009E73",
  "#CC79A7",
  "#E69F00",
  "#56B4E9",
  "#8C564B",
  "#1F2937",
];

const DASHES = ["solid", "dot", "dash", "dashdot", "longdash", "longdashdot"];

interface MasteryTrendProps {
  points: MasteryHistoryPoint[];
  rows: MasteryRow[];
  maxSeries?: number;
}

export function MasteryTrend({ points, rows, maxSeries = 8 }: MasteryTrendProps) {
  const [showTable, setShowTable] = useState(false);

  const topicNames = useMemo(
    () => new Map(rows.map((row) => [row.topic_id, row.topic_name])),
    [rows],
  );

  const { data, hiddenCount } = useMemo(() => {
    const grouped = new Map<number, MasteryHistoryPoint[]>();
    for (const point of points) {
      const bucket = grouped.get(point.topic_id);
      if (bucket) {
        bucket.push(point);
      } else {
        grouped.set(point.topic_id, [point]);
      }
    }

    // A 100-topic subject would otherwise draw 100 overlapping lines. Show the
    // topics with the most history; the data table still lists every point.
    const entries = [...grouped.entries()].sort(
      (a, b) => b[1].length - a[1].length,
    );
    const shown = entries.slice(0, Math.max(maxSeries, 1));

    return {
      data: shown.map(([topicId, topicPoints], index) => {
        const name = topicNames.get(topicId) ?? `Topic ${topicId}`;
        const color = PALETTE[index % PALETTE.length];
        return {
          type: "scatter",
          mode: "lines+markers",
          name,
          x: topicPoints.map((point) => point.created_at),
          y: topicPoints.map((point) => point.mastery),
          line: { color, width: 2, dash: DASHES[index % DASHES.length] },
          marker: { color, size: 7, line: { color: "#ffffff", width: 1 } },
          hovertemplate: `<b>${name}</b><br>%{x|%d %b %Y}<br>Mastery: %{y:.1%}<extra></extra>`,
        };
      }),
      hiddenCount: entries.length - shown.length,
    };
  }, [points, topicNames, maxSeries]);

  const layout = useMemo(
    () => ({
      margin: { l: 48, r: 16, t: 16, b: 48 },
      yaxis: {
        range: [0, 1],
        tickformat: ".0%",
        gridcolor: "#e2e8f0",
        zeroline: false,
        title: { text: "Mastery", font: { size: 12 } },
      },
      xaxis: {
        type: "date",
        gridcolor: "#f1f5f9",
        tickformat: "%d %b",
      },
      hovermode: "closest",
      showlegend: true,
      legend: { orientation: "h", y: -0.25, font: { size: 11 } },
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

  return (
    <div className="chart-block">
      <Plot
        data={data}
        layout={layout}
        ariaLabel={`Line chart of mastery over time for ${data.length} topic${
          data.length === 1 ? "" : "s"
        }.`}
      />
      {hiddenCount > 0 && (
        <p className="hint">
          Showing the {data.length} topics with the most history; {hiddenCount} more
          {hiddenCount === 1 ? " has" : " have"} snapshots. The data table below lists every
          point.
        </p>
      )}
      <button
        type="button"
        className="link-button"
        aria-expanded={showTable}
        aria-controls="trend-data-table"
        onClick={() => setShowTable((value) => !value)}
      >
        {showTable ? "Hide data table" : "View data table"}
      </button>
      {showTable && (
        <div className="table-wrap" id="trend-data-table">
          <table>
            <caption>Mastery snapshots over time</caption>
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
