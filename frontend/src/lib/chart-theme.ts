/** Shared Recharts styling tokens — uses CSS variables for theme consistency. */

export const CHART_HOME = 'hsl(var(--chart-1))';
export const CHART_AWAY = 'hsl(var(--chart-2))';
export const CHART_ACCENT = 'hsl(var(--chart-3))';
export const CHART_WARN = 'hsl(var(--chart-4))';
export const CHART_DANGER = 'hsl(var(--chart-5))';

export const chartGrid = {
  strokeDasharray: '2 6',
  stroke: 'hsl(var(--border))',
  opacity: 0.5,
  vertical: false,
};

export const chartAxisTick = {
  fontSize: 11,
  fill: 'hsl(var(--muted-foreground))',
  fontFamily: 'var(--font-mono)',
};

export const chartAxisLabel = {
  fontSize: 10,
  fill: 'hsl(var(--muted-foreground))',
  fontFamily: 'var(--font-body)',
};

export const chartTooltipStyle = {
  backgroundColor: 'hsl(var(--popover))',
  border: '1px solid hsl(var(--border))',
  borderRadius: '6px',
  fontSize: '12px',
  fontFamily: 'var(--font-body)',
  boxShadow: 'none',
};

export const chartLegendStyle = {
  fontSize: '12px',
  fontFamily: 'var(--font-body)',
};

export const chartMargin = { top: 8, right: 16, bottom: 28, left: 8 };
