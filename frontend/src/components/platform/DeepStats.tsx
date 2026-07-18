"use client";
import React, { useMemo } from "react";
import { Gauge, ArrowUp, ArrowDown, Minus } from "lucide-react";
import type { RecentMatch, TeamHistoryResponse, CompetitionBenchmarkResponse } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import {
  summarize, consistencyStars, unpredictabilityIndex, percentileFromNormal,
  momentumFor, splitHomeAway, TeamStatSummary, Momentum, getRelevantMatches,
} from "@/lib/teamInsights";
import InfoTooltip from "@/components/platform/InfoTooltip";

const fmt1 = (n: number) => n.toFixed(1);

// --- Percentis ---------------------------------------------------------
function PercentileChip({ label, pct }: { label: string; pct: number }) {
  const tone = pct >= 80 ? "text-emerald-500 border-emerald-500/40 bg-emerald-500/10"
    : pct >= 55 ? "text-cyan-500 border-cyan-500/40 bg-cyan-500/10"
    : pct >= 30 ? "text-amber-500 border-amber-500/40 bg-amber-500/10"
    : "text-red-400 border-red-400/40 bg-red-400/10";
  return (
    <div className={`rounded-lg border px-3 py-2 text-center ${tone}`}>
      <p className="text-lg font-bold font-mono leading-none">{pct}º</p>
      <p className="text-[10px] mt-1 uppercase tracking-wide opacity-80">{label}</p>
    </div>
  );
}

// --- Comparação ofensiva completa (tabela) ------------------------------
type Row = { label: string; hv: number; av: number; suf?: string; lowerBetter?: boolean; d?: number };

