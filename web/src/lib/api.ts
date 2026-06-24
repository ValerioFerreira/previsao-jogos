export type TeamResponse = {
  team: string;
  defaults: Record<string, number>;
  bases: string[];
};

export type TeamsResponse = {
  teams: string[];
  tournaments: string[];
};

export type H2HResponse = {
  home: string;
  away: string;
  summary: string;
  metrics: Record<string, number | string | null>;
};

export type NumericPrediction = {
  estimativa: number;
  intervalo: [number, number];
  confianca: "Alta" | "Media" | "Média" | "Baixa" | string;
};

// Odd justa direta de uma face (over/under) de uma linha, derivada da CDF real.
export type LineOdds = {
  prob: number;
  odd_justa: number;
};

export type OverUnderLine = {
  over: LineOdds;
  under: LineOdds;
};

// Mercado de contagem com distribuicao propria (PMF) e grade completa de linhas O/U.
// Vale para chutes, escanteios (mandante/visitante/total) e cartoes (idem).
export type CountPrediction = NumericPrediction & {
  distribuicao: number[];
  linhas: Record<string, OverUnderLine>;
};

export type PredictionResponse = {
  vencedor: {
    vencedor: string;
    confianca: number;
    probabilidades: Record<string, number>;
  };
  gols: NumericPrediction;
  chutes: CountPrediction;
  // Chutes divididos por equipe (mandante/visitante) e chutes a gol (mand/vis/total).
  chutes_equipe?: Record<string, CountPrediction>;
  chutes_a_gol?: Record<string, CountPrediction>;
  escanteios: Record<string, CountPrediction>;
  cartoes: Record<string, CountPrediction>;
  // Tier de confiabilidade do jogo pela cobertura de dados refinados (box-score).
  confiabilidade?: {
    tier: string;                 // "Alta" | "Média" | "Baixa"
    score: number;
    cobertura_mandante: number;
    cobertura_visitante: number;
    _resumo: string;
  };
  ambas_marcam: {
    resposta: string;
    confianca: number;
    prob_sim: number;
  };
  over_2_5: {
    resposta: string;
    confianca: number;
    prob_sim: number;
  };
  confronto_direto: string;
  odds: OddsBlock;
};

export type OddsRange = {
  min: number;
  max: number;
};

export type OddsMarket = {
  probabilidade: number;
  odd_justa: number;
  faixa_odd_justa: OddsRange;
  intervalo_probabilidade_80: [number, number];
};

export type NumericLineMarket =
  | {
      disponivel: false;
      motivo: string;
    }
  | {
      disponivel: true;
      linha: number;
      metodo: string;
      over: OddsMarket;
      under: OddsMarket;
    };

export type OddsBlock = {
  vencedor: Record<string, OddsMarket>;
  ambas_marcam: {
    sim: OddsMarket;
    nao: OddsMarket;
  };
  over_under_2_5: {
    sim: OddsMarket;
    nao: OddsMarket;
  };
  linhas_numericas: {
    gols: NumericLineMarket;
    chutes: NumericLineMarket;
    escanteios: Record<string, NumericLineMarket>;
    cartoes: Record<string, NumericLineMarket>;
  };
  nota: string;
};

export type PredictPayload = {
  home_team: string;
  away_team: string;
  neutral: boolean;
  tournament: string;
  home_vals?: Record<string, number>;
  away_vals?: Record<string, number>;
  context_overrides?: Record<string, number>;
  h2h_overrides?: Record<string, number>;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `Erro ${response.status} ao falar com a API.`);
  }

  return response.json() as Promise<T>;
}

export type SystemStatusResponse = {
  last_successful_run: string;
};

export type RecentMatch = {
  date: string;
  opponent: string;
  is_home: boolean;
  goals_scored: number;
  goals_conceded: number;
  sb_shots: number;
  sb_shots_on_target: number;
  sb_corners: number;
  sb_cards: number;
};

export type RecentMatchesResponse = {
  team: string;
  matches: RecentMatch[];
  total_matches: number;
};

export type Anomaly = {
  stat: string;
  z_score: number;
  window_size: number;
  message: string;
  type: string;
};

export type AnomaliesResponse = {
  team: string;
  anomalies: Anomaly[];
};

export type EloHistoryPoint = {
  date: string;
  elo: number;
};

export type FrequencyPoint = {
  label: string;
  frequency: number;
};

export type TeamHistoryResponse = {
  team: string;
  elo_history: EloHistoryPoint[];
  attack_avg: number;
  defense_avg: number;
  corners_freq: FrequencyPoint[];
  cards_freq: FrequencyPoint[];
};

export const api = {
  health: () => request<{ status: string; service: string }>("/health"),
  teams: () => request<TeamsResponse>("/teams"),
  team: (name: string) => request<TeamResponse>(`/team/${encodeURIComponent(name)}`),
  h2h: (home: string, away: string) =>
    request<H2HResponse>(`/h2h?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}`),
  predict: (payload: PredictPayload) =>
    request<PredictionResponse>("/predict", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  systemStatus: () => request<SystemStatusResponse>("/api/system/status"),
  recentMatches: (name: string) => request<RecentMatchesResponse>(`/api/teams/${encodeURIComponent(name)}/recent`),
  teamAnomalies: (name: string) => request<AnomaliesResponse>(`/api/teams/${encodeURIComponent(name)}/anomalies`),
  teamHistory: (name: string) => request<TeamHistoryResponse>(`/api/teams/${encodeURIComponent(name)}/history`),
};

