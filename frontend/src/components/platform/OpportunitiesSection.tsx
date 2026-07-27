"use client";
import React, { useEffect, useState, useMemo } from "react";
import { Filter, ShieldAlert, Sparkles, TrendingUp } from "lucide-react";
import type { BookmakerOddsResponse, NumericLineMarket, OddsMarket, PredictionResponse, Scope } from "@/lib/api";
import { api } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import { bmEntries, lineOutcomeKey } from "@/components/platform/AnalysisResultsView";

type OpportunityRow = {
  mercadoTipo: "Resultado" | "Gols" | "Ambas Marcam" | "Escanteios" | "Cartões";
  mercadoLabel: string;
  equipe: string;
  casa: string;
  oddModelo: number;
  faixaMin: number;
  faixaMax: number;
  oddCasa: number;
  probabilidade: number;
  ev: number;
};

const BOOKMAKER_STYLES: Record<string, { bg: string; label: string }> = {
  "Bet365": { bg: "bg-emerald-600/20 text-emerald-400 border-emerald-500/30", label: "365" },
  "Betano": { bg: "bg-orange-600/20 text-orange-400 border-orange-500/30", label: "B" },
  "Betfair": { bg: "bg-amber-500/20 text-amber-300 border-amber-500/30", label: "BF" },
  "Pinnacle": { bg: "bg-blue-950 text-blue-400 border-blue-500/30", label: "PIN" },
  "Novibet": { bg: "bg-cyan-600/20 text-cyan-400 border-cyan-500/30", label: "NOVI" },
  "KTO": { bg: "bg-red-600/20 text-red-400 border-red-500/30", label: "KTO" },
  "Superbet": { bg: "bg-rose-600/20 text-rose-400 border-rose-500/30", label: "SUPER" },
  "Sportingbet": { bg: "bg-blue-600/20 text-blue-400 border-blue-500/30", label: "SB" },
  "Stake": { bg: "bg-slate-800 text-slate-200 border-slate-600/30", label: "STAKE" },
  "1xBet": { bg: "bg-sky-600/20 text-sky-400 border-sky-500/30", label: "1X" },
  "Betnacional": { bg: "bg-yellow-600/20 text-yellow-400 border-yellow-500/30", label: "NAC" },
  "EstrelaBet": { bg: "bg-indigo-600/20 text-indigo-400 border-indigo-500/30", label: "EST" },
};

function BookmakerLogo({ name }: { name: string }) {
  const [err, setErr] = useState(false);
  const cleanName = name.toLowerCase().replace(/[^a-z0-9]/g, "");
  const style = BOOKMAKER_STYLES[name] || {
    bg: "bg-muted text-muted-foreground border-border/40",
    label: name.slice(0, 3).toUpperCase(),
  };

  if (!err) {
    return (
      <img
        src={`/bookmakers/${cleanName}.png`}
        alt={name}
        className="w-5 h-5 object-contain shrink-0 rounded bg-white/5 p-0.5 border border-white/10"
        onError={() => setErr(true)}
      />
    );
  }

  return (
    <span className={`inline-flex items-center justify-center px-1.5 py-0.5 rounded text-[10px] font-extrabold border shrink-0 font-mono tracking-tighter ${style.bg}`}>
      {style.label}
    </span>
  );
}

function pushBinaryComparisons(
  rows: OpportunityRow[],
  bookmakerOdds: BookmakerOddsResponse | null,
  mercadoApi: string,
  outcomeApi: string,
  mercadoTipo: "Resultado" | "Gols" | "Ambas Marcam" | "Escanteios" | "Cartões",
  mercadoLabel: string,
  equipe: string,
  market: OddsMarket | undefined,
) {
  if (!market) return;
  const entries = bmEntries(bookmakerOdds, mercadoApi, outcomeApi);
  const prob = market.probabilidade / 100;
  const oddModelo = market.probabilidade > 0 ? 100 / market.probabilidade : 0;
  for (const e of entries) {
    const ev = e.odd * prob - 1;
    if (ev > 0) {
      rows.push({
        mercadoTipo,
        mercadoLabel,
        equipe,
        casa: e.casa,
        oddModelo,
        faixaMin: market.faixa_odd_justa.min,
        faixaMax: market.faixa_odd_justa.max,
        oddCasa: e.odd,
        probabilidade: market.probabilidade,
        ev,
      });
    }
  }
}

