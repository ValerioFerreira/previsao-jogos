"use client";
import React, { useMemo } from "react";
import { Swords } from "lucide-react";
import type { RecentMatch } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import { summarize, TeamStatSummary } from "@/lib/teamInsights";
import InfoTooltip from "@/components/platform/InfoTooltip";

// Compara ataque de uma equipe com a defesa da outra e devolve frases de "confronto de estilos".
function buildCompatibility(hName: string, aName: string, hs: TeamStatSummary, as: TeamStatSummary): string[] {
  const out: string[] = [];
  if (hs.n === 0 || as.n === 0) return out;

  if (hs.avgShots >= as.avgShots + 3) {
    out.push(`${hName} cria muito mais volume ofensivo (${hs.avgShots.toFixed(0)} finalizações/jogo) do que ${aName} costuma sofrer bem — pressão constante sobre a defesa visitante.`);
  }
  if (as.avgGoalsConceded <= 1.0 && hs.avgGoalsScored >= 1.5) {
    out.push(`${aName} sofre poucos gols (${as.avgGoalsConceded.toFixed(1)}/jogo), o que reduz parte da vantagem ofensiva de ${hName} (${hs.avgGoalsScored.toFixed(1)} gols/jogo).`);
  }
  if (hs.avgCorners >= as.avgCorners + 2) {
    out.push(`${hName} usa muito mais escanteios (${hs.avgCorners.toFixed(0)}/jogo) do que ${aName} — confronto que tende a favorecer bolas paradas para o lado de ${hName}.`);
  }
  if (as.avgCards >= hs.avgCards + 1) {
    out.push(`${aName} costuma jogar em um ritmo mais faltoso/cartões (${as.avgCards.toFixed(1)}/jogo) — pode dar mais espaço para bolas paradas de ${hName}.`);
  }
  if (as.avgShots >= hs.avgShots + 3) {
    out.push(`${aName} cria muito mais volume ofensivo (${as.avgShots.toFixed(0)} finalizações/jogo) do que ${hName} costuma sofrer bem — pressão constante sobre a defesa mandante.`);
  }
  if (hs.avgGoalsConceded <= 1.0 && as.avgGoalsScored >= 1.5) {
    out.push(`${hName} sofre poucos gols (${hs.avgGoalsConceded.toFixed(1)}/jogo), o que reduz parte da vantagem ofensiva de ${aName} (${as.avgGoalsScored.toFixed(1)} gols/jogo).`);
  }
  if (out.length === 0) {
    out.push(`${hName} e ${aName} têm perfis ofensivo/defensivo parecidos nos jogos recentes — confronto equilibrado, sem vantagem estatística clara de estilo.`);
  }
  return out.slice(0, 4);
}

function MatchupBar({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const w = Math.max(4, Math.min(100, (value / Math.max(max, 0.01)) * 100));
  return (
    <div className="mb-2 last:mb-0">
      <div className="flex items-center justify-between text-[11px] mb-0.5">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono font-semibold">{value.toFixed(2)}</span>
      </div>
      <div className="h-2.5 rounded-full bg-muted overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${w}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

function Direction({ attacker, defender, atkStats, defStats }: {
  attacker: string; defender: string; atkStats: TeamStatSummary; defStats: TeamStatSummary;
}) {
  const max = Math.max(atkStats.avgGoalsScored, defStats.avgGoalsConceded, 1.5) * 1.2;
  const diff = atkStats.avgGoalsScored - defStats.avgGoalsConceded;
  const verdict = diff > 0.35 ? { text: "Ataque tende a superar a defesa", tone: "text-emerald-500" }
    : diff < -0.35 ? { text: "Defesa tende a conter o ataque", tone: "text-red-400" }
    : { text: "Equilíbrio entre ataque e defesa", tone: "text-amber-500" };
  return (
    <div className="rounded-lg border border-border/40 p-3">
      <p className="text-xs font-medium mb-2">
        Ataque <span className="text-emerald-500">{teamPt(attacker)}</span> vs Defesa <span className="text-orange-500">{teamPt(defender)}</span>
      </p>
      <MatchupBar label={`Gols esperados — ${teamPt(attacker)}`} value={atkStats.avgGoalsScored} max={max} color="#10b981" />
      <MatchupBar label={`Gols sofridos — ${teamPt(defender)}`} value={defStats.avgGoalsConceded} max={max} color="#f97316" />
      <p className={`text-[11px] font-medium mt-2 ${verdict.tone}`}>→ {verdict.text}</p>
    </div>
  );
}

export default function StyleMatchup({ home, away, homeMatches, awayMatches }: {
  home: string; away: string; homeMatches: RecentMatch[]; awayMatches: RecentMatch[];
}) {
  const hs = useMemo(() => summarize(homeMatches || []), [homeMatches]);
  const as = useMemo(() => summarize(awayMatches || []), [awayMatches]);
  const bullets = useMemo(() => buildCompatibility(teamPt(home), teamPt(away), hs, as), [home, away, hs, as]);
  if (hs.n === 0 && as.n === 0) return null;

  return (
    <div className="bg-card border border-border/50 rounded-xl p-5">
      <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
        <Swords className="w-4 h-4 text-violet-500" />
        Como Estes Estilos Se Enfrentam
        <InfoTooltip text="Compara o volume ofensivo de uma equipe com a solidez defensiva da outra (finalizações, escanteios, cartões, gols sofridos) para apontar qual lado tende a levar vantagem no confronto de estilos." />
      </h3>
      <ul className="space-y-1.5 mb-4">
        {bullets.map((text, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-violet-500 shrink-0" />
            <span className="text-foreground/90 leading-relaxed">{text}</span>
          </li>
        ))}
      </ul>

      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">Matchup Ataque × Defesa</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Direction attacker={home} defender={away} atkStats={hs} defStats={as} />
        <Direction attacker={away} defender={home} atkStats={as} defStats={hs} />
      </div>
    </div>
  );
}
