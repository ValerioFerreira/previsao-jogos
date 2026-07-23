"use client";
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Target, Gauge, Trophy, ShieldAlert, ArrowRight, TrendingDown,
  BarChart3, CheckCircle2, Scale, Info, Search, Crosshair,
} from "lucide-react";
import { api, PerformanceOverview, PerfHitrate, PerfFairOddsLeague } from "@/lib/api";

const LEAGUE_LABEL: Record<string, string> = {
  "Brasileirao Serie A": "Brasileirão Série A",
  "Premier League": "Premier League",
  "La Liga": "La Liga",
  "Serie A Italia": "Serie A (Itália)",
  "Geral (ligas-alvo)": "Geral (ligas principais)",
};

const STRAT_LABEL: Record<string, string> = {
  modelo_1x2: "Modelo (nosso palpite)",
  sempre_favorito: "Sempre no favorito",
  sempre_azarao: "Sempre no azarão",
  sempre_mandante: "Sempre no mandante",
  sempre_empate: "Sempre no empate",
};

function fmt(n: number | null | undefined, suffix = "") {
  return n === null || n === undefined ? "—" : `${n}${suffix}`;
}

function Section({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 18 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className={`mx-auto w-full max-w-5xl px-4 ${className}`}
    >
      {children}
    </motion.section>
  );
}

