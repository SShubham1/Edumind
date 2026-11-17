import { useEffect, useRef } from "react";
import Plotly, { type PlotlyConfig, type PlotlyLayout, type PlotlyTrace } from "plotly.js-basic-dist-min";

interface PlotProps {
  data: PlotlyTrace[];
  layout: PlotlyLayout;
  config?: PlotlyConfig;
  ariaLabel: string;
  className?: string;
}

const BASE_CONFIG: PlotlyConfig = {
  displayModeBar: false,
  responsive: true,
};

export function Plot({ data, layout, config, ariaLabel, className }: PlotProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) {
      return;
    }
    void Plotly.react(element, data, layout, { ...BASE_CONFIG, ...config });
    return () => {
      Plotly.purge(element);
    };
  }, [data, layout, config]);

  return (
    <div
      ref={containerRef}
      className={className ?? "plot"}
      role="img"
      aria-label={ariaLabel}
    />
  );
}
