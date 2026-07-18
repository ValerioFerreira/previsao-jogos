"use client";
import React, { useMemo } from "react";
import { Sparkles } from "lucide-react";
import type { RecentMatch, GoalTimingResponse } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import { summarize, momentumFor, consistencyStars } from "@/lib/teamInsights";
import InfoTooltip from "@/components/platform/InfoTooltip";

function timingPeak(data: GoalTimingResponse | null, key: "scored" | "conceded"): string | null {
  if (!data || !data.blocks?.length) return null;
  let best = data.blocks[0];
  for (const b of data.blocks) if (b[key] > best[key]) best = b;
  return best[key] > 0 ? best.label : null;
}

function buildInsights(
  home: string, away: string,
  homeMs: RecentMatch[], awayMs: RecentMatch[],
  homeTiming: GoalTimingResponse | null, awayTiming: GoalTimingResponse | null,
): string[] {
  const hs = summarize(homeMs), as = summarize(awayMs);
  const out: { text: string; prio: number }[] = [];
  const hName = teamPt(home), aName = teamPt(away);

  // Momento defensivo/ofensivo recente (V/D nos últimos jogos considerando gols sofridos).
  const hDefMom = momentumFor(homeMs, (m) => m.goals_conceded);
  const aDefMom = momentumFor(awayMs, (m) => m.goals_conceded);
  if (hDefMom.momentum === "down" && hs.n >= 4) {
    out.push({ text: `${hName} chega em melhor momento defensivo, sofrendo em média ${hDefMom.recentAvg.toFixed(1)} gol/jogo nos jogos mais recentes (ante ${hDefMom.olderAvg.toFixed(1)} antes).`, prio: 5 });
  }
  if (aDefMom.momentum === "down" && as.n >= 4) {
    out.push({ text: `${aName} também melhorou defensivamente: ${aDefMom.recentAvg.toFixed(1)} sofrido/jogo recentemente, contra ${aDefMom.olderAvg.toFixed(1)} antes.`, prio: 4 });
  }
  if (aDefMom.momentum === "up" && as.n >= 4) {
    out.push({ text: `${aName} vem sofrendo mais gols recentemente (${aDefMom.recentAvg.toFixed(1)}/jogo, ante ${aDefMom.olderAvg.toFixed(1)}) — momento defensivo em queda.`, prio: 4 });
  }
  if (hDefMom.momentum === "up" && hs.n >= 4) {
    out.push({ text: `${hName} vem sofrendo mais gols recentemente (${hDefMom.recentAvg.toFixed(1)}/jogo, ante ${hDefMom.olderAvg.toFixed(1)}) — momento defensivo em queda.`, prio: 4 });
  }

  // Ataque mais "explosivo" (maior desvio-padrão de gols marcados) x mais consistente.
  const hAtkCons = consistencyStars(hs.avgGoalsScored, hs.stdGoalsScored);
  const aAtkCons = consistencyStars(as.avgGoalsScored, as.stdGoalsScored);
  if (hs.avgGoalsScored > as.avgGoalsScored + 0.3 && hAtkCons.stars <= aAtkCons.stars) {
    out.push({ text: `${hName} tem o ataque mais explosivo (${hs.avgGoalsScored.toFixed(1)} gols/jogo), mas também mais irregular — enquanto ${aName} concede menos espaço aos rivais.`, prio: 3 });
  } else if (as.avgGoalsScored > hs.avgGoalsScored + 0.3 && aAtkCons.stars <= hAtkCons.stars) {
    out.push({ text: `${aName} apresenta um ataque mais explosivo (${as.avgGoalsScored.toFixed(1)} gols/jogo), mas também concede mais espaços defensivos.`, prio: 3 });
  }

  // Minutagem — risco no fim de jogo.
  const hConcededPeak = timingPeak(homeTiming, "conceded");
  const aConcededPeak = timingPeak(awayTiming, "conceded");
  const isLatePeak = (label: string | null) => label === "76-90+";
  if (hConcededPeak && isLatePeak(hConcededPeak)) {
    out.push({ text: `O maior risco para ${hName} está nos minutos finais (${hConcededPeak}′), período em que mais sofre gols historicamente.`, prio: 4 });
  }
  if (aConcededPeak && isLatePeak(aConcededPeak)) {
    out.push({ text: `${aName} também concentra boa parte dos gols sofridos nos minutos finais (${aConcededPeak}′) — atenção à reta final do jogo.`, prio: 3 });
  }

  // Chances de poucas finalizações cedidas: ataque forte de um lado x poucas finalizações do outro.
  if (hs.avgShots > as.avgShots + 4) {
    out.push({ text: `Tendência de poucas finalizações cedidas por ${aName} (${as.avgShots.toFixed(0)}/jogo), o que pode reduzir o potencial ofensivo de ${hName} apesar do volume de jogo.`, prio: 2 });
  } else if (as.avgShots > hs.avgShots + 4) {
    out.push({ text: `Tendência de poucas finalizações cedidas por ${hName} (${hs.avgShots.toFixed(0)}/jogo), o que pode reduzir o potencial ofensivo de ${aName} apesar do volume de jogo.`, prio: 2 });
  }

  // BTTS como conclusão de fechamento.
  if (hs.bttsPct >= 60 && as.bttsPct >= 60) {
    out.push({ text: `Ambas as equipes marcam com frequência (BTTS em ${hs.bttsPct}% dos jogos de ${hName} e ${as.bttsPct}% dos de ${aName}) — cenário favorável a "Ambas Marcam".`, prio: 2 });
  } else if (hs.cleanSheetPct >= 50 || as.cleanSheetPct >= 50) {
    const solid = hs.cleanSheetPct >= as.cleanSheetPct ? hName : aName;
    const pctv = Math.max(hs.cleanSheetPct, as.cleanSheetPct);
    out.push({ text: `${solid} mantém a meta invicta em ${pctv}% dos jogos recentes — defesa sólida reduz o cenário de "Ambas Marcam".`, prio: 2 });
  }

  return out.sort((a, b) => b.prio - a.prio).slice(0, 5).map((x) => x.text);
}

export default function AutoInsights({ home, away, homeMatches, awayMatches, homeTiming, awayTiming }: {
  home: string; away: string; homeMatches: RecentMatch[]; awayMatches: RecentMatch[];
  homeTiming: GoalTimingResponse | null; awayTiming: GoalTimingResponse | null;
}) {
  const insights = useMemo(
    () => buildInsights(home, away, homeMatches || [], awayMatches || [], homeTiming, awayTiming),
    [home, away, homeMatches, awayMatches, homeTiming, awayTiming],
  );
  if (insights.length === 0) return null;
  return (
    <div className="bg-gradient-to-br from-cyan-500/10 via-card to-card border border-cyan-500/30 rounded-xl p-5">
      <h3 className="text-sm font-semibold mb-3 flex items-center gap-1.5">
        <Sparkles className="w-4 h-4 text-cyan-500" />
        Principais Conclusões
        <InfoTooltip text="Leitura automática combinando momento recente, minutagem de gols, consistência e tendência de BTTS das duas equipes — um resumo do que os números abaixo significam na prática." />
      </h3>
      <ul className="space-y-1.5">
        {insights.map((text, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-cyan-500 shrink-0" />
            <span className="text-foreground/90 leading-relaxed">{text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
