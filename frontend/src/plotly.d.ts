declare module "plotly.js-basic-dist-min" {
  export type PlotlyTrace = Record<string, unknown>;
  export type PlotlyLayout = Record<string, unknown>;
  export type PlotlyConfig = Record<string, unknown>;

  interface Plotly {
    react(
      element: HTMLElement,
      data: PlotlyTrace[],
      layout?: PlotlyLayout,
      config?: PlotlyConfig,
    ): Promise<unknown>;
    purge(element: HTMLElement): void;
  }

  const Plotly: Plotly;
  export default Plotly;
}
