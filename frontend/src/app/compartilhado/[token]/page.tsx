"use client";
import React, { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Loader2, AlertTriangle } from "lucide-react";
import { api, type SharedAnalysisPublic, type ScorersResponse } from "@/lib/api";
import { AnalysisResultsView } from "@/components/platform/AnalysisResultsView";
import ScreenshotGuard from "@/components/platform/ScreenshotGuard";
import { teamPt } from "@/lib/teamNames";

// Página pública (sem cadastro/login) de uma análise gerada e publicada pelo admin --
// porta de entrada para novos usuários. Reaproveita o mesmo AnalysisResultsView da
// página autenticada, sem "Monte sua Seleção" (depende de analysisId/carteira, fora
// de escopo aqui).
export default function SharedAnalysisPage() {
  const params = useParams();
  const token = String(params.token);

  const [data, setData] = useState<SharedAnalysisPublic | null>(null);
  const [teamIds, setTeamIds] = useState<Record<string, number>>({});
  const [scorers, setScorers] = useState<ScorersResponse | null>(null);
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

  return (
    <div className="space-y-6">
      <div className="text-center">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-cyan-600 dark:text-cyan-400 mb-1">Análise Compartilhada</p>
        <h1 className="font-heading font-extrabold text-2xl sm:text-3xl">
          {teamPt(data.home_team)} <span className="text-muted-foreground">x</span> {teamPt(data.away_team)}
        </h1>
        <p className="text-sm text-muted-foreground mt-1">{data.tournament}</p>
      </div>

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
