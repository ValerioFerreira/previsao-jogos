"use client";
import React, { useMemo } from "react";
import { Sparkles } from "lucide-react";
import type { RecentMatch, GoalTimingResponse } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import { summarize, momentumFor, consistencyStars, getRelevantMatches } from "@/lib/teamInsights";
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
  targetCompetition?: string,
): string[] {
  const homeMs10 = getRelevantMatches(homeMs, targetCompetition, 10);
  const awayMs10 = getRelevantMatches(awayMs, targetCompetition, 10);
  const hs = summarize(homeMs10), as = summarize(awayMs10);
  const out: { text: string; prio: number }[] = [];
  const hName = teamPt(home), aName = teamPt(away);

  // Momento defensivo/ofensivo recente (V/D nos últimos jogos considerando gols sofridos).
  const hDefMom = momentumFor(homeMs, (m) => m.goals_conceded, targetCompetition);
  const aDefMom = momentumFor(awayMs, (m) => m.goals_conceded, targetCompetition);
  if (hDefMom.momentum === "down" && hs.n >= 4) {
    out.push({ text: `${hName} chega em melhor momento defensivo, sofrendo em média ${hDefMom.recentAvg.toFixed(1)} gol/jogo nos últimos 10 jogos (comparado a ${hDefMom.olderAvg.toFixed(1)} nos anteriores).`, prio: 5 });
  }
  if (aDefMom.momentum === "down" && as.n >= 4) {
    out.push({ text: `${aName} também melhorou defensivamente: ${aDefMom.recentAvg.toFixed(1)} sofrido/jogo recentemente nos últimos 10 jogos, contra ${aDefMom.olderAvg.toFixed(1)} nos anteriores.`, prio: 4 });
  }
  if (aDefMom.momentum === "up" && as.n >= 4) {
    out.push({ text: `${aName} vem sofrendo mais gols recentemente (${aDefMom.recentAvg.toFixed(1)}/jogo nos últimos 10 jogos, ante ${aDefMom.olderAvg.toFixed(1)} nos anteriores) — momento defensivo em queda.`, prio: 4 });
  }
  if (hDefMom.momentum === "up" && hs.n >= 4) {
    out.push({ text: `${hName} vem sofrendo mais gols recentemente (${hDefMom.recentAvg.toFixed(1)}/jogo nos últimos 10 jogos, ante ${hDefMom.olderAvg.toFixed(1)} nos anteriores) — momento defensivo em queda.`, prio: 4 });
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

  // Achados do Radar de Estilo (comparações marcantes entre as equipes).
  if (hs.avgShots >= as.avgShots + 4.5 && hs.n >= 3) {
    out.push({ text: `${hName} apresenta volume ofensivo bastante superior no radar de estilo (média de ${hs.avgShots.toFixed(0)} finalizações/jogo vs ${as.avgShots.toFixed(0)} de ${aName}).`, prio: 4 });
  } else if (as.avgShots >= hs.avgShots + 4.5 && as.n >= 3) {
    out.push({ text: `${aName} apresenta volume ofensivo bastante superior no radar de estilo (média de ${as.avgShots.toFixed(0)} finalizações/jogo vs ${hs.avgShots.toFixed(0)} de ${hName}).`, prio: 4 });
  }

  if (hs.avgGoalsConceded <= as.avgGoalsConceded - 0.5 && hs.n >= 3) {
    out.push({ text: `${hName} destaca-se pela solidez defensiva no radar de estilo, sofrendo significativamente menos gols (${hs.avgGoalsConceded.toFixed(1)}/jogo) que ${aName} (${as.avgGoalsConceded.toFixed(1)}/jogo).`, prio: 4 });
  } else if (as.avgGoalsConceded <= hs.avgGoalsConceded - 0.5 && as.n >= 3) {
    out.push({ text: `${aName} destaca-se pela solidez defensiva no radar de estilo, sofrendo significativamente menos gols (${as.avgGoalsConceded.toFixed(1)}/jogo) que ${hName} (${hs.avgGoalsConceded.toFixed(1)}/jogo).`, prio: 4 });
  }

  if (hs.avgCards >= as.avgCards + 1.2 && hs.n >= 3) {
    out.push({ text: `${hName} possui menor índice de disciplina no radar (${hs.avgCards.toFixed(1)} cartões/jogo), elevando o potencial de sanções na partida.`, prio: 3 });
  } else if (as.avgCards >= hs.avgCards + 1.2 && as.n >= 3) {
    out.push({ text: `${aName} possui menor índice de disciplina no radar (${as.avgCards.toFixed(1)} cartões/jogo), elevando o potencial de sanções na partida.`, prio: 3 });
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

export default function AutoInsights({ home, away, homeMatches, awayMatches, homeTiming, awayTiming, targetCompetition }: {
  home: string; away: string; homeMatches: RecentMatch[]; awayMatches: RecentMatch[];
  homeTiming: GoalTimingResponse | null; awayTiming: GoalTimingResponse | null;
  targetCompetition?: string;
}) {
  const insights = useMemo(
    () => buildInsights(home, away, homeMatches || [], awayMatches || [], homeTiming, awayTiming, targetCompetition),
    [home, away, homeMatches, awayMatches, homeTiming, awayTiming, targetCompetition],
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
