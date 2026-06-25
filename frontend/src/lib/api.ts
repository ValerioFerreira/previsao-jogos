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

// Motivo estruturado do alerta de desvio do Placar Exato (texto montado no front
// em PT-BR; o lado favorito vira teamPt(home)/teamPt(away)).
export type PlacarMotivo =
  | { tipo: "favoritismo"; favorito_lado: "mandante" | "visitante"; exp_alto: number; exp_baixo: number }
  | { tipo: "placar_alto"; exp_total: number; prob_4_mais: number };

export type PredictionResponse = {
  vencedor: {
    vencedor: string;
    confianca: number;
    probabilidades: Record<string, number>;
  };
  gols: NumericPrediction;
  // Gols por equipe (mandante/visitante) — marginais da conjunta do Dixon-Coles.
  gols_equipe?: Record<string, CountPrediction>;
  chutes: CountPrediction;
  // Chutes divididos por equipe (mandante/visitante) e chutes a gol (mand/vis/total).
  chutes_equipe?: Record<string, CountPrediction>;
  chutes_a_gol?: Record<string, CountPrediction>;
  escanteios: Record<string, CountPrediction>;
  cartoes: Record<string, CountPrediction>;
  // Mercados por tempo (1º/2º): cada chave (gols_1t, gols_2t, cartoes_1t, cartoes_2t)
  // é um mapa {mandante, visitante, total} -> CountPrediction.
  tempos?: Record<string, Record<string, CountPrediction>>;
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
  // Placar exato: 3 placares mais prováveis (top-3 da matriz conjunta DC) + alerta
  // de potencial de desvio (placar fora do padrão). Os motivos vêm estruturados
  // (sem nome cru do time) para o front montar o texto em PT-BR com teamPt.
  placar_exato?: {
    top: { mandante: number; visitante: number; prob: number }[];
    alerta: {
      nivel: "normal" | "moderado" | "alto";
      supremacia_gols: number;
      prob_4_mais: number;
      exp_mandante: number;
      exp_visitante: number;
      motivos: PlacarMotivo[];
    };
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
  competition?: string;
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

export type GoalTrendPoint = {
  label: string;
  scored: number;
  conceded: number;
};

export type TeamHistoryResponse = {
  team: string;
  elo_history: EloHistoryPoint[];
  goal_trend?: GoalTrendPoint[];
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
  referees: () => request<{ referees: string[] }>("/api/referees"),
  teamIds: () => request<Record<string, number>>("/api/team-ids"),
  upcomingFixtures: () => request<{ fixtures: UpcomingFixture[] }>("/api/fixtures/upcoming"),
  pastFixtures: () => request<{ fixtures: UpcomingFixture[] }>("/api/fixtures/past"),
  matchDetail: (home: string, away: string, date: string) =>
    request<MatchDetail>(`/api/match-detail?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}&date=${encodeURIComponent(date)}`),
};

export type LineupPlayer = { id: number | null; name: string; number: number | null; pos: string | null; grid: string | null };
export type MatchPlayer = {
  id: number | null; name: string; pos: string | null; number: number | null;
  rating: string | null; minutes: number | null; goals: number | null; assists: number | null;
  shots_total: number | null; shots_on: number | null; passes: number | null; key_passes: number | null;
  tackles: number | null; yellow: number | null; red: number | null;
};
export type MatchDetail = {
  found: boolean;
  info?: {
    date: string; status: string | null; referee: string | null; venue: string | null; city: string | null;
    league: string | null; league_logo: string | null; country: string | null; season: number | null; round: string | null;
    home: string | null; home_id: number | null; away: string | null; away_id: number | null;
  };
  goals?: { home: number | null; away: number | null };
  score?: { halftime?: { home: number | null; away: number | null }; fulltime?: any; extratime?: any; penalty?: any };
  statistics?: { team: string; team_id: number; stats: Record<string, string | number | null> }[];
  events?: { minute: number | null; extra: number | null; type: string; detail: string; team: string; player: string; assist: string | null }[];
  lineups?: { team: string; team_id: number; formation: string | null; coach: { id: number | null; name: string | null }; startXI: LineupPlayer[]; substitutes: LineupPlayer[] }[];
  players?: { team: string; team_id: number; players: MatchPlayer[] }[];
};

// Foto do jogador (api-football media; não conta cota).
export function playerPhotoUrl(playerId?: number | null): string | null {
  return playerId ? `https://media.api-sports.io/football/players/${playerId}.png` : null;
}

export type UpcomingFixture = {
  fixture_id: string;
  home: string;
  away: string;
  tournament: string;
  neutral: boolean;
  date: string;
  league_name: string;
};

// URL do logo da seleção (api-football media; não conta cota).
export function teamLogoUrl(teamId?: number): string | null {
  return teamId ? `https://media.api-sports.io/football/teams/${teamId}.png` : null;
}

