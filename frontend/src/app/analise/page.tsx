"use client";
import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Coins, Loader2, Sparkles, TrendingUp } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { api, PredictionResponse, UpcomingFixture } from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { analysisApi, type AnalysisResponse } from "@/lib/monetizationApi";
import { TeamSelect } from "@/components/platform/TeamSelect";
import { MatchPickerModal } from "@/components/platform/MatchPickerModal";
import { MatchHeader } from "@/components/platform/MatchHeader";
import PredictionDisplay from "@/components/platform/PredictionDisplay";
import BetBuilder from "@/components/platform/BetBuilder";
import { teamPt } from "@/lib/teamNames";

export default function AnalisePage() {
  const { user, wallet, loading: authLoading, refreshWallet } = useAuth();
  const router = useRouter();

  const [teams, setTeams] = useState<string[]>([]);
  const [tournaments, setTournaments] = useState<string[]>([]);
  const [upcoming, setUpcoming] = useState<UpcomingFixture[]>([]);
  const [teamIds, setTeamIds] = useState<Record<string, number>>({});

  const [mode, setMode] = useState<"independente" | "futura">("independente");
  const [home, setHome] = useState("");
  const [away, setAway] = useState("");
  const [tournament, setTournament] = useState("Copa do Mundo");
  const [neutral, setNeutral] = useState(false);
  const [fixtureId, setFixtureId] = useState<number | null>(null);
  const [matchDate, setMatchDate] = useState<string | undefined>();
  const [modalOpen, setModalOpen] = useState(false);

  const [generating, setGenerating] = useState(false);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [h2hData, setH2hData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { if (!authLoading && !user) router.replace("/entrar"); }, [authLoading, user, router]);

  useEffect(() => {
    api.teams().then((r) => { setTeams(r.teams); setTournaments(r.tournaments); }).catch(() => {});
    api.upcomingFixtures().then((r) => setUpcoming(r.fixtures)).catch(() => {});
    api.teamIds().then(setTeamIds).catch(() => {});
  }, []);

  const pickFuture = (fx: UpcomingFixture) => {
    setHome(fx.home); setAway(fx.away); setTournament(fx.tournament);
    setNeutral(fx.neutral); setFixtureId(Number(fx.fixture_id)); setMatchDate(fx.date); setAnalysis(null);
  };

  const canGenerate = home && away && home !== away && (mode === "independente" || fixtureId);
  const credits = wallet ? Math.floor(Number(wallet.available_balance)) : 0;

  const generate = useCallback(async () => {
    if (!canGenerate) return;
    setGenerating(true); setErr(null); setAnalysis(null); setH2hData(null);
    api.h2h(home, away).then((h) => setH2hData(h?.metrics ?? null)).catch(() => {});
    try {
      const a = await analysisApi.create({
        home_team: home, away_team: away, tournament, neutral,
        type: mode === "futura" ? "future_match" : "independent",
        fixture_id: mode === "futura" ? fixtureId : null,
      });
      setAnalysis(a);
      await refreshWallet();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setGenerating(false);
    }
  }, [canGenerate, home, away, tournament, neutral, mode, fixtureId, refreshWallet]);

  if (authLoading || !user) {
    return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2"><TrendingUp className="w-6 h-6 text-emerald-500" /> Análise</h1>
        <Link href="/carteira" className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-md bg-emerald-500/10 text-emerald-600 font-semibold hover:bg-emerald-500/20">
          <Coins className="w-4 h-4" /> {credits} créditos
        </Link>
      </div>

      {home && away && (
        <MatchHeader home={home} away={away} teamIds={teamIds} competition={tournament} date={matchDate} referee="" neutral={neutral} />
      )}

      {/* 1-2. Configuração */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="bg-card border border-border/50 rounded-xl p-5">
        <h2 className="text-lg font-heading font-bold mb-4">Configuração da análise</h2>

        <div className="inline-flex p-1 mb-4 rounded-lg bg-muted text-xs font-medium">
          <button onClick={() => { setMode("futura"); }} className={`px-3 py-1.5 rounded-md transition ${mode === "futura" ? "bg-background shadow-sm" : "text-muted-foreground"}`}>Partida futura</button>
          <button onClick={() => { setMode("independente"); setFixtureId(null); setMatchDate(undefined); }} className={`px-3 py-1.5 rounded-md transition ${mode === "independente" ? "bg-background shadow-sm" : "text-muted-foreground"}`}>Análise independente</button>
        </div>

        <p className="text-xs text-muted-foreground mb-3">
          {mode === "futura"
            ? "Partida oficial futura: reserva 1 crédito e habilita a Aposta Escolhida (Só Paga se Acertar)."
            : "Escolha livre de duas seleções: consome 1 crédito. Sem acompanhamento de resultado."}
        </p>

        {mode === "futura" ? (
          <button onClick={() => setModalOpen(true)} className="px-4 py-2 rounded-lg text-sm font-medium border border-cyan-500/40 bg-cyan-500/10 hover:bg-cyan-500/20 transition">
            {home && away ? `${teamPt(home)} x ${teamPt(away)} — trocar partida` : "Escolher partida agendada"}
          </button>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <Label className="text-xs text-muted-foreground mb-1.5 block">Mandante</Label>
              <TeamSelect value={home} onValueChange={(v) => { setHome(v); setAnalysis(null); }} teams={teams.filter((t) => t !== away)} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground mb-1.5 block">Visitante</Label>
              <TeamSelect value={away} onValueChange={(v) => { setAway(v); setAnalysis(null); }} teams={teams.filter((t) => t !== home)} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground mb-1.5 block">Competição</Label>
              <Select value={tournament} onValueChange={setTournament}>
                <SelectTrigger className="h-10"><SelectValue /></SelectTrigger>
                <SelectContent>{tournaments.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="flex items-end pb-2">
              <div className="flex items-center gap-2">
                <Switch id="neu" checked={neutral} onCheckedChange={setNeutral} />
                <Label htmlFor="neu" className="text-sm cursor-pointer">Campo neutro</Label>
              </div>
            </div>
          </div>
        )}
      </motion.div>

      <MatchPickerModal open={modalOpen} onOpenChange={setModalOpen} fixtures={upcoming} teamIds={teamIds} onSelect={pickFuture} title="Selecionar partida futura" />

      {err && (
        <div className="text-sm rounded-md bg-red-500/10 text-red-600 p-3">
          {err}{err.includes("insuficiente") && <> <Link href="/carteira" className="underline font-medium">Comprar créditos</Link>.</>}
        </div>
      )}

      {/* 3. Gerar */}
      <div className="flex justify-center">
        <Button onClick={generate} disabled={!canGenerate || generating || credits < 1} size="lg"
          className="bg-gradient-to-r from-emerald-500 to-cyan-500 text-white">
          {generating ? <span className="flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Gerando...</span>
            : (<><Sparkles className="w-4 h-4 mr-2" /> Gerar análise (1 crédito)</>)}
        </Button>
      </div>
      {credits < 1 && <p className="text-center text-sm text-muted-foreground">Sem créditos. <Link href="/carteira" className="text-primary underline">Comprar</Link>.</p>}

      {/* 4. Exibição + 5. Aposta */}
      {analysis && (
        <div className="space-y-6">
          <div className="text-center text-xs text-muted-foreground">
            {analysis.credits_consumed ? "1 crédito consumido." : "1 crédito reservado."} Análise #{analysis.id.slice(0, 8)} · v{analysis.algo_version}
          </div>

          <PredictionDisplay projection={analysis.snapshot as unknown as PredictionResponse} home={home} away={away} teamIds={teamIds} h2hData={h2hData} />

          {analysis.type === "future_match" && (
            <div className="pt-2">
              <h3 className="text-lg font-heading font-bold mb-3 border-b border-border/50 pb-2">Construção da aposta</h3>
              <BetBuilder analysisId={analysis.id} onConfirmed={() => refreshWallet()} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