export default function DesempenhoPage() {
  const [data, setData] = useState<PerformanceOverview | null>(null);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    api.performance().then(setData).catch(() => setErro(true));
  }, []);

  const head = data?.overview?.headline;
  const hitLigas = data?.hitrates?.ligas || {};
  const naiveLigas = data?.model_vs_naive?.ligas || {};
  const resp = data?.overview?.jogo_responsavel;
  const fairMercados = data?.fair_odds?.mercados || {};

  return (
    <main className="min-h-screen pb-24 pt-10 space-y-16">
      {/* ---------- HERÓI: CALIBRAÇÃO ---------- */}
      <Section>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 border border-emerald-500/40 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-emerald-300">
          <Gauge className="w-3.5 h-3.5" /> Desempenho real do modelo
        </span>
        <h1 className="mt-4 font-heading text-4xl sm:text-5xl font-extrabold leading-tight">
          Os números que <span className="bg-gradient-to-r from-emerald-300 to-cyan-300 bg-clip-text text-transparent">a gente não esconde</span>
        </h1>
        <p className="mt-3 max-w-2xl text-muted-foreground">
          Tudo aqui vem de <b className="text-foreground">teste fora da amostra</b> — jogos que o modelo
          nunca viu no treino. Sem cherry-picking, com o método à mostra.
        </p>

        {erro && (
          <p className="mt-6 text-sm text-amber-400">Não foi possível carregar as métricas agora. Tente novamente em instantes.</p>
        )}

        {head && (
          <div className="mt-8 grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="sm:col-span-3 rounded-2xl border border-emerald-500/30 bg-gradient-to-br from-emerald-500/10 to-transparent p-6">
              <p className="flex items-center gap-2 text-sm font-semibold text-emerald-300">
                <Target className="w-4 h-4" /> Calibração
              </p>
              <p className="mt-2 font-heading text-3xl sm:text-4xl font-extrabold text-foreground">
                {head.frase_calibracao}
              </p>
              <p className="mt-2 text-sm text-muted-foreground max-w-2xl">{head.explicacao_leiga}</p>
            </div>

            <Kpi label="Erro de calibração (ECE)" value={fmt(head.calibracao_ece_pct, "%")} sub="menor é melhor · <2% já é ótimo" good />
            <Kpi label="Acurácia no 1x2" value={fmt(head.acuracia_1x2_pct, "%")} sub="no teto prático do mercado" />
            <Kpi label="Placar exato" value={fmt(head.placar_exato_pct, "%")} sub="acima da literatura (~10-13%)" good />
          </div>
        )}

        {head && (
          <p className="mt-4 text-xs text-muted-foreground flex items-center gap-1.5">
            <Info className="w-3.5 h-3.5 shrink-0" />
            Base: {head.n_jogos.toLocaleString("pt-BR")} jogos out-of-sample em {head.n_competicoes} competições · log-loss {head.log_loss}.
          </p>
        )}
      </Section>

      {/* ---------- MODELO vs MERCADO ---------- */}
      <Section>
        <h2 className="font-heading text-2xl sm:text-3xl font-bold flex items-center gap-2">
          <Scale className="w-6 h-6 text-cyan-300" /> Modelo vs. o mercado
        </h2>
        <p className="mt-2 text-sm text-muted-foreground max-w-2xl">
          O <b className="text-foreground">mercado de fechamento</b> (a odd final das casas) é o benchmark mais
          difícil que existe — é a previsão coletiva mais afiada do planeta. Nós chegamos coladinho nele,
          e mostramos a conta.
        </p>
        <div className="mt-5 overflow-x-auto">
          <table className="w-full text-sm min-w-[560px]">
            <thead>
              <tr className="text-left text-muted-foreground border-b border-white/10">
                <th className="py-2 pr-3 font-medium">Liga</th>
                <th className="py-2 px-3 font-medium">Acurácia (nós)</th>
                <th className="py-2 px-3 font-medium">Acurácia (mercado)</th>
                <th className="py-2 px-3 font-medium">Log-loss (nós)</th>
                <th className="py-2 px-3 font-medium">Log-loss (mercado)</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(hitLigas).map(([lg, h]: [string, PerfHitrate]) => (
                <tr key={lg} className="border-b border-white/5">
                  <td className="py-2 pr-3 font-medium text-foreground">{LEAGUE_LABEL[lg] || lg}</td>
                  <td className="py-2 px-3">{fmt(h.modelo_1x2.acuracia, "%")}</td>
                  <td className="py-2 px-3 text-muted-foreground">{h.mercado_1x2 ? fmt(h.mercado_1x2.acuracia, "%") : "—"}</td>
                  <td className="py-2 px-3">{fmt(h.modelo_1x2.log_loss)}</td>
                  <td className="py-2 px-3 text-muted-foreground">{h.mercado_1x2 ? fmt(h.mercado_1x2.log_loss) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {/* ---------- TAXAS DE ACERTO POR LIGA ---------- */}
      <Section>
        <h2 className="font-heading text-2xl sm:text-3xl font-bold flex items-center gap-2">
          <BarChart3 className="w-6 h-6 text-emerald-300" /> Taxas de acerto por liga
        </h2>
        <div className="mt-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
          {Object.entries(hitLigas)
            .filter(([lg]) => lg !== "Geral (ligas-alvo)")
            .map(([lg, h]: [string, PerfHitrate]) => (
              <div key={lg} className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                <p className="font-heading font-bold text-foreground">{LEAGUE_LABEL[lg] || lg}</p>
                <p className="text-xs text-muted-foreground">{h.n_jogos} jogos</p>
                <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                  <MiniStat label="Resultado" value={fmt(h.modelo_1x2.acuracia, "%")} />
                  <MiniStat label="Placar exato" value={fmt(h.placar_e_btts.placar_exato_top1_acerto_pct, "%")} />
                  <MiniStat label="Ambas marcam" value={fmt(h.placar_e_btts.btts_acerto_pct, "%")} />
                </div>
                <p className="mt-3 text-xs text-muted-foreground">
                  Empate: prevemos a probabilidade em <b className="text-foreground">{fmt(h.empates.prob_media_empate_modelo, "%")}</b>,
                  e ele aconteceu em <b className="text-foreground">{fmt(h.empates.freq_real_empate, "%")}</b> — calibrado.
                </p>
              </div>
            ))}
        </div>
      </Section>

      {/* ---------- MODELO vs APOSTA RUIM ---------- */}
      <Section>
        <h2 className="font-heading text-2xl sm:text-3xl font-bold flex items-center gap-2">
          <Trophy className="w-6 h-6 text-amber-400" /> Modelo vs. aposta no chute
        </h2>
        <p className="mt-2 text-sm text-muted-foreground max-w-2xl">
          Acurácia no resultado (1x2), no geral das ligas principais. Apostar no chute —
          sempre no empate, no azarão ou no mandante — acerta <b className="text-foreground">muito</b> menos.
          Só o "sempre no favorito" chega perto, e não é coincidência: o modelo quase sempre concorda com
          o favorito — e ainda te entrega a probabilidade de <b className="text-foreground">cada</b> mercado,
          não só o palpite do vencedor.
        </p>
        {naiveLigas["Geral (ligas-alvo)"] && (
          <div className="mt-5 space-y-2">
            {Object.entries(naiveLigas["Geral (ligas-alvo)"].estrategias)
              .filter(([k]) => STRAT_LABEL[k])
              .sort((a, b) => (b[1].hit_rate ?? 0) - (a[1].hit_rate ?? 0))
              .map(([k, s]) => {
                const isModel = k === "modelo_1x2";
                const pct = s.hit_rate ?? 0;
                return (
                  <div key={k} className="flex items-center gap-3">
                    <span className={`w-44 shrink-0 text-sm ${isModel ? "font-bold text-emerald-300" : "text-muted-foreground"}`}>
                      {STRAT_LABEL[k]}
                    </span>
                    <div className="relative h-6 flex-1 rounded-full bg-white/5 overflow-hidden">
                      <div
                        className={`h-full rounded-full ${isModel ? "bg-gradient-to-r from-emerald-500 to-cyan-400" : "bg-white/15"}`}
                        style={{ width: `${Math.max(pct, 2)}%` }}
                      />
                    </div>
                    <span className={`w-14 text-right text-sm tabular-nums ${isModel ? "font-bold text-emerald-300" : "text-muted-foreground"}`}>
                      {fmt(s.hit_rate, "%")}
                    </span>
                  </div>
                );
              })}
          </div>
        )}
        <div className="mt-5 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 flex gap-3">
          <TrendingDown className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
          <p className="text-sm text-muted-foreground">
            <b className="text-foreground">Verdade inteira:</b> contra a margem das casas (o vig), no longo prazo
            <b className="text-foreground"> toda</b> estratégia tende ao prejuízo — inclusive a nossa. A diferença é
            que as apostas no chute perdem <b className="text-foreground">muito</b> mais. Nós entregamos probabilidade
            honesta pra você decidir melhor, nunca uma promessa de lucro.
          </p>
        </div>
      </Section>

      {/* ---------- ODD JUSTA REAL / VALOR ENTRE CASAS ---------- */}
      {Object.keys(fairMercados).length > 0 && (
        <Section>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-cyan-500/15 border border-cyan-500/40 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-cyan-300">
            <Crosshair className="w-3.5 h-3.5" /> O ativo da plataforma
          </span>
          <h2 className="mt-4 font-heading text-2xl sm:text-3xl font-bold flex items-center gap-2">
            <Search className="w-6 h-6 text-cyan-300" /> Odd justa REAL — onde mora o valor
          </h2>
          <p className="mt-2 text-sm text-muted-foreground max-w-2xl">
            O modelo calcula a probabilidade real e devolve a <b className="text-foreground">odd justa</b> (1&nbsp;÷&nbsp;probabilidade).
            Medimos o quanto ele acerta essa odd comparando com a odd justa do mercado (sem a margem da casa).
            Cada casa oferece uma odd diferente — o valor está em achar a que paga <b className="text-foreground">acima da justa</b>.
          </p>

          {Object.entries(fairMercados).map(([mkt, mdata]) => {
            const ligas = (mdata?.ligas || {}) as Record<string, PerfFairOddsLeague>;
            return (
              <div key={mkt} className="mt-5">
                <p className="font-heading font-bold text-foreground mb-2">{mkt}</p>
                <div className="panel-like overflow-x-auto rounded-2xl border border-white/10 bg-white/[0.03]">
                  <table className="w-full text-sm min-w-[620px]">
                    <thead>
                      <tr className="text-left text-muted-foreground border-b border-white/10">
                        <th className="py-2.5 px-4 font-medium">Liga</th>
                        <th className="py-2.5 px-3 font-medium" title="Erro médio absoluto entre a odd justa do modelo e a do mercado">Precisão (erro)</th>
                        <th className="py-2.5 px-3 font-medium" title="Erro sistemático — perto de zero = sem viés">Viés</th>
                        <th className="py-2.5 px-3 font-medium" title="Quanto a odd oferecida precisa subir para chegar na justa">Alvo de valor</th>
                        <th className="py-2.5 px-3 font-medium" title="Quanto a melhor casa já paga acima da média (mediana)">Melhor casa vs. média</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(ligas).map(([lg, r]) => {
                        const covers = r.gap_melhor_casa_mediano_pct !== null &&
                          r.gap_melhor_casa_mediano_pct >= r.breakeven_uplift_mediano_pct;
                        return (
                          <tr key={lg} className={`border-b border-white/5 ${lg.startsWith("Geral") ? "font-semibold" : ""}`}>
                            <td className="py-2.5 px-4">{LEAGUE_LABEL[lg] || lg}</td>
                            <td className="py-2.5 px-3 num" style={{ fontVariantNumeric: "tabular-nums" }}>±{r.precisao_mae_pp} pp</td>
                            <td className="py-2.5 px-3" style={{ fontVariantNumeric: "tabular-nums" }}>
                              <span className={Math.abs(r.vies_prob_pp) <= 1.5 ? "text-emerald-300" : "text-amber-300"}>
                                {r.vies_prob_pp > 0 ? "+" : ""}{r.vies_prob_pp} pp
                              </span>
                            </td>
                            <td className="py-2.5 px-3" style={{ fontVariantNumeric: "tabular-nums" }}>+{r.breakeven_uplift_mediano_pct}%</td>
                            <td className="py-2.5 px-3" style={{ fontVariantNumeric: "tabular-nums" }}>
                              <span className={covers ? "text-emerald-300 font-semibold" : "text-cyan-300"}>
                                {r.gap_melhor_casa_mediano_pct === null ? "—" : `+${r.gap_melhor_casa_mediano_pct}%`}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}

          <div className="mt-5 rounded-xl border border-cyan-500/30 bg-cyan-500/10 p-4 flex gap-3">
            <Info className="w-5 h-5 text-cyan-300 shrink-0 mt-0.5" />
            <p className="text-sm text-muted-foreground">
              <b className="text-foreground">Como ler:</b> o modelo aponta a odd justa quase sem viés (erro médio perto de zero).
              Para virar valor, a odd precisa estar cerca de <b className="text-foreground">4–5% acima</b> da oferecida — e a
              diferença entre a melhor casa e a média já entrega boa parte disso. <b className="text-foreground">Nós apontamos o
              lado e a odd justa; você compara casas e pega a que paga mais.</b> Isso não é promessa de lucro: bater o mercado
              médio não dá vantagem — a vantagem é comparar casas.
            </p>
          </div>
        </Section>
      )}

      {/* ---------- DESTAQUE REGIONAL ---------- */}
      {hitLigas["Brasileirao Serie A"] && (
        <Section>
          <div className="rounded-2xl border border-emerald-500/30 bg-gradient-to-br from-emerald-500/10 via-cyan-500/5 to-transparent p-6">
            <p className="flex items-center gap-2 text-sm font-semibold text-emerald-300">
              <CheckCircle2 className="w-4 h-4" /> Feito pra quem acompanha o Brasileirão
            </p>
            <p className="mt-2 font-heading text-2xl font-bold text-foreground">
              O mercado nº 1 do apostador brasileiro é o nosso quintal.
            </p>
            <div className="mt-4 grid grid-cols-3 gap-3 max-w-md">
              <MiniStat label="Resultado" value={fmt(hitLigas["Brasileirao Serie A"].modelo_1x2.acuracia, "%")} big />
              <MiniStat label="Placar exato" value={fmt(hitLigas["Brasileirao Serie A"].placar_e_btts.placar_exato_top1_acerto_pct, "%")} big />
              <MiniStat label="Ambas marcam" value={fmt(hitLigas["Brasileirao Serie A"].placar_e_btts.btts_acerto_pct, "%")} big />
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              Cobrimos também Série B e os times do Nordeste no mesmo motor. Copas continentais
              (Libertadores, Sul-Americana) entram no número agregado das {head?.n_competicoes ?? 52} competições.
            </p>
          </div>
        </Section>
      )}

      {/* ---------- JOGO RESPONSÁVEL ---------- */}
      <Section>
        <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6">
          <p className="flex items-center gap-2 font-heading text-lg font-bold text-foreground">
            <ShieldAlert className="w-5 h-5 text-amber-400" /> Jogo responsável
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            {resp?.aviso ?? "Apostas são para maiores de 18 anos e envolvem risco real de perda."}
          </p>
          {resp?.dado && <p className="mt-2 text-xs text-muted-foreground">{resp.dado}</p>}
          <div className="mt-4 flex flex-wrap gap-3">
            <Link href="/como-funciona" className="inline-flex items-center gap-1.5 text-sm font-semibold text-emerald-300 hover:text-emerald-200">
              Como o modelo funciona <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </Section>
    </main>
  );
}

function Kpi({ label, value, sub, good }: { label: string; value: string; sub?: string; good?: boolean }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`mt-1 font-heading text-3xl font-extrabold ${good ? "text-emerald-300" : "text-foreground"}`}>{value}</p>
      {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}

function MiniStat({ label, value, big }: { label: string; value: string; big?: boolean }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] py-2 px-1">
      <p className={`font-heading font-extrabold text-foreground ${big ? "text-2xl" : "text-lg"}`}>{value}</p>
      <p className="text-[10px] text-muted-foreground leading-tight">{label}</p>
    </div>
  );
}