function pushLineComparisons(
  rows: OpportunityRow[],
  bookmakerOdds: BookmakerOddsResponse | null,
  mercadoApi: string,
  mercadoTipo: "Gols" | "Escanteios" | "Cartões",
  equipe: string,
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
    const oddModelo = m.probabilidade > 0 ? 100 / m.probabilidade : 0;
    for (const e of entries) {
      const ev = e.odd * prob - 1;
      if (ev > 0) {
        rows.push({
          mercadoTipo,
          mercadoLabel: `${mercadoTipo} (${outcomeLabel})`,
          equipe,
          casa: e.casa,
          oddModelo,
          faixaMin: m.faixa_odd_justa.min,
          faixaMax: m.faixa_odd_justa.max,
          oddCasa: e.odd,
          probabilidade: m.probabilidade,
          ev,
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
  const [selectedMarket, setSelectedMarket] = useState<string>("Todos os Mercados");
  const [selectedHouse, setSelectedHouse] = useState<string>("Todas as Casas");

  useEffect(() => {
    if (!fixtureId) { setBookmakerOdds(null); return; }
    let cancelled = false;
    api.getBookmakerOdds(fixtureId, scope || "selecao")
      .then(res => { if (!cancelled) setBookmakerOdds(res); })
      .catch(() => { if (!cancelled) setBookmakerOdds(null); });
    return () => { cancelled = true; };
  }, [fixtureId, scope]);

  const rows = useMemo(() => {
    if (!fixtureId || !bookmakerOdds || !bookmakerOdds.disponivel) return [];
    const odds = prediction.odds;
    const list: OpportunityRow[] = [];
    if (odds) {
      pushBinaryComparisons(list, bookmakerOdds, "resultado", "Home", "Resultado", "Resultado (Vitória)", teamPt(home), odds.vencedor?.[home]);
      pushBinaryComparisons(list, bookmakerOdds, "resultado", "Draw", "Resultado", "Resultado (Empate)", "Partida", odds.vencedor?.["Empate"]);
      pushBinaryComparisons(list, bookmakerOdds, "resultado", "Away", "Resultado", "Resultado (Vitória)", teamPt(away), odds.vencedor?.[away]);
      pushBinaryComparisons(list, bookmakerOdds, "btts", "Yes", "Ambas Marcam", "Ambas Marcam (Sim)", "Partida", odds.ambas_marcam?.sim);
      pushBinaryComparisons(list, bookmakerOdds, "btts", "No", "Ambas Marcam", "Ambas Marcam (Não)", "Partida", odds.ambas_marcam?.nao);
      pushLineComparisons(list, bookmakerOdds, "gols_over_under", "Gols", "Partida", odds.linhas_numericas?.gols);
      pushLineComparisons(list, bookmakerOdds, "escanteios_mandante", "Escanteios", teamPt(home), odds.linhas_numericas?.escanteios?.[home]);
      pushLineComparisons(list, bookmakerOdds, "escanteios_total", "Escanteios", "Partida", odds.linhas_numericas?.escanteios?.total);
      pushLineComparisons(list, bookmakerOdds, "escanteios_visitante", "Escanteios", teamPt(away), odds.linhas_numericas?.escanteios?.[away]);
      pushLineComparisons(list, bookmakerOdds, "cartoes_mandante", "Cartões", teamPt(home), odds.linhas_numericas?.cartoes?.[home]);
      pushLineComparisons(list, bookmakerOdds, "cartoes_total", "Cartões", "Partida", odds.linhas_numericas?.cartoes?.total);
      pushLineComparisons(list, bookmakerOdds, "cartoes_visitante", "Cartões", teamPt(away), odds.linhas_numericas?.cartoes?.[away]);
    }
    list.sort((a, b) => b.ev - a.ev);
    return list;
  }, [bookmakerOdds, fixtureId, prediction.odds, home, away]);

  const houseOptions = useMemo(() => {
    const set = new Set<string>();
    rows.forEach(r => set.add(r.casa));
    return ["Todas as Casas", ...Array.from(set).sort()];
  }, [rows]);

  const filteredRows = useMemo(() => {
    return rows.filter(r => {
      const matchMarket = selectedMarket === "Todos os Mercados" || r.mercadoTipo === selectedMarket;
      const matchHouse = selectedHouse === "Todas as Casas" || r.casa === selectedHouse;
      return matchMarket && matchHouse;
    });
  }, [rows, selectedMarket, selectedHouse]);

  if (rows.length === 0) return null;

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

      <div className="bg-card border border-emerald-500/30 rounded-xl p-4 sm:p-5 shadow-sm space-y-4">
        {/* BARRA DE FILTROS */}
        <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg border border-border/50 bg-muted/20">
          <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
            <Filter className="w-3.5 h-3.5 text-emerald-400" />
            <span>Filtros:</span>
          </div>

          <div className="flex flex-wrap items-center gap-2.5 min-w-0">
            {/* Filtro de Mercado */}
            <select
              value={selectedMarket}
              onChange={(e) => setSelectedMarket(e.target.value)}
              className="h-8 text-xs rounded-lg border border-emerald-500/30 bg-muted/60 px-2.5 py-1 text-foreground focus:outline-none focus:ring-1 focus:ring-emerald-500 font-medium"
            >
              <option value="Todos os Mercados">Todos os Mercados</option>
              <option value="Resultado">Resultado</option>
              <option value="Gols">Gols</option>
              <option value="Ambas Marcam">Ambas Marcam</option>
              <option value="Escanteios">Escanteios</option>
              <option value="Cartões">Cartões</option>
            </select>

            {/* Filtro de Casa de Apostas */}
            <select
              value={selectedHouse}
              onChange={(e) => setSelectedHouse(e.target.value)}
              className="h-8 text-xs rounded-lg border border-emerald-500/30 bg-muted/60 px-2.5 py-1 text-foreground focus:outline-none focus:ring-1 focus:ring-emerald-500 font-medium"
            >
              {houseOptions.map(h => (
                <option key={h} value={h}>{h}</option>
              ))}
            </select>
          </div>
        </div>

        {/* TABELA DE OPORTUNIDADES (5 Linhas visíveis + Scrolldown) */}
        <div className="overflow-x-auto rounded-lg border border-emerald-500/20 bg-background/50">
          <div className="max-h-[295px] overflow-y-auto pr-0.5">
            <table className="w-full text-left border-collapse min-w-[620px]">
              <thead className="sticky top-0 z-10 bg-card border-b border-emerald-500/30 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground shadow-sm">
                <tr>
                  <th className="py-2.5 px-3">Mercado</th>
                  <th className="py-2.5 px-3">Equipe</th>
                  <th className="py-2.5 px-3">Casa de Aposta</th>
                  <th className="py-2.5 px-3 text-center">Odd Modelo</th>
                  <th className="py-2.5 px-3 text-center">Odd Casa</th>
                  <th className="py-2.5 px-3 text-right">EV</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-emerald-500/10 text-xs font-medium">
                {filteredRows.map((r, i) => (
                  <tr key={i} className="hover:bg-emerald-500/5 transition-colors">
                    <td className="py-2.5 px-3 font-semibold text-foreground">
                      {r.mercadoLabel}
                    </td>
                    <td className="py-2.5 px-3">
                      {r.equipe === "Partida" ? (
                        <span className="text-muted-foreground/80 font-medium italic">Partida</span>
                      ) : (
                        <span className="text-foreground">{r.equipe}</span>
                      )}
                    </td>
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-2">
                        <BookmakerLogo name={r.casa} />
                        <span className="font-medium text-foreground">{r.casa}</span>
                      </div>
                    </td>
                    <td className="py-2.5 px-3 text-center font-mono text-muted-foreground">
                      {r.oddModelo.toFixed(2)}
                    </td>
                    <td className="py-2.5 px-3 text-center font-mono font-bold text-foreground">
                      {r.oddCasa.toFixed(2)}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono font-bold text-emerald-400">
                      <span className="inline-flex items-center justify-end gap-1">
                        <TrendingUp className="w-3 h-3 text-emerald-400 shrink-0" />
                        +{(r.ev * 100).toFixed(1)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {filteredRows.length === 0 && (
              <div className="py-8 text-center text-xs text-muted-foreground italic">
                Nenhuma oportunidade encontrada para os filtros selecionados.
              </div>
            )}
          </div>
        </div>

        {filteredRows.length > 5 && (
          <p className="text-[10px] text-muted-foreground/80 text-right italic pt-0.5">
            Exibindo 5 visíveis de {filteredRows.length} oportunidades — role a tabela para ver mais.
          </p>
        )}

        <p className="text-xs text-muted-foreground leading-relaxed pt-2 border-t border-border/40">
          <strong className="text-foreground">O que é EV (valor esperado)?</strong> Quando a odd oferecida por
          uma casa paga mais do que a probabilidade real segundo o nosso modelo sugere, a aposta é
          matematicamente favorável no longo prazo — mas isso{" "}
          <strong className="text-foreground">não garante lucro em uma aposta individual</strong>. A
          probabilidade usada é uma <strong className="text-foreground">estimativa</strong> do modelo, não uma
          certeza. Jogue com responsabilidade.
        </p>

        <p className="mt-2 text-[11px] text-muted-foreground flex items-start gap-1.5 pt-2 border-t border-border/40">
          <ShieldAlert className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
          Apostas envolvem risco real de perda e são destinadas a maiores de 18 anos. Nenhuma previsão garante resultado.
        </p>
      </div>
    </div>
  );
}