function ComparisonTable({ home, away, hs, as }: { home: string; away: string; hs: TeamStatSummary; as: TeamStatSummary }) {
  const rows: Row[] = [
    { label: "Gols marcados", hv: hs.avgGoalsScored, av: as.avgGoalsScored, d: 2 },
    { label: "Gols sofridos", hv: hs.avgGoalsConceded, av: as.avgGoalsConceded, d: 2, lowerBetter: true },
    { label: "Finalizações", hv: hs.avgShots, av: as.avgShots, d: 1 },
    { label: "Chutes a gol", hv: hs.avgShotsOnTarget, av: as.avgShotsOnTarget, d: 1 },
    { label: "Escanteios", hv: hs.avgCorners, av: as.avgCorners, d: 1 },
    { label: "Cartões", hv: hs.avgCards, av: as.avgCards, d: 1, lowerBetter: true },
  ];
  if (hs.avgPossession != null && as.avgPossession != null) {
    rows.push({ label: "Posse de bola", hv: hs.avgPossession, av: as.avgPossession, d: 0, suf: "%" });
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-muted-foreground">
            <th className="text-left font-medium py-1.5">Indicador</th>
            <th className="text-right font-medium py-1.5 text-emerald-500">{teamPt(home)}</th>
            <th className="text-right font-medium py-1.5 text-orange-500">{teamPt(away)}</th>
            <th className="text-right font-medium py-1.5">Melhor</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const hBetter = r.lowerBetter ? r.hv < r.av : r.hv > r.av;
            const tie = Math.abs(r.hv - r.av) < 1e-9;
            const winner = tie ? "—" : hBetter ? teamPt(home) : teamPt(away);
            return (
              <tr key={r.label} className="border-t border-border/30">
                <td className="py-1.5 text-muted-foreground">{r.label}</td>
                <td className={`py-1.5 text-right font-mono ${!tie && hBetter ? "font-bold text-emerald-500" : ""}`}>{r.hv.toFixed(r.d ?? 1)}{r.suf || ""}</td>
                <td className={`py-1.5 text-right font-mono ${!tie && !hBetter ? "font-bold text-orange-500" : ""}`}>{r.av.toFixed(r.d ?? 1)}{r.suf || ""}</td>
                <td className="py-1.5 text-right text-muted-foreground">{winner}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// --- BTTS detalhado -------------------------------------------------------
function BttsPanel({ team, s, accent }: { team: string; s: TeamStatSummary; accent: string }) {
  const items: { label: string; v: number }[] = [
    { label: "Marca", v: s.scoredPct },
    { label: "Sofre", v: s.concededPct },
    { label: "BTTS", v: s.bttsPct },
    { label: "Clean Sheet", v: s.cleanSheetPct },
    { label: "Sem marcar", v: s.failedToScorePct },
  ];
  return (
    <div>
      <p className="text-xs font-semibold mb-2" style={{ color: accent }}>{teamPt(team)}</p>
      <div className="space-y-1.5">
        {items.map((it) => (
          <div key={it.label} className="flex items-center gap-2 text-[11px]">
            <span className="w-20 text-muted-foreground shrink-0">{it.label}</span>
            <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${it.v}%`, backgroundColor: accent }} />
            </div>
            <span className="font-mono w-9 text-right shrink-0">{it.v}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// --- Consistência + imprevisibilidade -------------------------------------
function Stars({ n }: { n: number }) {
  return <span className="tracking-tight">{"★".repeat(n)}{"☆".repeat(5 - n)}</span>;
}

function ConsistencyPanel({ team, s, accent }: { team: string; s: TeamStatSummary; accent: string }) {
  const atk = consistencyStars(s.avgGoalsScored, s.stdGoalsScored);
  const def = consistencyStars(s.avgGoalsConceded, s.stdGoalsConceded);
  const idx = unpredictabilityIndex(s);
  const idxLabel = idx >= 65 ? "Muito imprevisível" : idx >= 35 ? "Moderadamente imprevisível" : "Bastante previsível";
  const idxTone = idx >= 65 ? "text-red-400" : idx >= 35 ? "text-amber-500" : "text-emerald-500";
  return (
    <div className="rounded-lg border border-border/40 p-3">
      <p className="text-xs font-semibold mb-2" style={{ color: accent }}>{teamPt(team)}</p>
      <div className="space-y-1 text-[11px]">
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Consistência do ataque</span>
          <span className="font-mono text-amber-400"><Stars n={atk.stars} /></span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Consistência da defesa</span>
          <span className="font-mono text-amber-400"><Stars n={def.stars} /></span>
        </div>
        <div className="flex items-center justify-between pt-1.5 mt-1 border-t border-border/30">
          <span className="text-muted-foreground">Índice de imprevisibilidade</span>
          <span className={`font-mono font-bold ${idxTone}`}>{idx}%</span>
        </div>
        <p className={`text-[10px] ${idxTone}`}>{idxLabel}</p>
      </div>
    </div>
  );
}

// --- Momentum ---------------------------------------------------------
function MomentumIcon({ momentum, goodIsUp }: { momentum: Momentum; goodIsUp: boolean }) {
  const good = momentum === "stable" ? null : (momentum === "up") === goodIsUp;
  const color = momentum === "stable" ? "text-muted-foreground" : good ? "text-emerald-500" : "text-red-400";
  const Icon = momentum === "up" ? ArrowUp : momentum === "down" ? ArrowDown : Minus;
  return <Icon className={`w-3.5 h-3.5 ${color}`} />;
}

function MomentumPanel({ team, matches, accent, targetCompetition }: { team: string; matches: RecentMatch[]; accent: string; targetCompetition?: string }) {
  const rows = [
    { label: "Ataque", pick: (m: RecentMatch) => m.goals_scored, goodIsUp: true },
    { label: "Defesa (sofridos)", pick: (m: RecentMatch) => m.goals_conceded, goodIsUp: false },
    { label: "Finalizações", pick: (m: RecentMatch) => m.sb_shots || 0, goodIsUp: true },
    { label: "Cartões", pick: (m: RecentMatch) => m.sb_cards || 0, goodIsUp: false },
  ];
  return (
    <div>
      <p className="text-xs font-semibold mb-2" style={{ color: accent }}>{teamPt(team)}</p>
      <div className="space-y-1.5">
        {rows.map((r) => {
          const m = momentumFor(matches, r.pick, targetCompetition);
          return (
            <div key={r.label} className="flex items-center justify-between text-[11px]">
              <span className="text-muted-foreground">{r.label}</span>
              <span className="flex items-center gap-1 font-mono">
                <MomentumIcon momentum={m.momentum} goodIsUp={r.goodIsUp} />
                {fmt1(m.recentAvg)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// --- Casa/Fora (leve) -----------------------------------------------------
function HomeAwaySplit({ team, matches, accent }: { team: string; matches: RecentMatch[]; accent: string }) {
  const { home: h, away: a } = useMemo(() => splitHomeAway(matches), [matches]);
  if (h.n === 0 && a.n === 0) return null;
  return (
    <div className="text-[11px]">
      <p className="font-semibold mb-1" style={{ color: accent }}>{teamPt(team)}</p>
      <div className="flex items-center justify-between text-muted-foreground">
        <span>Em casa ({h.n})</span>
        <span className="font-mono">{h.n ? `${fmt1(h.avgGoalsScored)}–${fmt1(h.avgGoalsConceded)}` : "—"}</span>
      </div>
      <div className="flex items-center justify-between text-muted-foreground">
        <span>Fora ({a.n})</span>
        <span className="font-mono">{a.n ? `${fmt1(a.avgGoalsScored)}–${fmt1(a.avgGoalsConceded)}` : "—"}</span>
      </div>
    </div>
  );
}

export default function DeepStats({ home, away, homeMatches, awayMatches, homeHistory, awayHistory, benchmark, targetCompetition }: {
  home: string; away: string; homeMatches: RecentMatch[]; awayMatches: RecentMatch[];
  homeHistory: TeamHistoryResponse | null; awayHistory: TeamHistoryResponse | null;
  benchmark: CompetitionBenchmarkResponse | null; targetCompetition?: string;
}) {
  const homeMatches10 = useMemo(() => getRelevantMatches(homeMatches || [], targetCompetition, 10), [homeMatches, targetCompetition]);
  const awayMatches10 = useMemo(() => getRelevantMatches(awayMatches || [], targetCompetition, 10), [awayMatches, targetCompetition]);

  const hs = useMemo(() => summarize(homeMatches10), [homeMatches10]);
  const as = useMemo(() => summarize(awayMatches10), [awayMatches10]);
  if (hs.n === 0 && as.n === 0) return null;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-card border border-border/50 rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-3">Comparação Completa</h3>
          <ComparisonTable home={home} away={away} hs={hs} as={as} />
        </div>

        <div className="bg-card border border-border/50 rounded-xl p-5 flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-1.5">
              Momentum
              <InfoTooltip text="Compara a média ponderada dos últimos 10 jogos com os anteriores (limitado a 50), reduzindo o peso de amistosos. Seta verde = melhorando; vermelha = piorando." />
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 mb-4">
              <MomentumPanel team={home} matches={homeMatches} accent="#10b981" targetCompetition={targetCompetition} />
              <MomentumPanel team={away} matches={awayMatches} accent="#f97316" targetCompetition={targetCompetition} />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 pt-3 border-t border-border/30">
            <HomeAwaySplit team={home} matches={homeMatches} accent="#10b981" />
            <HomeAwaySplit team={away} matches={awayMatches} accent="#f97316" />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-card border border-border/50 rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-1.5">
            BTTS Detalhado
            <InfoTooltip text="Frequência (%) em que a equipe marca, sofre, participa de jogos com ambas marcando, mantém a meta invicta ou fica sem marcar, nos jogos recentes." />
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <BttsPanel team={home} s={hs} accent="#10b981" />
            <BttsPanel team={away} s={as} accent="#f97316" />
          </div>
        </div>

        <div className="bg-card border border-border/50 rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-1.5">
            Consistência e Imprevisibilidade
            <InfoTooltip text="Consistência: quanto menor a variação em torno da média de gols, mais estrelas. Imprevisibilidade: combina a variação de gols, cartões e escanteios em um índice de 0 a 100 — quanto maior, mais 'caótica' tende a ser a equipe." />
          </h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <ConsistencyPanel team={home} s={hs} accent="#10b981" />
            <ConsistencyPanel team={away} s={as} accent="#f97316" />
          </div>
        </div>
      </div>
    </div>
  );
}
