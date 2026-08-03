"use client";
import React, { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { DerivedMarkets, DerivedOutcome, PredictionResponse, CountPrediction, teamLogoUrl, onImgError } from "@/lib/api";
import InfoTooltip from "@/components/platform/InfoTooltip";
import { teamPt } from "@/lib/teamNames";
import { fairOddRange, overProb } from "@/components/platform/MarketCard";

type DProps = { d: DerivedMarkets; home: string; away: string };
type Outcome = { label: string; o?: DerivedOutcome; color?: string };

// Card de números centrados — coerente com o card "Ambas Marcam" (poucas saídas).
export function DerivedBigCard({ title, tip, outcomes }: { title: string; tip: string; outcomes: Outcome[] }) {
  const valid = outcomes.filter((x) => x.o);
  if (valid.length === 0) return null;
  return (
    <div className="bg-card border border-border/50 rounded-xl p-5 flex flex-col h-full">
      <h4 className="text-sm font-semibold mb-3 flex items-center justify-center gap-1.5">{title}<InfoTooltip text={tip} /></h4>
      <div className="flex-1 flex flex-wrap items-center justify-center gap-x-6 gap-y-3 sm:gap-x-8 text-center">
        {valid.map(({ label, o, color }) => (
          <div key={label}>
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">{label}</p>
            <p className={`text-2xl font-mono font-bold ${color ?? "text-emerald-400"}`}>{o!.prob.toFixed(1)}%</p>
            <p className="text-[10px] text-muted-foreground mt-1">odd justa: {o!.odd_justa.toFixed(2)}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// Card compacto em linhas — para mercados com muitas saídas (handicap).
export function DerivedRowsCard({ title, tip, rows }: { title: string; tip: string; rows: Outcome[] }) {
  const valid = rows.filter((r) => r.o);
  if (valid.length === 0) return null;
  return (
    <div className="bg-card border border-border/50 rounded-xl p-5 flex flex-col h-full">
      <h4 className="text-sm font-semibold mb-2 flex items-center justify-center gap-1.5">{title}<InfoTooltip text={tip} /></h4>
      <div className="flex-1 flex flex-col justify-center">
        {valid.map(({ label, o }) => (
          <div key={label} className="flex items-center justify-between text-xs py-1.5 border-t border-border/20 first:border-t-0">
            <span className="text-muted-foreground truncate mr-2">{label}</span>
            <span className="flex items-baseline gap-2 shrink-0">
              <span className="font-mono font-bold text-emerald-400">{o!.prob.toFixed(1)}%</span>
              <span className="font-mono text-[10px] text-muted-foreground">odd {o!.odd_justa.toFixed(2)}</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---- Cards individuais (posicionáveis livremente nas seções da página) ----
export function DuplaChanceCard({ d, home, away }: DProps) {
  const H = teamPt(home), A = teamPt(away);
  return <DerivedBigCard title="Dupla Chance" tip="O palpite vence em dois dos três resultados possíveis (1X, 12 ou X2)." outcomes={[
    { label: `${H} ou Empate`, o: d.dupla_chance[`${home} ou Empate`], color: "text-emerald-400" },
    { label: `${H} ou ${A}`, o: d.dupla_chance[`${home} ou ${away}`], color: "text-foreground" },
    { label: `Empate ou ${A}`, o: d.dupla_chance[`Empate ou ${away}`], color: "text-cyan-400" },
  ]} />;
}

export function TimeAMarcarPrimeiroCard({ d, home, away }: { d: any; home: string; away: string }) {
  return <DerivedBigCard title="Time a Marcar Primeiro" tip="Probabilidade de cada time marcar o 1º gol da partida (ou de a partida terminar sem gols)." outcomes={[
    { label: teamPt(home), o: d[home], color: "text-emerald-400" },
    { label: teamPt(away), o: d[away], color: "text-blue-400" },
    { label: "Nenhum (0x0)", o: d.nenhum, color: "text-muted-foreground" },
  ]} />;
}

export function EmpateAnulaCard({ d, home, away }: DProps) {
  return <DerivedBigCard title="Empate Anula (DNB)" tip="Seleção no vencedor; se a partida empatar, o valor é devolvido." outcomes={[
    { label: teamPt(home), o: d.empate_anula[home], color: "text-emerald-400" },
    { label: teamPt(away), o: d.empate_anula[away], color: "text-cyan-400" },
  ]} />;
}

export function HandicapCard({ d, team, label }: { d: DerivedMarkets; team: string; label: string }) {
  const m = d.handicap?.[team] ?? {};
  const rows = Object.keys(m)
    .sort((a, b) => Number(a) - Number(b))
    .map((k) => ({ label: `${Number(k) > 0 ? "+" : ""}${k}`, o: m[k] }));
  return <DerivedRowsCard title={`Handicap — ${label}`} tip="Vantagem/desvantagem de gols aplicada à equipe (linhas .5, sem empate)." rows={rows} />;
}

// Handicaps das duas equipes num único card; cada coluna traz o nome e, abaixo, a bandeira.
export function HandicapsCard({ d, home, away, teamIds }: DProps & { teamIds: Record<string, number> }) {
  const lines = (team: string) => {
    const m = d.handicap?.[team] ?? {};
    return Object.keys(m).sort((a, b) => Number(a) - Number(b)).map((k) => ({ key: k, label: `${Number(k) > 0 ? "+" : ""}${k}`, o: m[k] }));
  };
  return (
    <div className="bg-card border border-border/50 rounded-xl p-5 flex flex-col h-full">
      <h4 className="text-sm font-semibold mb-3 flex items-center justify-center gap-1.5">
        Handicaps
        <InfoTooltip text={'O Handicap de Gols é um mercado que adiciona uma vantagem ou desvantagem fictícia a uma equipe antes do início da partida. Após aplicar esse handicap ao placar final, é determinado se a seleção foi validada.\n\nExemplo: Brasil -1,5 x Argentina. Se você selecionar o Brasil -1,5, ele precisa vencer por 2 ou mais gols de diferença (2x0, 3x1, 4x2...). Se vencer por apenas 1 gol, empatar ou perder, a seleção não é validada. Já quem seleciona a Argentina +1,5 tem sua seleção validada se a Argentina empatar, vencer ou perder por apenas 1 gol.'} />
      </h4>
      <div className="grid grid-cols-2 gap-4 flex-1">
        {[home, away].map((team) => (
          <div key={team}>
            <div className="flex flex-col items-center mb-2">
              <span className="text-xs font-semibold leading-tight text-center truncate max-w-full">{teamPt(team)}</span>
              {teamLogoUrl(teamIds[team]) && (
                <img src={teamLogoUrl(teamIds[team])!} alt="" className="w-6 h-6 object-contain mt-1" loading="lazy" onError={onImgError} />
              )}
            </div>
            {/* Cabeçalho das colunas */}
            <div className="grid grid-cols-[1.2fr_1fr_1fr] text-[9px] uppercase tracking-wide text-muted-foreground/80 pb-1 border-b border-border/40 text-right">
              <span className="text-left">Linha</span>
              <span>Prob.</span>
              <span>Odd Justa</span>
            </div>
            {lines(team).map(({ key, label, o }) => (
              <div key={key} className="grid grid-cols-[1.2fr_1fr_1fr] text-xs py-1 border-t border-border/20 text-right items-center">
                <span className="text-left text-muted-foreground">{label}</span>
                <span className="font-mono font-bold text-emerald-400">{o ? `${o.prob.toFixed(1)}%` : "—"}</span>
                <span className="font-mono text-[10px] text-muted-foreground">{o ? o.odd_justa.toFixed(2) : ""}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function ParImparCard({ d }: { d: DerivedMarkets }) {
  return <DerivedBigCard title="Total de Gols Par/Ímpar" tip="Paridade do total de gols da partida." outcomes={[
    { label: "Par", o: d.gols_par_impar["Par"], color: "text-emerald-400" },
    { label: "Ímpar", o: d.gols_par_impar["Ímpar"], color: "text-blue-400" },
  ]} />;
}

export function FaixaGolsCard({ d }: { d: DerivedMarkets }) {
  return <DerivedBigCard title="Faixa de Gols" tip="Total de gols da partida dentro de cada faixa." outcomes={[
    { label: "0 a 1", o: d.faixa_gols["0-1"] },
    { label: "2 a 3", o: d.faixa_gols["2-3"] },
    { label: "4 a 6", o: d.faixa_gols["4-6"] },
    { label: "7 ou +", o: d.faixa_gols["7+"] },
  ]} />;
}

export function CleanSheetCard({ d, home, away }: DProps) {
  return <DerivedBigCard title="Não Sofrer Gol" tip="A equipe termina a partida sem sofrer gols (clean sheet)." outcomes={[
    { label: teamPt(home), o: d.clean_sheet[home], color: "text-emerald-400" },
    { label: teamPt(away), o: d.clean_sheet[away], color: "text-cyan-400" },
  ]} />;
}

export function VitoriaSemSofrerCard({ d, home, away }: DProps) {
  return <DerivedBigCard title="Vitória sem Sofrer Gols" tip="A equipe vence a partida sem sofrer nenhum gol." outcomes={[
    { label: teamPt(home), o: d.vitoria_sem_sofrer[home], color: "text-emerald-400" },
    { label: teamPt(away), o: d.vitoria_sem_sofrer[away], color: "text-cyan-400" },
  ]} />;
}

// Qualificação/agregado em mata-mata ida-e-volta (só competições continentais de
// clube que jogam em 2 pernas — ver KNOCKOUT_TOURNAMENTS no backend). Mandante da
// análise = mandante da ida; visitante = mandante da volta (mando invertido).
// probA + probB soma sempre 100% (empate no agregado é dividido 50/50 entre os dois
// lados, ver predictor.py::predict_aggregate) — a barra de comparação usa isso direto.
export function MataMataAgregadoCard({ d, teamIds }: { d: NonNullable<PredictionResponse["mata_mata_agregado"]>; teamIds?: Record<string, number> }) {
  const { leg1_mandante: a, leg2_mandante: b } = d;
  const probA = d.qualifica[a]?.prob ?? 0;
  const probB = d.qualifica[b]?.prob ?? 0;
  const aIsFav = probA >= probB;
  const topScore = d.placar_agregado_top[0];

  const sides = [
    { team: a, prob: probA, odd: d.qualifica[a]?.odd_justa, fav: aIsFav,
      ring: "border-emerald-500/50 bg-emerald-500/5 shadow-[0_0_22px_-6px_rgba(16,185,129,0.45)]",
      text: "text-emerald-400" },
    { team: b, prob: probB, odd: d.qualifica[b]?.odd_justa, fav: !aIsFav,
      ring: "border-cyan-500/50 bg-cyan-500/5 shadow-[0_0_22px_-6px_rgba(34,211,238,0.45)]",
      text: "text-cyan-400" },
  ];

  const favoriteName = teamPt(aIsFav ? a : b);
  const favoriteProb = Math.max(probA, probB);
  const resumo = `${favoriteName} chega como favorito para avançar, com ${favoriteProb.toFixed(1)}% de probabilidade `
    + `de classificação. O modelo projeta expectativa de ${d.gols_agregados.estimativa.toFixed(1)} gols ao longo `
    + `das duas partidas`
    + (d.empate_agregado_prob >= 5 ? ` e cerca de ${d.empate_agregado_prob.toFixed(1)}% de chance de decisão na prorrogação.` : ".");

  return (
    <div className="bg-card border border-border/50 rounded-xl p-5 flex flex-col h-full">
      <h4 className="text-sm font-semibold mb-1 flex items-center justify-center gap-1.5">
        Chance de Classificação
        <InfoTooltip text={d._nota} />
      </h4>
      <p className="text-[11px] text-muted-foreground text-center mb-4">
        1º jogo: {teamPt(a)} (Casa) · 2º jogo: {teamPt(b)} (Casa)
      </p>

      <div className="grid grid-cols-2 gap-3">
        {sides.map((s) => (
          <div key={s.team} className={`rounded-xl p-3.5 text-center border transition-all ${s.fav ? s.ring : "border-border/40"}`}>
            <div className="flex flex-col items-center gap-1.5 mb-2">
              {teamIds && teamLogoUrl(teamIds[s.team]) && (
                <img src={teamLogoUrl(teamIds[s.team])!} alt="" className="w-8 h-8 object-contain" loading="lazy" onError={onImgError} />
              )}
              <span className="text-xs font-semibold leading-tight truncate max-w-full">{teamPt(s.team)}</span>
            </div>
            <p className={`text-4xl font-mono font-bold tabular-nums ${s.text}`}>
              {s.prob.toFixed(1)}<span className="text-lg">%</span>
            </p>
            <p className="text-[11px] text-muted-foreground mt-1">Chance de classificação</p>
            <p className="text-[10px] text-muted-foreground/70 mt-0.5">Odd justa: {s.odd?.toFixed(2)}</p>
          </div>
        ))}
      </div>

      {/* barra de comparação entre as duas chances de classificação */}
      <div className="flex h-2 rounded-full overflow-hidden mt-3">
        <div style={{ width: `${probA}%` }} className="bg-emerald-500" title={`${teamPt(a)} ${probA.toFixed(1)}%`} />
        <div style={{ width: `${probB}%` }} className="bg-cyan-500" title={`${teamPt(b)} ${probB.toFixed(1)}%`} />
      </div>

      <div className="mt-4 pt-4 border-t border-border/20">
        <p className="text-[11px] text-muted-foreground mb-2">Resultados agregados mais prováveis</p>
        <div className="space-y-1.5">
          {d.placar_agregado_top.map((p, i) => (
            <div key={i} className="flex items-center gap-3 text-xs">
              <span className={`font-mono font-semibold w-10 shrink-0 ${i === 0 ? "text-foreground" : "text-muted-foreground"}`}>
                {p[a]}–{p[b]}
              </span>
              <div className="flex-1 h-1 rounded-full bg-muted/40 overflow-hidden">
                <div className="h-full bg-emerald-500/60" style={{ width: `${topScore ? (p.prob / topScore.prob) * 100 : 0}%` }} />
              </div>
              <span className="font-mono text-muted-foreground shrink-0">{p.prob.toFixed(1)}%</span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-3 rounded-lg bg-muted/30 border border-border/30 px-3 py-2.5 flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] text-muted-foreground">Chance de decisão na prorrogação</p>
          <p className="text-[10px] text-muted-foreground/70">Empate no agregado → prorrogação/pênaltis</p>
        </div>
        <p className="text-xl font-mono font-bold text-foreground shrink-0">{d.empate_agregado_prob.toFixed(1)}%</p>
      </div>

      <div className="mt-4 pt-3 border-t border-border/20">
        <p className="text-[11px] font-semibold text-foreground mb-1">Resumo do confronto</p>
        <p className="text-xs text-muted-foreground leading-relaxed">{resumo}</p>
      </div>
    </div>
  );
}

// Total de gols nas duas pernas do mata-mata — soma direta das duas PMFs
// (CountPrediction padrão, já vem pronta do backend em gols_agregados).
export function GolsAgregadosCard({ d }: { d: CountPrediction }) {
  const [viewMode, setViewMode] = useState<"prob" | "odd">("prob");
  const [isExpanded, setIsExpanded] = useState(false);
  const dist = d.distribuicao ?? [];
  const mean = d.estimativa ?? 0;

  const { lines, mainLine } = useMemo(() => {
    const center = Math.round(mean - 0.5) + 0.5;
    const all: number[] = [];
    for (let i = -4; i <= 4; i++) {
      const L = center + i;
      if (L >= 0.5) all.push(Number(L.toFixed(1)));
    }
    return { lines: all, mainLine: all.includes(center) ? center : all[0] };
  }, [mean]);

  if (dist.length === 0) return null;

  const Cell = ({ line, side }: { line: number; side: "over" | "under" }) => {
    const p = side === "over" ? overProb(dist, line) : 1 - overProb(dist, line);
    return viewMode === "prob" ? <span>{(p * 100).toFixed(1)}%</span> : <span>{fairOddRange(p)}</span>;
  };
  const mainOverP = overProb(dist, mainLine);

  return (
    <div className="bg-card border border-border/60 rounded-2xl overflow-hidden shadow-md shadow-black/10 transition-all hover:border-border/80">
      <div className="p-4 border-b border-border/40 space-y-3">
        <h3 className="text-xs font-bold flex items-center justify-center gap-1.5 text-center text-foreground">
          Total de Gols (Confronto)
          <InfoTooltip text="Mercado considerando a soma dos gols dos dois jogos (ida + volta)." />
        </h3>
        <div className="flex items-center justify-between gap-2 flex-wrap text-xs">
          <div className="flex items-center gap-1.5 bg-muted/30 px-2.5 py-1 rounded-lg border border-border/40">
            <span className="text-muted-foreground text-[11px]">Gols esperados</span>
            <span className="font-mono font-bold text-emerald-400">{mean.toFixed(1)}</span>
          </div>
          <div className="bg-muted/40 p-0.5 rounded-lg flex text-[11px] font-semibold border border-border/40">
            <button
              onClick={() => setViewMode("prob")}
              className={`px-2.5 py-0.5 rounded-md transition-all ${viewMode === "prob" ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"}`}
            >Prob.</button>
            <button
              onClick={() => setViewMode("odd")}
              className={`px-2.5 py-0.5 rounded-md transition-all ${viewMode === "odd" ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"}`}
            >Odd</button>
          </div>
        </div>
      </div>

      <div className="p-4 space-y-3">
        <div className="bg-muted/20 p-3 rounded-xl border border-border/50 space-y-2">
          <div className="flex justify-between items-center text-xs">
            <div className="flex-1 text-center">
              <span className="block text-[11px] text-muted-foreground mb-0.5">Mais de {mainLine} gols</span>
              <span className="font-mono font-bold text-base text-emerald-400"><Cell line={mainLine} side="over" /></span>
            </div>
            <div className="w-px h-8 bg-border/40" />
            <div className="flex-1 text-center">
              <span className="block text-[11px] text-muted-foreground mb-0.5">Menos de {mainLine} gols</span>
              <span className="font-mono font-bold text-base text-cyan-400"><Cell line={mainLine} side="under" /></span>
            </div>
          </div>
          <div className="w-full bg-cyan-950/40 h-1.5 rounded-full overflow-hidden flex border border-white/5">
            <div className="bg-emerald-500 transition-all duration-300" style={{ width: `${mainOverP * 100}%` }} />
            <div className="bg-cyan-500 transition-all duration-300" style={{ width: `${(1 - mainOverP) * 100}%` }} />
          </div>
        </div>

        <button
          onClick={() => setIsExpanded((e) => !e)}
          className="w-full flex items-center justify-center gap-1.5 py-1.5 text-[11px] font-semibold text-muted-foreground hover:text-foreground transition-colors"
        >
          {isExpanded ? "Ocultar linhas alternativas" : "Ver linhas alternativas"}
          <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-200 ${isExpanded ? "rotate-180" : ""}`} />
        </button>

        <AnimatePresence>
          {isExpanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="pt-2 border-t border-border/40 space-y-1">
                <div className="grid grid-cols-3 text-[10px] font-mono font-bold text-muted-foreground text-center pb-1">
                  <span className="text-emerald-400">Mais</span>
                  <span>Linha</span>
                  <span className="text-cyan-400">Menos</span>
                </div>
                <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
                  {lines.map((L) => (
                    <div key={L} className={`grid grid-cols-3 text-xs py-1.5 rounded-lg border transition-colors ${L === mainLine ? "bg-emerald-500/10 border-emerald-500/30" : "border-transparent hover:bg-muted/30"}`}>
                      <div className="text-center font-mono font-semibold text-emerald-400"><Cell line={L} side="over" /></div>
                      <div className="text-center font-mono font-bold text-foreground">{L}</div>
                      <div className="text-center font-mono font-semibold text-cyan-400"><Cell line={L} side="under" /></div>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <p className="text-[10px] text-muted-foreground text-center">Mercado considerando a soma dos gols dos dois jogos.</p>
      </div>
    </div>
  );
}

// Bloco completo (compat p/ PredictionDisplay); a página de Análise usa os cards individuais.
export default function DerivedMarketsBlock({ d, home, away }: DProps) {
  return (
    <div className="mt-8">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 items-stretch">
        <DuplaChanceCard d={d} home={home} away={away} />
        <EmpateAnulaCard d={d} home={home} away={away} />
        <HandicapCard d={d} team={home} label={teamPt(home)} />
        <HandicapCard d={d} team={away} label={teamPt(away)} />
        <CleanSheetCard d={d} home={home} away={away} />
        <VitoriaSemSofrerCard d={d} home={home} away={away} />
        <ParImparCard d={d} />
        <FaixaGolsCard d={d} />
      </div>
    </div>
  );
}
