"use client";
import React, { useState } from 'react';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { TeamSelect } from '@/components/platform/TeamSelect';
import InfoTooltip from '@/components/platform/InfoTooltip';
import { usePrediction } from '@/lib/PredictionContext';
import { api, UpcomingFixture } from '@/lib/api';
import { teamPt } from '@/lib/teamNames';

function dBR(s: string): string {
  const d = (s || '').slice(0, 10).split('-');
  return d.length === 3 ? `${d[2]}/${d[1]}/${d[0]}` : s;
}

// Seletor de modo reutilizável (Partida Futura x Análise Independente) + árbitro.
// Escreve no contexto compartilhado (times/competição/mando), usado por todas as páginas.
export function MatchModePicker({ showReferee = true }: { showReferee?: boolean }) {
  const { setHomeTeamId, setAwayTeamId, setCompetition, setNeutralField } = usePrediction();
  const [mode, setMode] = useState<'independente' | 'futura'>('independente');
  const [referee, setReferee] = useState('');
  const [referees, setReferees] = useState<string[]>([]);
  const [upcoming, setUpcoming] = useState<UpcomingFixture[]>([]);

  React.useEffect(() => {
    api.upcomingFixtures().then(r => setUpcoming(r.fixtures)).catch(() => {});
    if (showReferee) api.referees().then(r => setReferees(r.referees)).catch(() => {});
  }, [showReferee]);

  const pick = (fid: string) => {
    const fx = upcoming.find(f => f.fixture_id === fid);
    if (!fx) return;
    setHomeTeamId(fx.home);
    setAwayTeamId(fx.away);
    setCompetition(fx.tournament);
    setNeutralField(fx.neutral);
  };

  return (
    <div className="mb-2">
      <div className="inline-flex p-1 mb-3 rounded-lg bg-muted text-xs font-medium">
        <button onClick={() => setMode('futura')}
          className={`px-3 py-1.5 rounded-md transition-colors ${mode === 'futura' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
          Selecionar Partida Futura
        </button>
        <button onClick={() => setMode('independente')}
          className={`px-3 py-1.5 rounded-md transition-colors ${mode === 'independente' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
          Análise Independente
        </button>
      </div>

      {mode === 'futura' && (
        <div className="mb-3">
          <Label className="text-xs text-muted-foreground mb-1.5 block">Partida Agendada</Label>
          {upcoming.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">Nenhuma partida futura disponível no momento.</p>
          ) : (
            <Select onValueChange={pick}>
              <SelectTrigger className="h-10 max-w-xl"><SelectValue placeholder="Escolha um jogo agendado..." /></SelectTrigger>
              <SelectContent>
                {upcoming.map(fx => (
                  <SelectItem key={fx.fixture_id} value={fx.fixture_id}>
                    {dBR(fx.date)} · {teamPt(fx.home)} x {teamPt(fx.away)} · {fx.league_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <p className="text-[11px] text-muted-foreground mt-1.5">Pré-preenche as equipes (e competição/mando) abaixo.</p>
        </div>
      )}

      {showReferee && (
        <div className="max-w-xs">
          <Label className="text-xs text-muted-foreground mb-1.5 block flex items-center gap-1">
            Árbitro (opcional)
            <InfoTooltip text="Você pode informar o árbitro. No momento não influencia os cálculos; ficará disponível para análises futuras." />
          </Label>
          <TeamSelect value={referee} onValueChange={setReferee} teams={referees} labelFn={(s) => s} placeholder="Buscar árbitro..." searchPlaceholder="Buscar árbitro..." />
        </div>
      )}
    </div>
  );
}
