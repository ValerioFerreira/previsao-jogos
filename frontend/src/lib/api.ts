import type { SyntheticEvent } from "react";

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
// Resultado de um mercado derivado: probabilidade (%) + odd justa (nunca < 1,00).
export type DerivedOutcome = { prob: number; odd_justa: number };
export type DerivedMarkets = {
  dupla_chance: Record<string, DerivedOutcome>;
  empate_anula: Record<string, DerivedOutcome>;
  handicap: Record<string, Record<string, DerivedOutcome>>;
  clean_sheet: Record<string, DerivedOutcome>;
  vitoria_sem_sofrer: Record<string, DerivedOutcome>;
  gols_par_impar: Record<string, DerivedOutcome>;
  faixa_gols: Record<string, DerivedOutcome>;
};

export type PlacarMotivo =
  | { tipo: "favoritismo"; favorito_lado: "mandante" | "visitante"; exp_alto: number; exp_baixo: number }
  | { tipo: "placar_alto"; exp_total: number; prob_4_mais: number };

export type PredictionResponse = {
  // Análise aprofundada textual, opcional, feita por admin pra uma partida específica.
  deep_analysis?: { analyst_name: string; markdown_content: string };
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
  // Impedimentos (mandante/visitante/total) — mercado NB exposto cru (sem calibração).
  impedimentos?: Record<string, CountPrediction>;
  // Cartões vermelhos isolados (mandante/visitante/total) — mercado NB exposto cru.
  cartoes_vermelhos?: Record<string, CountPrediction>;
  // Time a marcar primeiro — mandante/visitante/"nenhum" (probabilidade + odd justa).
  time_marca_primeiro?: Record<string, { prob: number; odd_justa: number }>;
  // Mercados derivados: cortes exatos da matriz conjunta do Dixon-Coles / PMFs de gols.
  mercados_derivados?: DerivedMarkets;
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

export type Scope = "selecao" | "clube";

export type PredictPayload = {
  home_team: string;
  away_team: string;
  neutral: boolean;
  tournament: string;
  scope?: Scope;
  home_vals?: Record<string, number>;
  away_vals?: Record<string, number>;
  context_overrides?: Record<string, number>;
  h2h_overrides?: Record<string, number>;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

// Cache em memória (TTL) + deduplicação de chamadas em voo para GETs. Os dados de
// leitura (histórico, h2h, minutagem, benchmark, goleador…) mudam no máximo 1×/dia, então
// reservá-los por alguns minutos evita re-consultas ao banco a cada navegação e junta
// chamadas simultâneas idênticas numa só — reduzindo transfer no Neon e no cliente.
const CACHE_TTL = 5 * 60 * 1000;
const _cache = new Map<string, { ts: number; data: unknown }>();
const _inflight = new Map<string, Promise<unknown>>();

// Invalida o cache (ex.: após uma ação que muda dados). Sem argumento, limpa tudo.
export function clearApiCache(prefix?: string) {
  if (!prefix) { _cache.clear(); return; }
  for (const k of _cache.keys()) if (k.startsWith(prefix)) _cache.delete(k);
}

// `fetch` nativo não tem timeout -- se a conexão cair no meio de um restart do
// backend (Render redeploy/cold start), a requisição fica pendurada indefinidamente
// e a UI nunca sai do estado de "carregando". REQUEST_TIMEOUT_MS força um erro
// tratável depois de um tempo razoável, em vez de spinner eterno.
const REQUEST_TIMEOUT_MS = 20000;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method || "GET").toUpperCase();
  const cacheable = method === "GET";

  if (cacheable) {
    const hit = _cache.get(path);
    if (hit && Date.now() - hit.ts < CACHE_TTL) return hit.data as T;
    const inflight = _inflight.get(path);
    if (inflight) return inflight as Promise<T>;
  }

  const doFetch = (async () => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    let response: Response;
    try {
      response = await fetch(`${API_URL}${path}`, {
        ...init,
        headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
        signal: controller.signal,
      });
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") {
        throw new Error("timeout ao falar com a API.");
      }
      throw new Error("erro de conexão ao falar com a API.");
    } finally {
      clearTimeout(timeoutId);
    }
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new Error(body?.detail || `Erro ${response.status} ao falar com a API.`);
    }
    return response.json();
  })();

  if (!cacheable) return doFetch as Promise<T>;

  _inflight.set(path, doFetch);
  try {
    const data = await doFetch;
    _cache.set(path, { ts: Date.now(), data });
    return data as T;
  } finally {
    _inflight.delete(path);
  }
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
  sb_offsides?: number;
  sb_fouls?: number;
  sb_possession?: number;
  sb_passes?: number;
};

