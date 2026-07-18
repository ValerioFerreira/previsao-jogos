// Funções puras de cálculo para os cartões de "insights" da página de Estatísticas.
// Tudo aqui deriva do que a API já retorna (RecentMatch[], benchmark de competição) —
// nenhuma chamada de rede. Ver frontend/src/app/estatisticas/page.tsx e
// components/platform/{AutoInsights,StyleMatchup,DeepStats}.tsx para o consumo.
import type { RecentMatch } from "./api";

function mean(xs: number[]): number {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;
}
function stdDev(xs: number[]): number {
  if (xs.length < 2) return 0;
  const m = mean(xs);
  return Math.sqrt(mean(xs.map((x) => (x - m) ** 2)));
}
const pct = (n: number, total: number) => (total ? Math.round((100 * n) / total) : 0);

export type TeamStatSummary = {
  n: number;
  avgGoalsScored: number;
  avgGoalsConceded: number;
  avgShots: number;
  avgShotsOnTarget: number;
  avgCorners: number;
  avgCards: number;
  avgFouls: number;
  avgPossession: number | null;
  stdGoalsScored: number;
  stdGoalsConceded: number;
  stdCorners: number;
  stdCards: number;
  bttsPct: number;
  scoredPct: number;
  concededPct: number;
  cleanSheetPct: number;
  failedToScorePct: number;
};

// Resumo estatístico dos jogos recentes de uma equipe (todos os campos derivados de RecentMatch).
export function summarize(matches: RecentMatch[]): TeamStatSummary {
  const ms = matches || [];
  const n = ms.length;
  const gs = ms.map((m) => m.goals_scored);
  const gc = ms.map((m) => m.goals_conceded);
  const corners = ms.map((m) => m.sb_corners ?? 0);
  const cards = ms.map((m) => m.sb_cards ?? 0);
  const poss = ms.map((m) => m.sb_possession).filter((x): x is number => x != null);
  return {
    n,
    avgGoalsScored: mean(gs),
    avgGoalsConceded: mean(gc),
    avgShots: mean(ms.map((m) => m.sb_shots ?? 0)),
    avgShotsOnTarget: mean(ms.map((m) => m.sb_shots_on_target ?? 0)),
    avgCorners: mean(corners),
    avgCards: mean(cards),
    avgFouls: mean(ms.map((m) => m.sb_fouls ?? 0)),
    avgPossession: poss.length ? mean(poss) : null,
    stdGoalsScored: stdDev(gs),
    stdGoalsConceded: stdDev(gc),
    stdCorners: stdDev(corners),
    stdCards: stdDev(cards),
    bttsPct: pct(ms.filter((m) => m.goals_scored > 0 && m.goals_conceded > 0).length, n),
    scoredPct: pct(ms.filter((m) => m.goals_scored > 0).length, n),
    concededPct: pct(ms.filter((m) => m.goals_conceded > 0).length, n),
    cleanSheetPct: pct(ms.filter((m) => m.goals_conceded === 0).length, n),
    failedToScorePct: pct(ms.filter((m) => m.goals_scored === 0).length, n),
  };
}

// Consistência (1–5 estrelas) a partir do coeficiente de variação (desvio/média): quanto
// menor a variação relativa ao redor da média, mais consistente a equipe é nesse quesito.
export function consistencyStars(avg: number, sd: number): { stars: number; label: string } {
  if (avg <= 0.05 && sd <= 0.05) return { stars: 3, label: "Dados insuficientes" };
  const cv = sd / Math.max(avg, 0.15);
  const stars = Math.max(1, Math.min(5, Math.round(5 - cv * 3)));
  const label = stars >= 4 ? "Muito consistente" : stars === 3 ? "Moderadamente consistente" : "Inconsistente";
  return { stars, label };
}

// Índice de imprevisibilidade (0–100), combinando a variabilidade relativa de gols,
// cartões e escanteios. Quanto maior, mais "caótica"/imprevisível costuma ser a equipe.
export function unpredictabilityIndex(s: TeamStatSummary): number {
  const cvGoals = s.stdGoalsScored / Math.max(s.avgGoalsScored, 0.15);
  const cvCards = s.stdCards / Math.max(s.avgCards, 0.15);
  const cvCorners = s.stdCorners / Math.max(s.avgCorners, 0.15);
  const raw = cvGoals * 0.5 + cvCards * 0.25 + cvCorners * 0.25;
  return Math.max(0, Math.min(100, Math.round(raw * 55)));
}

