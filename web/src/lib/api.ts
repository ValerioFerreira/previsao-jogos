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

export type PredictionResponse = {
  vencedor: {
    vencedor: string;
    confianca: number;
    probabilidades: Record<string, number>;
  };
  gols: NumericPrediction;
  chutes: NumericPrediction;
  escanteios: Record<string, NumericPrediction>;
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
};