export type CompetitionBenchmarkResponse = {
  attack_mean: number;
  attack_std: number;
  defense_mean: number;
  defense_std: number;
  n_teams: number;
  scope: string;
  team_stats?: Record<string, { attack: number; defense: number }>;
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

export type GoalTimingBlock = { label: string; scored: number; conceded: number };
export type GoalTimingResponse = {
  team: string;
  n_matches: number;
  total_scored: number;
  total_conceded: number;
  blocks: GoalTimingBlock[];
};

export type PmfPreviewResponse = {
  home: string; away: string;
  expected_goals: number | null;
  interval: number[];
  confidence: string | null;
  distribution: number[];
  prob_over_2_5: number | null;
  odd_over_2_5: number | null;
  odd_under_2_5: number | null;
  prob_home: number | null;
  prob_draw: number | null;
  prob_away: number | null;
};

export type InjuryPlayer = { player_id: number | null; name: string | null; reason: string | null; type: string | null };
export type InjuriesResponse = { team: string; season: number | null; players: InjuryPlayer[] };

export type RefereeStatsResponse = {
  referee: string;
  n_matches: number;
  n_card_matches: number;
  n_foul_matches: number;
  avg_yellow: number;
  avg_red: number;
  avg_cards: number;
  avg_fouls: number;
  bench_cards: number;
  bench_fouls: number;
};

export const api = {
  health: () => request<{ status: string; service: string }>("/health"),
  teams: (scope: Scope = "selecao") => request<TeamsResponse>(`/teams?scope=${scope}`),
  team: (name: string, scope: Scope = "selecao") =>
    request<TeamResponse>(`/team/${encodeURIComponent(name)}?scope=${scope}`),
  h2h: (home: string, away: string, scope: Scope = "selecao") =>
    request<H2HResponse>(`/h2h?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}&scope=${scope}`),
  predict: (payload: PredictPayload) =>
    request<PredictionResponse>("/predict", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  systemStatus: () => request<SystemStatusResponse>("/api/system/status"),
  recentMatches: (name: string, scope: Scope = "selecao") =>
    request<RecentMatchesResponse>(`/api/teams/${encodeURIComponent(name)}/recent?scope=${scope}`),
  teamAnomalies: (name: string, scope: Scope = "selecao") =>
    request<AnomaliesResponse>(`/api/teams/${encodeURIComponent(name)}/anomalies?scope=${scope}`),
  teamHistory: (name: string, scope: Scope = "selecao") =>
    request<TeamHistoryResponse>(`/api/teams/${encodeURIComponent(name)}/history?scope=${scope}`),
  goalTiming: (name: string, scope: Scope = "selecao") =>
    request<GoalTimingResponse>(`/api/teams/${encodeURIComponent(name)}/goal-timing?scope=${scope}`),
  refereeStats: (name: string) => request<RefereeStatsResponse>(`/api/referees/${encodeURIComponent(name)}/stats`),
  injuries: (name: string, scope: Scope = "selecao") =>
    request<InjuriesResponse>(`/api/teams/${encodeURIComponent(name)}/injuries?scope=${scope}`),
  pmfPreview: (home: string, away: string, neutral: boolean, tournament: string, scope: Scope = "selecao") =>
    request<PmfPreviewResponse>(`/api/pmf-preview?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}&neutral=${neutral}&tournament=${encodeURIComponent(tournament)}&scope=${scope}`),
  referees: () => request<{ referees: string[] }>("/api/referees"),
  teamIds: (scope: Scope = "selecao") => request<Record<string, number>>(`/api/team-ids?scope=${scope}`),
  competitionBenchmark: (tournament: string, scope: Scope = "selecao") =>
    request<CompetitionBenchmarkResponse>(`/api/competition-benchmark?tournament=${encodeURIComponent(tournament)}&scope=${scope}`),
  upcomingFixtures: () => request<{ fixtures: UpcomingFixture[] }>("/api/fixtures/upcoming"),
  pastFixtures: () => request<{ fixtures: UpcomingFixture[] }>("/api/fixtures/past"),
  matchDetail: (home: string, away: string, date: string) =>
    request<MatchDetail>(`/api/match-detail?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}&date=${encodeURIComponent(date)}`),
  scorers: (home: string, away: string, scope: Scope = "selecao") =>
    request<ScorersResponse>(`/api/scorers?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}&scope=${scope}`),
};

// Prop "jogador a marcar": P(marca | joga) calibrada + odd justa.
export type PropLine = { prob: number; odd_justa: number };
export type ScorerPlayer = {
  player_id: number | null; nome: string; pos: string | null; prob: number; odd_justa: number;
  finalizar?: Record<string, PropLine>;  // { "0.5": {...}, "1.5": {...}, "2.5": {...} }
  assistir?: PropLine;
};
export type ScorersResponse = {
  disponivel: boolean; motivo?: string; info?: string; finalizar_disponivel?: boolean; assistir_disponivel?: boolean;
  [team: string]: boolean | string | ScorerPlayer[] | undefined;
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
  events?: { minute: number | null; extra: number | null; type: string; detail: string; team: string; team_id: number | null; player: string; assist: string | null }[];
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
  league_id?: number | null;
  scope: Scope;
  // Nome do analista, presente se a partida tiver Análise Aprofundada cadastrada no admin.
  deep_analyst?: string;
};

// URL do logo da seleção (api-football media; não conta cota).
export function teamLogoUrl(teamId?: number): string | null {
  return teamId ? `https://media.api-sports.io/football/teams/${teamId}.png` : null;
}

// URL do logo da competição (api-football media; não conta cota).
export function leagueLogoUrl(leagueId?: number | null): string | null {
  return leagueId ? `https://media.api-sports.io/football/leagues/${leagueId}.png` : null;
}

// Handler compartilhado p/ <img onError> de brasão/foto (api-football media). Em dev, o
// primeiro carregamento cross-origin às vezes é abortado (double-render do React) --
// um retry único evita esconder uma imagem válida; só desiste se falhar de novo.
export function onImgError(e: SyntheticEvent<HTMLImageElement>) {
  const img = e.currentTarget;
  if (!img.dataset.retried) {
    img.dataset.retried = "1";
    const src = img.src;
    img.src = "";
    img.src = src;
  } else {
    img.style.display = "none";
  }
}

