"use client";
import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Loader2, AlertTriangle } from "lucide-react";
import { api, type SharedAnalysisPublic, type ScorersResponse, type RecentMatch, type Anomaly } from "@/lib/api";
import { AnalysisResultsView } from "@/components/platform/AnalysisResultsView";
import ScreenshotGuard from "@/components/platform/ScreenshotGuard";
import { MatchHeader } from "@/components/platform/MatchHeader";
import H2HCard from "@/components/platform/H2HCard";
import { TeamRecentBlock } from "@/components/platform/TeamRecentBlock";
import { motion } from "framer-motion";

export default function SharedAnalysisPage() {
  const params = useParams();
  const router = useRouter();
  const token = String(params.token);

  const [data, setData] = useState<SharedAnalysisPublic | null>(null);
  const [teamIds, setTeamIds] = useState<Record<string, number>>({});
  const [scorers, setScorers] = useState<ScorersResponse | null>(null);
  const [h2hData, setH2hData] = useState<any>(null);
  const [loadingH2H, setLoadingH2H] = useState(false);
  const [errorH2H, setErrorH2H] = useState(false);

  const [homeForm, setHomeForm] = useState<{ matches: RecentMatch[]; total: number }>({ matches: [], total: 0 });
  const [awayForm, setAwayForm] = useState<{ matches: RecentMatch[]; total: number }>({ matches: [], total: 0 });
  const [homeAnomalies, setHomeAnomalies] = useState<Anomaly[]>([]);
  const [awayAnomalies, setAwayAnomalies] = useState<Anomaly[]>([]);
  const [loadingHome, setLoadingHome] = useState(false);
  const [loadingAway, setLoadingAway] = useState(false);
  const [errorHome, setErrorHome] = useState<false | 'not_found' | 'error'>(false);
  const [errorAway, setErrorAway] = useState<false | 'not_found' | 'error'>(false);

  const [notFound, setNotFound] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setNotFound(false);

    api.sharedAnalysis(token)
      .then(async (d) => {
        if (cancelled) return;
        setData(d);

        const [ids, sc] = await Promise.all([
          Promise.all([api.teamIds("selecao"), api.teamIds("clube")]).then(([sel, clu]) => ({ ...sel, ...clu })),
          api.scorers(d.home_team, d.away_team, d.scope).catch(() => null),
        ]);
        if (cancelled) return;
        setTeamIds(ids);
        setScorers(sc);

        // Busca H2H, forma recente e anomalias
        setLoadingH2H(true); setErrorH2H(false);
        api.h2h(d.home_team, d.away_team, d.scope)
          .then(h => setH2hData(h?.metrics ?? null))
          .catch(() => { setH2hData(null); setErrorH2H(true); })
          .finally(() => setLoadingH2H(false));

        setLoadingHome(true); setErrorHome(false);
        Promise.all([
          api.recentMatches(d.home_team, d.scope).then(res => setHomeForm({ matches: res.matches, total: res.total_matches })),
          api.teamAnomalies(d.home_team, d.scope).then(res => setHomeAnomalies(res.anomalies)),
        ]).catch((e) => setErrorHome(e?.status === 404 ? 'not_found' : 'error')).finally(() => setLoadingHome(false));

        setLoadingAway(true); setErrorAway(false);
        Promise.all([
          api.recentMatches(d.away_team, d.scope).then(res => setAwayForm({ matches: res.matches, total: res.total_matches })),
          api.teamAnomalies(d.away_team, d.scope).then(res => setAwayAnomalies(res.anomalies)),
        ]).catch((e) => setErrorAway(e?.status === 404 ? 'not_found' : 'error')).finally(() => setLoadingAway(false));
      })
      .catch(() => { if (!cancelled) setNotFound(true); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [token]);

  if (loading) {
    return <div className="flex justify-center py-24"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
  }

  if (notFound || !data) {
    return (
      <div className="max-w-md mx-auto text-center py-24 space-y-3">
        <AlertTriangle className="w-8 h-8 mx-auto text-amber-500" />
        <p className="text-sm text-muted-foreground">Este link de análise não existe mais ou foi desativado.</p>
        <Link href="/" className="text-primary font-medium underline">Voltar para a home</Link>
      </div>
    );
  }

  const openMatch = (teamId: string) => (m: RecentMatch) => {
    const mh = m.is_home ? teamId : m.opponent;
    const ma = m.is_home ? m.opponent : teamId;
    router.push(`/estatisticas?home=${encodeURIComponent(mh)}&away=${encodeURIComponent(ma)}&date=${encodeURIComponent(m.date.slice(0, 10))}`);
  };

  const hasH2H = h2hData && (h2hData.h2h_played ?? 0) > 0;

  return (
    <div className="space-y-6">
      <MatchHeader
        home={data.home_team}
        away={data.away_team}
        teamIds={teamIds}
        competition={data.tournament}
        date={data.match_date || undefined}
        neutral={data.neutral}
      />

      {/* RESUMO DO CONFRONTO DIRETO E ÚLTIMOS JOGOS */}
      {!hasH2H && !loadingH2H ? (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
          <div className="bg-card border border-border/50 rounded-xl p-5 text-center shadow-sm">
            <h3 className="text-sm font-bold uppercase mb-1">Resumo do Confronto Direto</h3>
            <p className="text-sm text-muted-foreground italic">Não há confrontos diretos entre estas equipes em nossa base de dados</p>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">
            <div className="min-w-0 flex-1">
              <TeamRecentBlock teamId={data.home_team} form={homeForm} anomalies={homeAnomalies} label="Mandante" loading={loadingHome} error={errorHome} teamIds={teamIds} onOpenMatch={openMatch(data.home_team)} />
            </div>
            <div className="min-w-0 flex-1">
              <TeamRecentBlock teamId={data.away_team} form={awayForm} anomalies={awayAnomalies} label="Visitante" loading={loadingAway} error={errorAway} teamIds={teamIds} onOpenMatch={openMatch(data.away_team)} />
            </div>
          </div>
        </motion.div>
      ) : (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">
          <div className="min-w-0">
            {loadingH2H && !h2hData ? (
              <div className="bg-card border border-border/50 rounded-xl p-5 h-full flex items-center justify-center gap-2 text-muted-foreground text-sm">
                <div className="w-4 h-4 border-2 border-muted-foreground/30 border-t-emerald-500 rounded-full animate-spin" />
                Buscando confronto direto…
              </div>
            ) : errorH2H ? (
              <div className="bg-card border border-border/50 rounded-xl p-5 h-full flex items-center justify-center gap-2 text-sm text-amber-500/80 text-center">
                <AlertTriangle className="w-4 h-4 shrink-0" /> Não foi possível carregar os dados. Tente novamente em instantes.
              </div>
            ) : (
              <H2HCard h2hData={h2hData} home={data.home_team} away={data.away_team} teamIds={teamIds} />
            )}
          </div>
          <div className="flex flex-col gap-4 h-full">
            <div className="flex-1">
              <TeamRecentBlock teamId={data.home_team} form={homeForm} anomalies={homeAnomalies} label="Mandante" loading={loadingHome} error={errorHome} teamIds={teamIds} onOpenMatch={openMatch(data.home_team)} />
            </div>
            <div className="flex-1">
              <TeamRecentBlock teamId={data.away_team} form={awayForm} anomalies={awayAnomalies} label="Visitante" loading={loadingAway} error={errorAway} teamIds={teamIds} onOpenMatch={openMatch(data.away_team)} />
            </div>
          </div>
        </motion.div>
      )}

      <ScreenshotGuard page="analise-compartilhada">
        <AnalysisResultsView
          prediction={data.snapshot}
          home={data.home_team}
          away={data.away_team}
          teamIds={teamIds}
          scorers={scorers}
        />
      </ScreenshotGuard>

      <div className="max-w-2xl mx-auto text-center rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-6 mt-10">
        <p className="text-base font-semibold mb-2">Quer fazer suas próprias análises, de qualquer partida?</p>
        <p className="text-sm text-muted-foreground mb-4">Cadastre-se no nosso site, e sua primeira análise é de graça!</p>
        <Link
          href="/cadastro"
          className="inline-flex px-5 py-2.5 rounded-lg text-sm font-bold bg-gradient-to-r from-emerald-500 to-cyan-500 text-white hover:opacity-90 transition-opacity"
        >
          Criar minha conta grátis →
        </Link>
      </div>
    </div>
  );
}
