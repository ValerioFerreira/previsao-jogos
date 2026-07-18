"use client";
import React from "react";
import { DerivedMarkets, DerivedOutcome, teamLogoUrl, onImgError } from "@/lib/api";
import InfoTooltip from "@/components/platform/InfoTooltip";
import { teamPt } from "@/lib/teamNames";

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
            <div className="flex items-center justify-between text-[9px] uppercase tracking-wide text-muted-foreground/80 pb-1 border-b border-border/40">
              <span>Linha</span>
              <span className="flex items-baseline gap-1.5 shrink-0">
                <span>Probabilidade</span>
                <span>Odd Justa</span>
              </span>
            </div>
            {lines(team).map(({ key, label, o }) => (
              <div key={key} className="flex items-center justify-between text-xs py-1 border-t border-border/20">
                <span className="text-muted-foreground">{label}</span>
                <span className="flex items-baseline gap-1.5 shrink-0">
                  <span className="font-mono font-bold text-emerald-400">{o ? `${o.prob.toFixed(1)}%` : "—"}</span>
                  <span className="font-mono text-[10px] text-muted-foreground">{o ? o.odd_justa.toFixed(2) : ""}</span>
                </span>
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
