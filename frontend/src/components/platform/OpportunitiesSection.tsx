"use client";
import React, { useEffect, useState } from "react";
import { ShieldAlert, Sparkles, TrendingUp } from "lucide-react";
import type { BookmakerOddsResponse, NumericLineMarket, OddsMarket, PredictionResponse, Scope } from "@/lib/api";
import { api } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import { bmEntries, lineOutcomeKey } from "@/components/platform/AnalysisResultsView";

// "OPORTUNIDADES ENCONTRADAS" -- cruza as odds por casa (Verificador de Bets, GET
// /api/odds/bookmakers) com a probabilidade do modelo já vinda de /predict
// (prediction.odds) para calcular EV = odd_oferecida × probabilidade_do_modelo − 1,
// 100% no cliente. NÃO recalcula odd justa em nenhum ponto -- só reusa
// prediction.odds.*.faixa_odd_justa. Reusa a MESMA chamada de dados feita em
// AnalysisResultsView (o cache TTL/dedup de lib/api.ts torna a segunda chamada
// gratuita na prática).

type OpportunityRow = {
  mercadoLabel: string;
  outcomeLabel: string;
  casa: string;
  odd: number;
  faixaMin: number;
  faixaMax: number;
  probabilidade: number; // %
  ev: number; // fração (0.05 = +5%)
};

function pushBinaryComparisons(
  rows: OpportunityRow[],
  bookmakerOdds: BookmakerOddsResponse | null,
  mercadoApi: string,
  outcomeApi: string,
  mercadoLabel: string,
  outcomeLabel: string,
  market: OddsMarket | undefined,
) {
  if (!market) return;
  const entries = bmEntries(bookmakerOdds, mercadoApi, outcomeApi);
  const prob = market.probabilidade / 100;
  for (const e of entries) {
    const ev = e.odd * prob - 1;
    if (ev > 0) {
      rows.push({
        mercadoLabel, outcomeLabel, casa: e.casa, odd: e.odd,
        faixaMin: market.faixa_odd_justa.min, faixaMax: market.faixa_odd_justa.max,
        probabilidade: market.probabilidade, ev,
      });
    }
  }
}

function pushLineComparisons(
  rows: OpportunityRow[],
  bookmakerOdds: BookmakerOddsResponse | null,
  mercadoApi: string,
  mercadoLabel: string,
  market: NumericLineMarket | undefined,
) {
  if (!market || !market.disponivel) return;
  const sides: Array<["Over" | "Under", OddsMarket, string]> = [
    ["Over", market.over, `Acima de ${market.linha}`],
    ["Under", market.under, `Abaixo de ${market.linha}`],
  ];
  for (const [side, m, outcomeLabel] of sides) {
    const entries = bmEntries(bookmakerOdds, mercadoApi, lineOutcomeKey(side, market.linha));
    const prob = m.probabilidade / 100;
    for (const e of entries) {
      const ev = e.odd * prob - 1;
      if (ev > 0) {
        rows.push({
          mercadoLabel, outcomeLabel, casa: e.casa, odd: e.odd,
          faixaMin: m.faixa_odd_justa.min, faixaMax: m.faixa_odd_justa.max,
          probabilidade: m.probabilidade, ev,
        });
      }
    }
  }
}

