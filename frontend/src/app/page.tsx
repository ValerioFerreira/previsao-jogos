"use client";
import React, { useState, useCallback, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { AlertTriangle, Zap, TrendingUp, ShieldAlert, ShieldCheck, ArrowDown, CheckCircle2, Clock, X } from 'lucide-react';
import { api, PredictionResponse, RecentMatch, Anomaly, UpcomingFixture, teamLogoUrl, onImgError } from '@/lib/api';
import InfoTooltip from '@/components/platform/InfoTooltip';
import { usePrediction } from '@/lib/PredictionContext';
import { TeamSelect } from '@/components/platform/TeamSelect';
import { teamPt } from '@/lib/teamNames';
import { competitionPt } from '@/lib/competitionNames';
import { MatchPickerModal } from '@/components/platform/MatchPickerModal';
import { MatchHeader } from '@/components/platform/MatchHeader';
import Link from 'next/link';
import { Coins, Sparkles, FileText, PenTool } from 'lucide-react';
import { useAuth } from '@/lib/AuthContext';
import { analysisApi } from '@/lib/monetizationApi';
import BetBuilder from '@/components/platform/BetBuilder';
import H2HCard from '@/components/platform/H2HCard';
import ScreenshotGuard from '@/components/platform/ScreenshotGuard';
import type { ScorersResponse } from '@/lib/api';
import { AnalysisResultsView, SectionDivider } from '@/components/platform/AnalysisResultsView';
import OpportunitiesSection from '@/components/platform/OpportunitiesSection';

// Data em dd/mm/aaaa a partir de "aaaa-mm-dd[...]".
function formatDateBR(s: string): string {
  const d = (s || '').slice(0, 10).split('-');
  return d.length === 3 ? `${d[2]}/${d[1]}/${d[0]}` : s;
}

// Data e hora da partida (dd/mm/aaaa hh:mm) para uso em textos como a oferta ParcerIA.
function fmtMatchDateTime(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

const CLUB_LEAGUES = [
  "Brasileirão Série A", "Brasileirão Série B", "Copa do Brasil", "Libertadores",
  "Champions League", "Premier League", "La Liga", "Bundesliga", "Serie A (Itália)", "Ligue 1",
];

// Cronômetro removido a pedido.

// Anúncio no topo da Análise — mercados de clubes chegando, com contagem regressiva.
// Dispensável (fica escondido em localStorage) para não incomodar quem já viu.
// v4: versão bumped e fundo deixou de depender de imagem externa hotlinked (pngtree bloqueia
// requisições sem contexto de navegador com uma página HTML de verificação — em vez de servir a
// imagem, o que fazia a seção inteira sumir em alguns celulares/redes). Fundo agora é 100% CSS.
const NEWS_BANNER_KEY = "apostai:news_banner_v4_dismissed";
function ClubMarketsBanner({ onExplore }: { onExplore: () => void }) {
  const [dismissed, setDismissed] = useState(true);
  useEffect(() => {
    try { setDismissed(localStorage.getItem(NEWS_BANNER_KEY) === "1"); } catch { setDismissed(false); }
  }, []);
  if (dismissed) return null;
  function dismiss() {
    try { localStorage.setItem(NEWS_BANNER_KEY, "1"); } catch { /* ignora */ }
    setDismissed(true);
  }
  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="relative overflow-hidden rounded-2xl border border-emerald-500/20 bg-card p-6 sm:p-8 shadow-xl shadow-emerald-950/10"
    >
      {/* Background vector pattern and glow */}
      <div className="absolute -top-24 -right-24 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute -bottom-24 -left-24 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute inset-0 bg-[radial-gradient(#10b981_1px,transparent_1px)] [background-size:24px_24px] opacity-10 pointer-events-none" />

      <button onClick={dismiss} aria-label="Fechar aviso" className="absolute top-3.5 right-3.5 text-muted-foreground hover:text-foreground transition-colors z-10 p-1 rounded-md hover:bg-muted/40">
        <X className="w-4 h-4" />
      </button>

      <div className="relative flex flex-col items-center text-center gap-4 max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[11px] font-mono font-bold uppercase tracking-wider">
          <Sparkles className="w-3 h-3" /> Modelo Quantitativo Atualizado
        </div>

        <h2 className="font-heading font-extrabold text-2xl sm:text-4xl text-foreground leading-tight tracking-tight">
          Inteligência Estatística para <span className="bg-gradient-to-r from-emerald-400 via-teal-400 to-cyan-400 bg-clip-text text-transparent">Clubes & Ligas</span>
        </h2>

        <p className="text-xs sm:text-sm text-muted-foreground max-w-xl leading-relaxed">
          Projeções matemáticas calibradas com Dixon-Coles, xG projetado e modelo de goleadores para mais de 40 competições globais.
        </p>

        <div className="flex flex-wrap justify-center gap-1.5 max-w-2xl my-1">
          {CLUB_LEAGUES.map((l) => (
            <span key={l} className="text-[11px] font-medium bg-muted/60 border border-border/50 text-foreground/80 rounded-lg px-2.5 py-1">
              {l}
            </span>
          ))}
          <span className="text-[11px] font-semibold bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 rounded-lg px-2.5 py-1">
            + 36 Ligas Globais
          </span>
        </div>

        <button
          onClick={() => { dismiss(); onExplore(); }}
          className="mt-2 px-6 py-2.5 rounded-xl text-xs font-bold bg-gradient-to-r from-emerald-500 to-cyan-500 text-slate-950 hover:brightness-110 transition-all shadow-lg shadow-emerald-500/20 active:scale-[0.98] cursor-pointer"
        >
          Explorar confronto de clubes →
        </button>
      </div>
    </motion.div>
  );
}

function startsInLessThanHour(iso?: string): boolean {
  if (!iso) return false;
  const matchTime = new Date(iso).getTime();
  if (isNaN(matchTime)) return false;
  const now = Date.now();
  const diffMs = matchTime - now;
  return diffMs > 0 && diffMs <= 3600000;
}

function FeaturedMatchesBanner({
  matches, teamIds, onPick,
}: {
  matches: UpcomingFixture[];
  teamIds: Record<string, number>;
  onPick: (fx: UpcomingFixture) => void;
}) {
  if (!matches.length) return null;

  const sortedMatches = React.useMemo(() => {
    return [...matches].sort((a, b) => {
      const ta = new Date(a.date).getTime() || 0;
      const tb = new Date(b.date).getTime() || 0;
      return ta - tb;
    });
  }, [matches]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="relative overflow-hidden border-b border-border/70 border-t-0 border-x-0 bg-transparent p-5 sm:p-7 sm:py-9"
    >
      {/* Imagem de Fundo com Alta Nitidez e Fade Profundo no topo e nas laterais para fusão 100% invisível das bordas com o fundo */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden z-0">
        <img
          src="/images/background-partidas-destaque.jpg"
          alt=""
          className="w-full h-full object-cover blur-[2px] scale-105 opacity-80 dark:opacity-75 dark:grayscale-0 grayscale contrast-110 brightness-105 transition-all duration-500"
        />
        {/* Overlay de gradiente base */}
        <div className="absolute inset-0 bg-gradient-to-b from-card/10 via-card/40 to-card/75" />
        
        {/* Fade Superior (Topo) com fusão total na cor da tela */}
        <div className="absolute top-0 left-0 right-0 h-32 bg-gradient-to-b from-background via-background/90 via-50% to-transparent pointer-events-none z-10" />
        
        {/* Fade Lateral Esquerdo com fusão total */}
        <div className="absolute top-0 bottom-0 left-0 w-32 bg-gradient-to-r from-background via-background/90 via-50% to-transparent pointer-events-none z-10" />
        
        {/* Fade Lateral Direito com fusão total */}
        <div className="absolute top-0 bottom-0 right-0 w-32 bg-gradient-to-l from-background via-background/90 via-50% to-transparent pointer-events-none z-10" />

        <div className="absolute top-0 right-0 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none" />
      </div>

      {/* Conteúdo em z-20 (100% à frente da imagem e dos fades, garantindo nitidez total nos textos) */}
      <div className="relative z-20 flex flex-col items-center text-center gap-5">
        <div>
          <h2 className="font-heading font-extrabold text-xl sm:text-3xl text-foreground tracking-tight flex items-center justify-center gap-2 flex-wrap drop-shadow">
            <span className="text-foreground">PARTIDAS EM</span>
            <motion.span
              animate={{ opacity: [0.85, 1, 0.85], scale: [0.98, 1.03, 0.98] }}
              transition={{ repeat: Infinity, duration: 3, ease: "easeInOut" }}
              className="bg-gradient-to-r from-emerald-400 via-cyan-400 to-teal-300 bg-clip-text text-transparent drop-shadow-md font-black"
            >
              DESTAQUE
            </motion.span>
          </h2>
          <p className="text-xs sm:text-sm text-muted-foreground mt-1 font-medium drop-shadow-sm">
            Selecione uma partida para ver a análise completa
          </p>
        </div>

        <div className="flex flex-wrap justify-center gap-3.5 max-w-5xl w-full mx-auto">
          {sortedMatches.map((fx) => (
            <motion.button
              key={fx.fixture_id}
              onClick={() => onPick(fx)}
              whileHover={{ y: -4, scale: 1.03 }}
              transition={{ type: "spring", stiffness: 400, damping: 25 }}
              className="group/match relative flex flex-col items-center justify-between gap-2 p-3.5 rounded-xl border border-border/80 bg-card/85 backdrop-blur-xl hover:bg-card/95 hover:border-emerald-500/60 transition-colors w-[calc(50%-0.5rem)] sm:w-[190px] text-center cursor-pointer shadow-lg shadow-black/30 hover:shadow-2xl hover:shadow-emerald-500/20"
            >
              {startsInLessThanHour(fx.date) && (
                <div className="absolute -top-2.5 left-1/2 -translate-x-1/2 z-10 pointer-events-none whitespace-nowrap">
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-red-500/20 border border-red-500/50 text-red-400 text-[8.5px] font-mono font-extrabold uppercase tracking-wider animate-pulse shadow-md shadow-red-500/30 backdrop-blur-md">
                    <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-ping" />
                    Inicia em menos de 1 hora
                  </span>
                </div>
              )}

              <div className="flex items-center justify-center gap-2 pt-1">
                <img src={teamLogoUrl(teamIds[fx.home]) || undefined} onError={onImgError} alt="" className="w-6 h-6 object-contain drop-shadow" />
                <span className="text-[10px] font-mono font-bold text-muted-foreground">VS</span>
                <img src={teamLogoUrl(teamIds[fx.away]) || undefined} onError={onImgError} alt="" className="w-6 h-6 object-contain drop-shadow" />
              </div>

              <div className="text-[12px] font-bold text-foreground leading-snug group-hover/match:text-emerald-400 transition-colors">
                {teamPt(fx.home)} <span className="text-muted-foreground font-normal">x</span> {teamPt(fx.away)}
              </div>

              <div className="text-[10px] text-muted-foreground truncate w-full">{competitionPt(fx.tournament)}</div>
              <div className="text-[9.5px] font-mono text-muted-foreground font-medium bg-muted/40 border border-border/40 px-2 py-0.5 rounded">{fmtMatchDateTime(fx.date)}</div>
            </motion.button>
          ))}
        </div>
      </div>
    </motion.div>
  );
}

import { TeamRecentBlock } from '@/components/platform/TeamRecentBlock';

export default function Previsoes() {
  const [teams, setTeams] = React.useState<string[]>([]);
  const [tournaments, setTournaments] = React.useState<string[]>([]);
  // Catálogo completo de competições dos DOIS escopos -- alimenta o grid do
  // MatchPickerModal (que tem seu próprio toggle de escopo interno), pra listar TODA
  // competição treinada mesmo sem jogo agendado nela.
  const [allCompetitions, setAllCompetitions] = React.useState<{ selecao: string[]; clube: string[] }>({ selecao: [], clube: [] });

  const router = useRouter();
  const {
    homeTeamId, setHomeTeamId, awayTeamId, setAwayTeamId, competition, setCompetition, neutralField, setNeutralField,
    scope, setScope, analysis, setAnalysis, mode, setMode, fixtureId, setFixtureId, matchDate, setMatchDate,
  } = usePrediction();
  const { user, wallet, refreshWallet } = useAuth();

  const [loading, setLoading] = useState(false);
  // projection é derivada da análise persistida no contexto — só ativa se os times baterem com a seleção atual
  const projection = (analysis && analysis.home_team === homeTeamId && analysis.away_team === awayTeamId)
    ? (analysis.snapshot as unknown as PredictionResponse)
    : null;
  const setProjection = (_: PredictionResponse | null) => { if (_ === null) setAnalysis(null); };
  const [errMsg, setErrMsg] = useState<string | null>(null);
  // available + promo: ambos são gastáveis em análise (ver analysis/service.py::create_analysis).
  // Não conta o crédito diário grátis nem a conta demo — esses não passam pelo saldo,
  // então o botão nunca deve travar por causa deles (ver `disabled` abaixo).
  const credits = wallet ? Math.floor(Number(wallet.available_balance) + Number(wallet.promo_balance || 0)) : 0;
  
  const [homeForm, setHomeForm] = useState<{matches: RecentMatch[], total: number}>({matches: [], total: 0});
  const [awayForm, setAwayForm] = useState<{matches: RecentMatch[], total: number}>({matches: [], total: 0});
  const [homeAnomalies, setHomeAnomalies] = useState<Anomaly[]>([]);
  const [awayAnomalies, setAwayAnomalies] = useState<Anomaly[]>([]);
  
  const [h2hData, setH2hData] = useState<any>(null);
  const [scorers, setScorers] = useState<ScorersResponse | null>(null);
  // F5: com as duas equipes escolhidas, o card de Configuração recolhe (só o título);
  // "Alterar Equipes" (no cabeçalho flutuante) reabre para trocar.
  const [editingTeams, setEditingTeams] = useState(false);

  // Prováveis goleadores (modelo de goleador) — busca ao gerar a análise. Sem props de
  // jogador para clubes ainda (get_scorers retorna disponivel:false, ScorersCard some).
  React.useEffect(() => {
    if (analysis && homeTeamId && awayTeamId && homeTeamId !== awayTeamId) {
      api.scorers(homeTeamId, awayTeamId, scope).then(setScorers).catch(() => setScorers(null));
    } else {
      setScorers(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analysis]);

  // Busca o H2H assim que as duas seleções estão escolhidas — o card de confronto
  // direto fica disponível ANTES de gerar a análise (e persiste ao voltar à página).
  const [errorH2H, setErrorH2H] = useState(false);
  React.useEffect(() => {
    if (homeTeamId && awayTeamId && homeTeamId !== awayTeamId) {
      setLoadingH2H(true); setErrorH2H(false);
      api.h2h(homeTeamId, awayTeamId, scope).then(h => setH2hData(h?.metrics ?? null))
        .catch(() => { setH2hData(null); setErrorH2H(true); }).finally(() => setLoadingH2H(false));
    } else {
      setH2hData(null); setLoadingH2H(false); setErrorH2H(false);
    }
  }, [homeTeamId, awayTeamId, scope]);

  // Modo de análise (mode) e data (matchDate) vêm do contexto (persistem ao navegar).
  const [referee, setReferee] = useState('');
  const [referees, setReferees] = useState<string[]>([]);
  const [upcoming, setUpcoming] = useState<UpcomingFixture[]>([]);
  const [featured, setFeatured] = useState<UpcomingFixture[]>([]);
  const [teamIds, setTeamIds] = useState<Record<string, number>>({});
  const [modalOpen, setModalOpen] = useState(false);
  const [loadingUpcoming, setLoadingUpcoming] = useState(false);
  const [loadingHome, setLoadingHome] = useState(false);
  const [loadingAway, setLoadingAway] = useState(false);
  const [loadingH2H, setLoadingH2H] = useState(false);

  React.useEffect(() => {
    api.referees().then(r => setReferees(r.referees)).catch(() => {});
    setLoadingUpcoming(true);
    api.upcomingFixtures().then(r => setUpcoming(r.fixtures)).catch(() => {}).finally(() => setLoadingUpcoming(false));
    api.featuredMatches().then(r => setFeatured(r.items)).catch(() => {});
    // Uma única lista com os dois escopos -- evita ter que refazer o fetch a cada troca
    // de Seleções/Clubes; nomes de seleção e de clube não colidem entre si.
    Promise.all([api.teamIds("selecao"), api.teamIds("clube")])
      .then(([sel, clu]) => setTeamIds({ ...sel, ...clu })).catch(() => {});
  }, []);

  // Confronto selecionado que já começou (aba aberta há horas, ou seleção reidratada do
  // localStorage num dia seguinte): limpa a seleção em vez de deixar gerar análise de um
  // jogo que já aconteceu. Roda ao montar e depois periodicamente enquanto a aba fica aberta.
  React.useEffect(() => {
    const checkStale = () => {
      const now = Date.now();
      const cutoff24h = now - 24 * 3600 * 1000;
      setUpcoming((prev) => prev.filter((f) => !f.date || new Date(f.date).getTime() > cutoff24h));
      // Partida expira 3h após o apito inicial (após encerramento)
      if (mode === 'futura' && matchDate && (new Date(matchDate).getTime() + 3 * 3600 * 1000) <= now) {
        setHomeTeamId('');
        setAwayTeamId('');
        setFixtureId(null);
        setMatchDate(undefined);
        setAnalysis(null);
        setProjection(null);
        setErrMsg('Esta partida já aconteceu. Para informações sobre a mesma, vá à página de Estatísticas.');
      }
    };
    checkStale();
    const id = setInterval(checkStale, 10000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, matchDate]);

  const selectFutureFixture = (fid: string) => {
    const fx = upcoming.find(f => f.fixture_id === fid);
    if (!fx) return;
    setScope(fx.scope || 'selecao'); // o sistema identifica sozinho pela liga da partida
    setHomeTeamId(fx.home);
    setAwayTeamId(fx.away);
    setCompetition(fx.tournament);
    setNeutralField(fx.neutral);
    setMatchDate(fx.date);
    setFixtureId(Number(fx.fixture_id));
    setProjection(null);
    setEditingTeams(false); // recolhe o card de configuração após escolher a partida
  };

  // Card de "Partidas em Destaque" (curadoria do admin): pré-preenche o confronto e o
  // modo "partida futura", igual selectFutureFixture, mas a partir do objeto já resolvido
  // pelo banner (não depende de já estar carregado em `upcoming`) -- só falta apertar
  // "Gerar Análise", como pedido.
  const selectFeaturedMatch = (fx: UpcomingFixture) => {
    setMode('futura');
    setScope(fx.scope || 'selecao');
    setHomeTeamId(fx.home);
    setAwayTeamId(fx.away);
    setCompetition(fx.tournament);
    setNeutralField(fx.neutral);
    setMatchDate(fx.date);
    setFixtureId(Number(fx.fixture_id));
    setProjection(null);
    setEditingTeams(false);
  };

  // Troca de escopo (Seleções/Clubes) na Análise Independente: roster e competições são
  // outros, então zera a escolha de times/competição em vez de manter algo inválido.
  const changeScope = (s: 'selecao' | 'clube') => {
    if (s === scope) return;
    setScope(s);
    setHomeTeamId('');
    setAwayTeamId('');
    setFixtureId(null);
    setAnalysis(null);
    setDeepAnalysisInfo(null);
    setProjection(null);
  };

  React.useEffect(() => {
    api.teams(scope).then(res => {
      setTeams(res.teams);
      setTournaments(res.tournaments);
      // Só corrige a competição parada no ar quando o usuário está montando o confronto
      // manualmente (Análise Independente) -- não mexe quando veio de uma partida agendada
      // (selectFutureFixture já define a competição certa a partir da própria fixture).
      if (mode === 'independente' && (!competition || !res.tournaments.includes(competition))) {
        setCompetition(res.tournaments[0] || '');
      }
    }).catch(console.error);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scope]);

  React.useEffect(() => {
    Promise.all([api.teams('selecao'), api.teams('clube')])
      .then(([sel, clu]) => setAllCompetitions({ selecao: sel.tournaments, clube: clu.tournaments }))
      .catch(() => {});
  }, []);

  const [errorHome, setErrorHome] = useState<false | 'not_found' | 'error'>(false);
  const [errorAway, setErrorAway] = useState<false | 'not_found' | 'error'>(false);

  React.useEffect(() => {
    if (homeTeamId) {
      setLoadingHome(true); setErrorHome(false);
      Promise.all([
        api.recentMatches(homeTeamId, scope).then(res => setHomeForm({matches: res.matches, total: res.total_matches})),
        api.teamAnomalies(homeTeamId, scope).then(res => setHomeAnomalies(res.anomalies)),
      ]).catch((e) => { setErrorHome(e?.status === 404 ? 'not_found' : 'error'); }).finally(() => setLoadingHome(false));
    } else {
      setHomeForm({matches: [], total: 0});
      setHomeAnomalies([]);
      setErrorHome(false);
    }
  }, [homeTeamId, scope]);

  React.useEffect(() => {
    if (awayTeamId) {
      setLoadingAway(true); setErrorAway(false);
      Promise.all([
        api.recentMatches(awayTeamId, scope).then(res => setAwayForm({matches: res.matches, total: res.total_matches})),
        api.teamAnomalies(awayTeamId, scope).then(res => setAwayAnomalies(res.anomalies)),
      ]).catch((e) => { setErrorAway(e?.status === 404 ? 'not_found' : 'error'); }).finally(() => setLoadingAway(false));
    } else {
      setAwayForm({matches: [], total: 0});
      setAwayAnomalies([]);
      setErrorAway(false);
    }
  }, [awayTeamId, scope]);

  const [deepAnalysisInfo, setDeepAnalysisInfo] = useState<{ hasDeep: boolean; analystName: string | null; fixtureId: number | null } | null>(null);

  React.useEffect(() => {
    if (!homeTeamId || !awayTeamId) {
      setDeepAnalysisInfo(null);
      return;
    }
    const matched = (upcoming || []).find(f => (fixtureId && String(f.fixture_id) === String(fixtureId)) || (f.home === homeTeamId && f.away === awayTeamId))
      || (featured || []).find(f => (fixtureId && String(f.fixture_id) === String(fixtureId)) || (f.home === homeTeamId && f.away === awayTeamId));

    if (matched?.deep_analyst) {
      setDeepAnalysisInfo({
        hasDeep: true,
        analystName: matched.deep_analyst,
        fixtureId: matched.fixture_id ? Number(matched.fixture_id) : null,
      });
      return;
    }

    let cancelled = false;
    api.checkDeepAnalysis({ fixture_id: fixtureId ? Number(fixtureId) : undefined, home: homeTeamId, away: awayTeamId })
      .then(res => {
        if (cancelled) return;
        if (res.has_deep_analysis && res.analyst_name) {
          setDeepAnalysisInfo({
            hasDeep: true,
            analystName: res.analyst_name,
            fixtureId: res.fixture_id,
          });
        } else {
          setDeepAnalysisInfo(null);
        }
      })
      .catch(() => { if (!cancelled) setDeepAnalysisInfo(null); });

    return () => { cancelled = true; };
  }, [homeTeamId, awayTeamId, fixtureId, upcoming, featured]);

  const canGenerate = homeTeamId && awayTeamId && homeTeamId !== awayTeamId;

  const handleGenerate = useCallback(async () => {
    if (!canGenerate) return;
    if (!user) { router.push('/entrar'); return; }
    setLoading(true);
    setErrMsg(null);
    setAnalysis(null);

    const resolvedFixtureId = fixtureId ? Number(fixtureId) : (deepAnalysisInfo?.fixtureId ? Number(deepAnalysisInfo.fixtureId) : null);

    try {
      const a = await analysisApi.create({
        home_team: homeTeamId,
        away_team: awayTeamId,
        tournament: competition,
        neutral: neutralField,
        scope,
        type: mode === 'futura' ? 'future_match' : 'independent',
        fixture_id: resolvedFixtureId,
      });
      setAnalysis(a); // persiste no contexto — não some ao navegar e voltar
      await refreshWallet();
    } catch (e) {
      setErrMsg((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [canGenerate, user, homeTeamId, awayTeamId, competition, neutralField, scope, mode, fixtureId, deepAnalysisInfo, refreshWallet, router, setAnalysis]);

  // Verificador de Bets / Oportunidades Encontradas precisam do fixture_id da partida
  // exibida (mesma resolução usada em handleGenerate: seletor explícito > casado por
  // deep-analysis). Sem fixture_id (análise independente, sem jogo agendado casado),
  // os dois componentes simplesmente não renderizam odds reais.
  const resolvedFixtureIdForOdds = fixtureId ? Number(fixtureId) : (deepAnalysisInfo?.fixtureId ? Number(deepAnalysisInfo.fixtureId) : null);

  return (
    <div className="space-y-6">
      {featured.length > 0 && (
        <FeaturedMatchesBanner matches={featured} teamIds={teamIds} onPick={selectFeaturedMatch} />
      )}
      {homeTeamId && awayTeamId && (
        <MatchHeader
          home={homeTeamId}
          away={awayTeamId}
          teamIds={teamIds}
          competition={competition}
          date={matchDate}
          referee={referee}
          neutral={neutralField}
          onEditTeams={() => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
            setEditingTeams(true);
            setAnalysis(null);
            setFixtureId(null);
            setDeepAnalysisInfo(null);
            setProjection(null);
            if (mode === 'futura') {
              setModalOpen(true);
            }
          }}
        />
      )}
      {(canGenerate && !editingTeams) ? null : (
      <motion.div
        layout
        transition={{ layout: { duration: 0.4, ease: 'easeInOut' } }}
        initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
        className={`bg-card border border-border/50 rounded-xl p-5 mx-auto max-w-full ${mode === 'independente' ? 'w-full' : 'w-fit'}`}
      >
        <div className="flex items-center justify-between gap-2 mb-4">
          <h2 className="text-lg font-heading font-bold flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-emerald-500" /> Configuração do Confronto
          </h2>
          {canGenerate && editingTeams && (
            <button onClick={() => setEditingTeams(false)} className="text-xs font-medium text-muted-foreground hover:text-foreground border border-border/60 rounded-md px-3 py-1.5">
              Concluir
            </button>
          )}
        </div>

        {/* Modo de análise: partida futura agendada x análise independente */}
        <div className="inline-flex p-1 mb-4 rounded-lg bg-muted text-xs font-medium">
          <button
            onClick={() => setMode('futura')}
            className={`px-3 py-1.5 rounded-md transition-colors ${mode === 'futura' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
          >Selecionar Partida Agendada</button>
          <button
            onClick={() => {
              setMode('independente');
              setMatchDate(undefined);
              setFixtureId(null);
              setAnalysis(null);
              setDeepAnalysisInfo(null);
              setProjection(null);
            }}
            className={`px-3 py-1.5 rounded-md transition-colors ${mode === 'independente' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
          >Análise Independente</button>
          <InfoTooltip
            text={'Selecionar Partida Agendada: selecione uma partida agendada e reserve um crédito para gerar a análise — elegível para a Oferta "ParcerIA". Análise Independente: escolha duas equipes quaisquer, sem necessariamente haver um jogo marcado entre elas, e utilize um crédito para gerar a análise — não elegível para a Oferta "ParcerIA".'}
            href="/como-funciona#promocao"
            linkText='Clique para conhecer a Oferta "ParcerIA" →'
          />
        </div>

        {mode === 'independente' && (
          <div className="inline-flex p-1 mb-4 ml-2 rounded-lg bg-muted text-xs font-medium">
            <button
              onClick={() => changeScope('selecao')}
              className={`px-3 py-1.5 rounded-md transition-colors ${scope === 'selecao' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
            >Seleções</button>
            <button
              onClick={() => changeScope('clube')}
              className={`px-3 py-1.5 rounded-md transition-colors ${scope === 'clube' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
            >Clubes</button>
          </div>
        )}

        {mode === 'futura' && (
          <div className="mb-2 flex flex-col items-center text-center">
            <button onClick={() => !loadingUpcoming && setModalOpen(true)} disabled={loadingUpcoming}
              className="px-4 py-2 rounded-lg text-sm font-medium border border-cyan-500/40 bg-cyan-500/10 text-foreground hover:bg-cyan-500/20 transition-colors disabled:opacity-60 inline-flex items-center gap-2">
              {loadingUpcoming && <span className="w-3.5 h-3.5 border-2 border-current/30 border-t-current rounded-full animate-spin" />}
              {loadingUpcoming
                ? 'Buscando partidas agendadas…'
                : (homeTeamId && awayTeamId ? `${teamPt(homeTeamId)} x ${teamPt(awayTeamId)} — trocar partida` : 'Escolher partida agendada')}
            </button>
            {homeTeamId && awayTeamId && (
              <p className="text-[11px] text-muted-foreground mt-2">Competição: {competition} · {neutralField ? 'Campo neutro' : 'Com mando'}</p>
            )}
          </div>
        )}

        {mode === 'independente' && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            <div>
              <Label className="text-xs text-muted-foreground mb-1.5 block">Time Mandante</Label>
              <TeamSelect value={homeTeamId} onValueChange={v => { setHomeTeamId(v); setFixtureId(null); setAnalysis(null); setDeepAnalysisInfo(null); setProjection(null); }} teams={teams.filter(t => t !== awayTeamId)}
                placeholder={scope === 'clube' ? 'Buscar clube...' : undefined} searchPlaceholder={scope === 'clube' ? 'Buscar clube...' : undefined} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground mb-1.5 block">Time Visitante</Label>
              <TeamSelect value={awayTeamId} onValueChange={v => { setAwayTeamId(v); setFixtureId(null); setAnalysis(null); setDeepAnalysisInfo(null); setProjection(null); }} teams={teams.filter(t => t !== homeTeamId)}
                placeholder={scope === 'clube' ? 'Buscar clube...' : undefined} searchPlaceholder={scope === 'clube' ? 'Buscar clube...' : undefined} />
            </div>
            <div>
              <Label className="text-xs text-muted-foreground mb-1.5 block">Competição</Label>
              <Select value={competition} onValueChange={setCompetition}>
                <SelectTrigger className="h-10"><SelectValue placeholder="Selecione..." /></SelectTrigger>
                <SelectContent>{tournaments.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs text-muted-foreground mb-1.5 block flex items-center gap-1">
                Árbitro (opcional)
                <InfoTooltip text="Você pode informar o árbitro da partida. No momento não influencia os cálculos; ficará disponível para análises futuras." />
              </Label>
              <TeamSelect value={referee} onValueChange={setReferee} teams={referees} labelFn={(s) => s} placeholder="Buscar árbitro..." searchPlaceholder="Buscar árbitro..." />
            </div>
            <div className="flex items-end pb-2">
              <div className="flex items-center gap-2">
                <Switch id="neutral" checked={neutralField} onCheckedChange={setNeutralField} />
                <Label htmlFor="neutral" className="text-sm cursor-pointer">Campo Neutro</Label>
                <InfoTooltip text="Remove a vantagem de mando de campo do modelo preditivo." />
              </div>
            </div>
          </div>
        )}
      </motion.div>
      )}

      <MatchPickerModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        fixtures={upcoming}
        teamIds={teamIds}
        onSelect={(fx) => selectFutureFixture(fx.fixture_id)}
        title="Selecionar Partida Agendada"
        defaultScope={scope}
        allCompetitions={allCompetitions}
      />

      <AnimatePresence>
        {(homeTeamId || awayTeamId) && (() => {
          const both = homeTeamId && awayTeamId && homeTeamId !== awayTeamId;
          const openMatch = (teamId: string) => (m: RecentMatch) => {
            const mh = m.is_home ? teamId : m.opponent;
            const ma = m.is_home ? m.opponent : teamId;
            router.push(`/estatisticas?home=${encodeURIComponent(mh)}&away=${encodeURIComponent(ma)}&date=${encodeURIComponent(m.date.slice(0, 10))}`);
          };
          if (both) {
            const hasH2H = h2hData && (h2hData.h2h_played ?? 0) > 0;
            if (!hasH2H && !loadingH2H) {
              return (
                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="space-y-4">
                  <div className="bg-card border border-border/50 rounded-xl p-5 text-center shadow-sm">
                    <h3 className="text-sm font-bold uppercase mb-1">Resumo do Confronto Direto</h3>
                    <p className="text-sm text-muted-foreground italic">Não há confrontos diretos entre estas equipes em nossa base de dados</p>
                  </div>

                  {/* Cards dos últimos 5 jogos: Mandante à esquerda e Visitante à direita */}
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">
                    <div className="min-w-0 flex-1">
                      <TeamRecentBlock teamId={homeTeamId} form={homeForm} anomalies={homeAnomalies} label="Mandante" loading={loadingHome} error={errorHome} teamIds={teamIds} onOpenMatch={openMatch(homeTeamId)} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <TeamRecentBlock teamId={awayTeamId} form={awayForm} anomalies={awayAnomalies} label="Visitante" loading={loadingAway} error={errorAway} teamIds={teamIds} onOpenMatch={openMatch(awayTeamId)} />
                    </div>
                  </div>
                </motion.div>
              );
            }

            return (
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">
                {/* ESQUERDA: Resumo do Confronto Direto */}
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
                    <H2HCard h2hData={h2hData} home={homeTeamId} away={awayTeamId} teamIds={teamIds} />
                  )}
                </div>
                {/* DIREITA: mandante e visitante empilhados */}
                <div className="flex flex-col gap-4 h-full">
                  <div className="flex-1">
                    <TeamRecentBlock teamId={homeTeamId} form={homeForm} anomalies={homeAnomalies} label="Mandante" loading={loadingHome} error={errorHome} teamIds={teamIds} onOpenMatch={openMatch(homeTeamId)} />
                  </div>
                  <div className="flex-1">
                    <TeamRecentBlock teamId={awayTeamId} form={awayForm} anomalies={awayAnomalies} label="Visitante" loading={loadingAway} error={errorAway} teamIds={teamIds} onOpenMatch={openMatch(awayTeamId)} />
                  </div>
                </div>
              </motion.div>
            );
          }
          // Só uma equipe selecionada — card único centralizado
          const s = homeTeamId
            ? { teamId: homeTeamId, form: homeForm, anomalies: homeAnomalies, label: 'Mandante', loading: loadingHome, error: errorHome }
            : { teamId: awayTeamId, form: awayForm, anomalies: awayAnomalies, label: 'Visitante', loading: loadingAway, error: errorAway };
          return (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="max-w-md mx-auto">
              <TeamRecentBlock teamId={s.teamId} form={s.form} anomalies={s.anomalies} label={s.label} loading={s.loading} error={s.error} teamIds={teamIds} onOpenMatch={openMatch(s.teamId)} />
            </motion.div>
          );
        })()}
      </AnimatePresence>

      <div className="flex flex-col items-center gap-2">
        {errMsg && (
          <div className="text-sm rounded-md bg-red-500/10 text-red-600 p-3 max-w-md text-center">
            {errMsg}{errMsg.toLowerCase().includes('insuficiente') && <> <Link href="/carteira" className="underline font-medium">Comprar créditos</Link>.</>}
          </div>
        )}
        
        {/* Badge Flutuante de Análise Aprofundada (Exibido ANTES de gerar a análise quando a partida possuir análise aprofundada cadastrada) */}
        {(() => {
          if (loading || analysis || !deepAnalysisInfo?.hasDeep || !deepAnalysisInfo?.analystName) return null;
          return (
            <motion.div
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="relative group my-2.5"
            >
              {/* Badge Principal */}
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-slate-900/90 border border-indigo-500/40 text-indigo-100 shadow-[0_0_15px_rgba(99,102,241,0.2)] hover:shadow-[0_0_22px_rgba(99,102,241,0.35)] hover:border-indigo-400/80 transition-all cursor-help select-none">
                <div className="relative w-5 h-5 flex items-center justify-center shrink-0">
                  <FileText className="w-5 h-5 text-indigo-400" />
                  <motion.div
                    animate={{
                      x: [-1, 3, -1],
                      y: [1, -2, 1],
                      rotate: [-5, 12, -5],
                    }}
                    transition={{
                      duration: 1.8,
                      repeat: Infinity,
                      ease: "easeInOut",
                    }}
                    className="absolute -top-1 -right-1 text-cyan-300 drop-shadow-[0_0_6px_rgba(34,211,238,0.8)]"
                  >
                    <PenTool className="w-3.5 h-3.5" />
                  </motion.div>
                </div>
                <span className="text-xs font-bold tracking-wide uppercase text-indigo-200">
                  Contém Análise Detalhada
                </span>
                <Sparkles className="w-3.5 h-3.5 text-amber-400 animate-pulse ml-0.5 shrink-0" />
              </div>

              {/* Balão de Informação ao Hover */}
              <div className="absolute bottom-full mb-3 left-1/2 -translate-x-1/2 w-72 p-3.5 bg-slate-900 border border-indigo-500/50 rounded-xl shadow-2xl shadow-indigo-950/90 text-xs text-indigo-100 z-50 pointer-events-none opacity-0 group-hover:opacity-100 transition-all duration-200 scale-95 group-hover:scale-100 origin-bottom text-left leading-relaxed">
                <p>
                  Esta partida contém uma análise aprofundada, feita por{" "}
                  <strong className="text-indigo-300 font-semibold">{deepAnalysisInfo.analystName}</strong>. Gere uma análise para conferi-la!
                </p>
                <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-indigo-500/50" />
              </div>
            </motion.div>
          );
        })()}

        <motion.button
          whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
          onClick={handleGenerate}
          // Não bloqueia por saldo: o backend decide a prioridade real de consumo
          // (crédito diário grátis → conta demo → promo_balance → available_balance —
          // ver analysis/service.py::create_analysis) e o front não tem como prever se o
          // grátis diário já foi usado hoje. Se realmente não houver crédito, o erro 402
          // aparece abaixo com o link "Comprar créditos" (não trava o clique à toa).
          disabled={!canGenerate || loading}
          className="px-8 py-3 rounded-xl font-semibold text-sm transition-all disabled:opacity-40 disabled:cursor-not-allowed bg-gradient-to-r from-emerald-500 to-cyan-500 text-white shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/30 cursor-pointer"
        >
          {loading
            ? <span className="flex items-center gap-2"><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Processando...</span>
            : (
              <span className="flex items-center gap-2">
                <Sparkles className="w-4 h-4" />
                {user
                  ? (
                    <span className="flex items-center gap-1.5">
                      Gerar análise{" "}
                      {competition === 'Copa do Mundo' || user.is_demo
                        ? (
                          <span className="relative inline-block">
                            (1 crédito)
                            <span className="pointer-events-none absolute -left-[6%] -right-[6%] top-1/2 h-[2.5px] bg-amber-400 -translate-y-1/2 -rotate-[8deg] rounded-full" />
                          </span>
                        )
                        : '(1 crédito)'}
                    </span>
                  )
                  : 'Entrar para gerar análise'}
              </span>
            )}
        </motion.button>
        {user && (
          <p className="text-xs text-muted-foreground flex items-center gap-1">
            <Coins className="w-3.5 h-3.5 text-emerald-500" />
            {user.is_demo
              ? 'Conta demo — análises sempre grátis'
              : <>{credits} créditos · <Link href="/carteira" className="underline font-medium text-primary">Ir para a Carteira ➜</Link></>}
          </p>
        )}
      </div>

      <AnimatePresence>
        {projection && !loading && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-6">
          <ScreenshotGuard page="analise-resultado">
          <div className="space-y-6">

            <AnalysisResultsView prediction={projection} home={homeTeamId} away={awayTeamId} teamIds={teamIds} scorers={scorers} fixtureId={resolvedFixtureIdForOdds} scope={scope} />

            {/* OPORTUNIDADES ENCONTRADAS — odds com EV positivo (Verificador de Bets) */}
            <OpportunitiesSection prediction={projection} home={homeTeamId} away={awayTeamId} fixtureId={resolvedFixtureIdForOdds} scope={scope} />

            {/* MONTE SUA SELEÇÃO — oferta "ParcerIA" (Só Paga se Acertar) */}
            <SectionDivider>MONTE SUA SELEÇÃO</SectionDivider>
            {analysis?.type === 'future_match' && !analysis?.is_free ? (
              <div className="max-w-3xl mx-auto mb-2">
                <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4 mb-4 text-sm text-muted-foreground leading-relaxed text-justify">
                  <p className="mb-2">
                    <b className="text-foreground">Oferta ParcerIA</b><br />
                    Você utilizou um crédito de análise para uma partida agendada (<b className="text-foreground">{teamPt(homeTeamId)} x {teamPt(awayTeamId)}</b> - {fmtMatchDateTime(matchDate)}).
                  </p>
                  <p className="mb-2">
                    Mas calma, seu crédito ainda não foi gasto, ele só está retido, e você ainda pode recuperá-lo para fazer outra análise.
                  </p>
                  <p className="mb-2">
                    Como? Monte sua seleção escolhendo os palpites desta análise, com odd combinada até 2,00. O sistema irá acompanhar a partida para verificar se ela foi validada.
                  </p>
                  <p className="mb-2">
                    Se não quiser ter o trabalho de escolher os palpites, não tem problema! Gere a seleção automaticamente e o sistema irá sugerir uma combinação dentro do limite de odd para você.
                  </p>
                  <p className="mb-2">
                    <b className="text-foreground">Se sua seleção for validada</b> - O crédito é consumido (pô, a gente ajudou né! 😅)
                  </p>
                  <p className="mb-2">
                    <b className="text-foreground">Se sua seleção não foi validada</b> - Não fique triste, seu crédito é estornado e você poderá fazer uma nova análise para outro confronto. Torcemos para que dê mais sorte! 🍀🤞
                  </p>
                  <Link href="/como-funciona#promocao" className="text-primary font-medium inline-flex items-center gap-1">
                    Ver a explicação completa da oferta ParcerIA →
                  </Link>
                </div>
                <BetBuilder analysisId={analysis.id} home={homeTeamId} away={awayTeamId} isFree={analysis.is_free} onConfirmed={() => refreshWallet()} />
              </div>
            ) : (
              <p className="text-sm text-muted-foreground text-center max-w-2xl mx-auto">
                A oferta <b>&quot;ParcerIA&quot;</b> vale apenas para <b>análises de partidas agendadas</b>. Esta é
                uma <b>análise independente</b>, então não é elegível.{' '}
                <Link href="/como-funciona#promocao" className="text-primary font-medium">Saiba mais</Link>.
              </p>
            )}

          </div>
          </ScreenshotGuard>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