// Aproximação da função erro (Abramowitz & Stegun 7.1.26) — usada para converter
// z-score em percentil (CDF normal) sem depender de nenhuma lib externa.
function erf(x: number): number {
  const sign = x < 0 ? -1 : 1;
  const ax = Math.abs(x);
  const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741, a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
  const t = 1 / (1 + p * ax);
  const y = 1 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-ax * ax);
  return sign * y;
}

// Percentil aproximado (1–99) de `value` numa distribuição normal de média/desvio dados
// (usado com a média/desvio de ataque e defesa da competição, já fornecidos pela API).
export function percentileFromNormal(value: number, meanValue: number, sd: number): number {
  if (!sd || sd <= 0) return 50;
  const z = (value - meanValue) / sd;
  const p = 0.5 * (1 + erf(z / Math.SQRT2));
  return Math.round(Math.max(1, Math.min(99, p * 100)));
}

export type Momentum = "up" | "down" | "stable";
export type MomentumResult = { momentum: Momentum; recentAvg: number; olderAvg: number };

// Momentum: compara a metade mais recente da janela de jogos com a metade mais antiga
// (matches[0] deve ser o jogo mais recente — é como a API já devolve). Precisa de pelo
// menos 4 jogos para ter duas metades minimamente informativas.
export function getMatchWeight(match: RecentMatch, targetCompetition?: string): number {
  const comp = (match.competition || "").toLowerCase();
  const isFriendly = comp.includes("friendly") || comp.includes("amistoso");
  let weight = isFriendly ? 0.35 : 1.0;
  
  if (targetCompetition) {
    const target = targetCompetition.toLowerCase();
    if (comp === target) {
      weight = 1.0;
    }
  }
  return weight;
}

export function getRelevantMatches(matches: RecentMatch[], targetCompetition?: string, count: number = 10): RecentMatch[] {
  const ms = matches || [];
  if (ms.length <= count) return ms;

  const scored = ms.map((m, index) => {
    const recencyScore = 1.0 / (1.0 + 0.05 * index);
    const comp = (m.competition || "").toLowerCase();
    const isFriendly = comp.includes("friendly") || comp.includes("amistoso");
    
    let compMultiplier = 1.0;
    if (targetCompetition) {
      const target = targetCompetition.toLowerCase();
      if (comp === target) {
        compMultiplier = 2.0;
      } else if (isFriendly) {
        compMultiplier = 0.45;
      }
    } else {
      if (isFriendly) {
        compMultiplier = 0.45;
      }
    }
    
    return {
      match: m,
      score: recencyScore * compMultiplier
    };
  });

  scored.sort((a, b) => b.score - a.score);

  const selected = scored.slice(0, count).map((x) => x.match);
  return selected.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
}

export function momentumFor(
  matches: RecentMatch[],
  pick: (m: RecentMatch) => number,
  targetCompetition?: string
): MomentumResult {
  const ms = matches || [];
  const recentCount = Math.min(10, ms.length);
  if (recentCount === 0) {
    return { momentum: "stable", recentAvg: 0, olderAvg: 0 };
  }

  const recentMatches = ms.slice(0, recentCount);
  const olderMatches = ms.slice(recentCount, Math.min(60, ms.length));

  const getWeightedAverage = (subMatches: RecentMatch[]) => {
    if (subMatches.length === 0) return 0;
    let sumVal = 0;
    let sumWeight = 0;
    for (const m of subMatches) {
      const w = getMatchWeight(m, targetCompetition);
      sumVal += pick(m) * w;
      sumWeight += w;
    }
    return sumWeight > 0 ? sumVal / sumWeight : 0;
  };

  const ra = getWeightedAverage(recentMatches);
  let oa = ra;
  if (olderMatches.length > 0) {
    oa = getWeightedAverage(olderMatches);
  }

  const diff = ra - oa;
  const threshold = Math.max(0.15, Math.abs(oa) * 0.1);
  const momentum: Momentum = diff > threshold ? "up" : diff < -threshold ? "down" : "stable";
  return { momentum, recentAvg: ra, olderAvg: oa };
}

// Recorte casa/fora dentro da janela de jogos recentes (força por contexto, versão leve).
export function splitHomeAway(matches: RecentMatch[]): { home: TeamStatSummary; away: TeamStatSummary } {
  const ms = matches || [];
  return { home: summarize(ms.filter((m) => m.is_home)), away: summarize(ms.filter((m) => !m.is_home)) };
}