export default function OpportunitiesSection({ prediction, home, away, fixtureId, scope }: {
  prediction: PredictionResponse;
  home: string;
  away: string;
  fixtureId?: number | null;
  scope?: Scope;
}) {
  const [bookmakerOdds, setBookmakerOdds] = useState<BookmakerOddsResponse | null>(null);

  useEffect(() => {
    if (!fixtureId) { setBookmakerOdds(null); return; }
    let cancelled = false;
    api.getBookmakerOdds(fixtureId, scope || "selecao")
      .then(res => { if (!cancelled) setBookmakerOdds(res); })
      .catch(() => { if (!cancelled) setBookmakerOdds(null); });
    return () => { cancelled = true; };
  }, [fixtureId, scope]);

  if (!fixtureId || !bookmakerOdds || !bookmakerOdds.disponivel) return null;

  const odds = prediction.odds;
  const rows: OpportunityRow[] = [];
  if (odds) {
    pushBinaryComparisons(rows, bookmakerOdds, "resultado", "Home", "Resultado", `Vitória de ${teamPt(home)}`, odds.vencedor?.[home]);
    pushBinaryComparisons(rows, bookmakerOdds, "resultado", "Draw", "Resultado", "Empate", odds.vencedor?.["Empate"]);
    pushBinaryComparisons(rows, bookmakerOdds, "resultado", "Away", "Resultado", `Vitória de ${teamPt(away)}`, odds.vencedor?.[away]);
    pushBinaryComparisons(rows, bookmakerOdds, "btts", "Yes", "Ambas Marcam", "Sim", odds.ambas_marcam?.sim);
    pushBinaryComparisons(rows, bookmakerOdds, "btts", "No", "Ambas Marcam", "Não", odds.ambas_marcam?.nao);
    pushLineComparisons(rows, bookmakerOdds, "gols_over_under", "Gols (Partida)", odds.linhas_numericas?.gols);
    pushLineComparisons(rows, bookmakerOdds, "escanteios_mandante", `Escanteios (${teamPt(home)})`, odds.linhas_numericas?.escanteios?.[home]);
    pushLineComparisons(rows, bookmakerOdds, "escanteios_total", "Escanteios (Partida)", odds.linhas_numericas?.escanteios?.total);
    pushLineComparisons(rows, bookmakerOdds, "escanteios_visitante", `Escanteios (${teamPt(away)})`, odds.linhas_numericas?.escanteios?.[away]);
    pushLineComparisons(rows, bookmakerOdds, "cartoes_mandante", `Cartões (${teamPt(home)})`, odds.linhas_numericas?.cartoes?.[home]);
    pushLineComparisons(rows, bookmakerOdds, "cartoes_total", "Cartões (Partida)", odds.linhas_numericas?.cartoes?.total);
    pushLineComparisons(rows, bookmakerOdds, "cartoes_visitante", `Cartões (${teamPt(away)})`, odds.linhas_numericas?.cartoes?.[away]);
  }

  // Nunca inventa oportunidade: sem nenhuma linha com EV>0, a seção inteira some.
  if (rows.length === 0) return null;

  rows.sort((a, b) => b.ev - a.ev);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4 mt-8 mb-4">
        <div className="h-px flex-1 bg-gradient-to-r from-transparent to-emerald-500/40" />
        <h3 className="text-lg font-heading font-bold uppercase tracking-wide whitespace-nowrap text-center text-emerald-400 flex items-center gap-2">
          <Sparkles className="w-5 h-5" />
          Oportunidades Encontradas
        </h3>
        <div className="h-px flex-1 bg-gradient-to-l from-transparent to-emerald-500/40" />
      </div>

      <div className="bg-card border border-emerald-500/30 rounded-xl p-5">
        <p className="text-xs text-muted-foreground mb-4 leading-relaxed">
          <strong className="text-foreground">O que é EV (valor esperado)?</strong> Quando a odd oferecida por
          uma casa paga mais do que a probabilidade real segundo o nosso modelo sugere, a aposta é
          matematicamente favorável no longo prazo — mas isso{" "}
          <strong className="text-foreground">não garante lucro em uma aposta individual</strong>. A
          probabilidade usada é uma <strong className="text-foreground">estimativa</strong> do modelo, não uma
          certeza, e pode estar errada. Jogue com responsabilidade e nunca aposte mais do que pode perder.
        </p>

        <div className="space-y-2">
          {rows.map((r, i) => (
            <div
              key={i}
              className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 px-3 py-2.5 rounded-lg border border-emerald-500/20 bg-emerald-500/5"
            >
              <div className="min-w-0">
                <p className="text-sm font-semibold text-foreground truncate">
                  {r.mercadoLabel} — {r.outcomeLabel}
                </p>
                <p className="text-[11px] text-muted-foreground">
                  {r.casa} · faixa de odd justa do modelo: {r.faixaMin.toFixed(2)}–{r.faixaMax.toFixed(2)} ·
                  probabilidade do modelo: {r.probabilidade.toFixed(1)}%
                </p>
              </div>
              <div className="flex items-center gap-4 shrink-0">
                <div className="text-center">
                  <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Odd oferecida</p>
                  <p className="font-mono font-bold text-foreground">{r.odd.toFixed(2)}</p>
                </div>
                <div className="text-center">
                  <p className="text-[10px] uppercase tracking-wide text-muted-foreground">EV</p>
                  <p className="font-mono font-bold text-emerald-400 flex items-center gap-1">
                    <TrendingUp className="w-3.5 h-3.5" />
                    +{(r.ev * 100).toFixed(1)}%
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>

        <p className="mt-4 text-[11px] text-muted-foreground flex items-start gap-1.5">
          <ShieldAlert className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
          Apostas envolvem risco real de perda e são destinadas a maiores de 18 anos. Nenhuma previsão, por
          melhor calibrada que seja, garante resultado.
        </p>
      </div>
    </div>
  );
}
