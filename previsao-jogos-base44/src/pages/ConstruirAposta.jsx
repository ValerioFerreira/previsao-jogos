import React, { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Checkbox } from '@/components/ui/checkbox';
import { Wrench, Search, TrendingUp, Layers, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import {
  TEAMS, COMPETITIONS, generateProjection,
  getOddFromProb, getProbFromOdd, calculateOverProb, calculateUnderProb,
} from '@/lib/mock-data';
import InfoTooltip from '@/components/platform/InfoTooltip';

const MARKET_OPTIONS = [
  { value: 'gols', label: 'Gols Totais' },
  { value: 'finalizacoes', label: 'Finalizações Totais' },
  { value: 'escanteios', label: 'Escanteios Totais' },
  { value: 'cartoes', label: 'Cartões Totais' },
];

export default function ConstruirAposta() {
  const [homeTeamId, setHomeTeamId] = useState('');
  const [awayTeamId, setAwayTeamId] = useState('');

  const homeTeam = TEAMS.find(t => t.id.toString() === homeTeamId);
  const awayTeam = TEAMS.find(t => t.id.toString() === awayTeamId);
  const bothSelected = homeTeam && awayTeam && homeTeamId !== awayTeamId;

  const projection = useMemo(() => {
    if (!bothSelected) return null;
    return generateProjection(homeTeam, awayTeam);
  }, [homeTeamId, awayTeamId]);

  return (
    <div className="space-y-6">
      {/* Team Selection */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-card border border-border/50 rounded-xl p-5"
      >
        <h2 className="text-lg font-heading font-bold mb-4 flex items-center gap-2">
          <Wrench className="w-5 h-5 text-purple-500" />
          Laboratório de Apostas
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-lg">
          <div>
            <Label className="text-xs text-muted-foreground mb-1.5 block">Mandante</Label>
            <Select value={homeTeamId} onValueChange={setHomeTeamId}>
              <SelectTrigger className="h-10"><SelectValue placeholder="Selecione..." /></SelectTrigger>
              <SelectContent>
                {TEAMS.filter(t => t.id.toString() !== awayTeamId).map(t => (
                  <SelectItem key={t.id} value={t.id.toString()}>{t.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs text-muted-foreground mb-1.5 block">Visitante</Label>
            <Select value={awayTeamId} onValueChange={setAwayTeamId}>
              <SelectTrigger className="h-10"><SelectValue placeholder="Selecione..." /></SelectTrigger>
              <SelectContent>
                {TEAMS.filter(t => t.id.toString() !== homeTeamId).map(t => (
                  <SelectItem key={t.id} value={t.id.toString()}>{t.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </motion.div>

      {!bothSelected && (
        <div className="text-center py-16 text-muted-foreground text-sm">
          Selecione duas equipes para acessar as ferramentas de construção de aposta.
        </div>
      )}

      {bothSelected && projection && (
        <div className="space-y-6">
          {/* Line Explorer */}
          <LineExplorer projection={projection} />

          {/* Value Betting */}
          <ValueBetting projection={projection} />

          {/* Parlay Builder */}
          <ParlayBuilder projection={projection} homeTeam={homeTeam} awayTeam={awayTeam} />
        </div>
      )}
    </div>
  );
}

function LineExplorer({ projection }) {
  const [market, setMarket] = useState('gols');
  const [side, setSide] = useState('over');
  const [line, setLine] = useState(2.5);

  const marketData = projection.markets[market];
  const prob = side === 'over'
    ? calculateOverProb(marketData.distribution, line)
    : calculateUnderProb(marketData.distribution, line);
  const fairOdd = getOddFromProb(prob);

  const minLine = 0.5;
  const maxLine = market === 'gols' ? 8.5 : market === 'finalizacoes' ? 35.5 : market === 'escanteios' ? 18.5 : 12.5;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
      className="bg-card border border-border/50 rounded-xl p-5"
    >
      <h3 className="text-sm font-semibold mb-4 flex items-center gap-1.5">
        <Search className="w-4 h-4 text-cyan-500" />
        Explorador de Linha
        <InfoTooltip text="Escolha o mercado, o lado (Over/Under) e escaneie a grade completa de odds justas calculadas pela CDF da distribuição de probabilidade." />
      </h3>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-5">
        <div>
          <Label className="text-xs text-muted-foreground mb-1.5 block">Mercado</Label>
          <Select value={market} onValueChange={v => { setMarket(v); setLine(v === 'gols' ? 2.5 : v === 'finalizacoes' ? 20.5 : v === 'escanteios' ? 9.5 : 3.5); }}>
            <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
            <SelectContent>
              {MARKET_OPTIONS.map(m => (
                <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs text-muted-foreground mb-1.5 block">Lado</Label>
          <div className="flex gap-1">
            <button
              onClick={() => setSide('over')}
              className={`flex-1 py-2 text-xs font-medium rounded-md transition-colors ${side === 'over' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-muted text-muted-foreground'}`}
            >
              Over
            </button>
            <button
              onClick={() => setSide('under')}
              className={`flex-1 py-2 text-xs font-medium rounded-md transition-colors ${side === 'under' ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' : 'bg-muted text-muted-foreground'}`}
            >
              Under
            </button>
          </div>
        </div>
        <div>
          <Label className="text-xs text-muted-foreground mb-1.5 block">Média Projetada</Label>
          <div className="h-9 flex items-center text-2xl font-bold font-mono text-foreground">
            {marketData.mean}
          </div>
        </div>
      </div>

      <div className="mb-4">
        <Label className="text-xs text-muted-foreground mb-2 block">Linha: {side === 'over' ? 'Over' : 'Under'} {line}</Label>
        <Slider
          value={[line]}
          onValueChange={([v]) => setLine(v)}
          min={minLine}
          max={maxLine}
          step={0.5}
          className="w-full"
        />
      </div>

      <div className="grid grid-cols-3 gap-4 bg-muted/50 rounded-lg p-4">
        <div className="text-center">
          <p className="text-[10px] text-muted-foreground mb-1">Linha</p>
          <p className="text-lg font-bold font-mono text-foreground">{side === 'over' ? 'O' : 'U'} {line}</p>
        </div>
        <div className="text-center">
          <p className="text-[10px] text-muted-foreground mb-1">Probabilidade</p>
          <p className="text-lg font-bold font-mono text-cyan-400">{(prob * 100).toFixed(1)}%</p>
        </div>
        <div className="text-center">
          <p className="text-[10px] text-muted-foreground mb-1">Odd Justa</p>
          <p className="text-lg font-bold font-mono text-emerald-400">{fairOdd > 50 ? '50+' : fairOdd}</p>
        </div>
      </div>
    </motion.div>
  );
}

function ValueBetting({ projection }) {
  const [market, setMarket] = useState('gols');
  const [side, setSide] = useState('over');
  const [line, setLine] = useState(2.5);
  const [offeredOdd, setOfferedOdd] = useState('');
  const [oppositeOdd, setOppositeOdd] = useState('');

  const marketData = projection.markets[market];
  const modelProb = side === 'over'
    ? calculateOverProb(marketData.distribution, line)
    : calculateUnderProb(marketData.distribution, line);
  const fairOdd = getOddFromProb(modelProb);

  // De-Vig calculation
  let deVigProb = null;
  if (offeredOdd && oppositeOdd) {
    const o1 = parseFloat(offeredOdd);
    const o2 = parseFloat(oppositeOdd);
    if (o1 > 1 && o2 > 1) {
      const p1 = 1 / o1;
      const p2 = 1 / o2;
      const total = p1 + p2;
      deVigProb = parseFloat((p1 / total).toFixed(4));
    }
  }

  const offered = parseFloat(offeredOdd);
  let ev = null;
  let roiPercent = null;
  if (offered > 1) {
    const impliedProb = deVigProb !== null ? deVigProb : (1 / offered);
    ev = modelProb * (offered - 1) - (1 - modelProb);
    roiPercent = ((modelProb - (1 / offered)) / (1 / offered) * 100);
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className="bg-card border border-border/50 rounded-xl p-5"
    >
      <h3 className="text-sm font-semibold mb-4 flex items-center gap-1.5">
        <TrendingUp className="w-4 h-4 text-emerald-500" />
        Value Betting — Identificação de Assimetrias
        <InfoTooltip text="Compare a probabilidade calculada pelo modelo com a odd oferecida pela casa de apostas. Se o EV (Valor Esperado) for positivo, existe uma assimetria a favor do apostador. O De-Vig remove a margem de lucro da banca para uma comparação mais justa." />
      </h3>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
        <div>
          <Label className="text-xs text-muted-foreground mb-1.5 block">Mercado</Label>
          <Select value={market} onValueChange={v => { setMarket(v); setLine(v === 'gols' ? 2.5 : v === 'finalizacoes' ? 20.5 : v === 'escanteios' ? 9.5 : 3.5); }}>
            <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
            <SelectContent>
              {MARKET_OPTIONS.map(m => (
                <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs text-muted-foreground mb-1.5 block">Lado & Linha</Label>
          <div className="flex gap-1">
            <button
              onClick={() => setSide(s => s === 'over' ? 'under' : 'over')}
              className="px-3 py-2 text-xs font-medium rounded-md bg-muted text-foreground shrink-0"
            >
              {side === 'over' ? 'Over' : 'Under'}
            </button>
            <Input
              type="number" step="0.5" value={line}
              onChange={e => setLine(parseFloat(e.target.value) || 0)}
              className="h-9 text-sm font-mono"
            />
          </div>
        </div>
        <div>
          <Label className="text-xs text-muted-foreground mb-1.5 block">Odd Oferecida</Label>
          <Input
            type="number" step="0.01" min="1.01" placeholder="Ex: 1.85"
            value={offeredOdd} onChange={e => setOfferedOdd(e.target.value)}
            className="h-9 text-sm font-mono"
          />
        </div>
        <div>
          <Label className="text-xs text-muted-foreground mb-1.5 block flex items-center gap-1">
            Odd Oposta (De-Vig)
            <InfoTooltip text="Insira a odd do lado oposto (ex: se apostou Over, insira a odd do Under) para calcular o De-Vig — a remoção da margem de lucro embutida pela casa de apostas." />
          </Label>
          <Input
            type="number" step="0.01" min="1.01" placeholder="Opcional"
            value={oppositeOdd} onChange={e => setOppositeOdd(e.target.value)}
            className="h-9 text-sm font-mono"
          />
        </div>
      </div>

      {/* Model Info */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4 bg-muted/50 rounded-lg p-3">
        <div className="text-center">
          <p className="text-[10px] text-muted-foreground">Prob. Modelo</p>
          <p className="text-sm font-bold font-mono text-foreground">{(modelProb * 100).toFixed(1)}%</p>
        </div>
        <div className="text-center">
          <p className="text-[10px] text-muted-foreground">Odd Justa</p>
          <p className="text-sm font-bold font-mono text-foreground">{fairOdd > 50 ? '50+' : fairOdd}</p>
        </div>
        {deVigProb !== null && (
          <div className="text-center">
            <p className="text-[10px] text-muted-foreground">Prob. De-Vig</p>
            <p className="text-sm font-bold font-mono text-amber-400">{(deVigProb * 100).toFixed(1)}%</p>
          </div>
        )}
        {offered > 1 && (
          <div className="text-center">
            <p className="text-[10px] text-muted-foreground">Prob. Implícita (Casa)</p>
            <p className="text-sm font-bold font-mono text-muted-foreground">{((1 / offered) * 100).toFixed(1)}%</p>
          </div>
        )}
      </div>

      {/* EV Result */}
      <AnimatePresence>
        {ev !== null && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className={`rounded-lg p-4 border ${ev > 0 ? 'bg-emerald-500/10 border-emerald-500/30' : 'bg-red-500/10 border-red-500/30'}`}
          >
            <div className="flex items-center gap-2">
              {ev > 0 ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
              ) : (
                <XCircle className="w-5 h-5 text-red-400 shrink-0" />
              )}
              <div>
                <p className={`text-sm font-bold ${ev > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {ev > 0 ? '🟢 Valor Encontrado (EV+)' : '🔴 Sem Valor Proporcional'}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  EV: <span className="font-mono font-semibold">{ev > 0 ? '+' : ''}{(ev * 100).toFixed(2)}%</span>
                  {roiPercent !== null && (
                    <span> · ROI Potencial: <span className="font-mono font-semibold">{roiPercent > 0 ? '+' : ''}{roiPercent.toFixed(1)}%</span></span>
                  )}
                </p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function ParlayBuilder({ projection, homeTeam, awayTeam }) {
  const [selections, setSelections] = useState([]);

  const parlayOptions = useMemo(() => {
    const options = [];
    // Result lines
    options.push({ id: 'home_win', label: `Vitória ${homeTeam.name}`, prob: 0.45 });
    options.push({ id: 'draw', label: 'Empate', prob: 0.25 });
    options.push({ id: 'away_win', label: `Vitória ${awayTeam.name}`, prob: 0.30 });

    // Market lines
    Object.entries(projection.markets).forEach(([key, market]) => {
      const line = key === 'gols' ? 2.5 : key === 'finalizacoes' ? 20.5 : key === 'escanteios' ? 8.5 : 3.5;
      const overProb = calculateOverProb(market.distribution, line);
      const underProb = calculateUnderProb(market.distribution, line);
      options.push({ id: `${key}_over`, label: `Over ${line} ${market.label}`, prob: overProb });
      options.push({ id: `${key}_under`, label: `Under ${line} ${market.label}`, prob: underProb });
    });

    return options;
  }, [projection, homeTeam, awayTeam]);

  const toggleSelection = (id) => {
    setSelections(prev => prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]);
  };

  const selectedOptions = parlayOptions.filter(o => selections.includes(o.id));
  const combinedProb = selectedOptions.reduce((acc, o) => acc * o.prob, 1);
  const combinedOdd = combinedProb > 0 ? getOddFromProb(combinedProb) : 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.3 }}
      className="bg-card border border-border/50 rounded-xl p-5"
    >
      <h3 className="text-sm font-semibold mb-4 flex items-center gap-1.5">
        <Layers className="w-4 h-4 text-amber-500" />
        Calculadora de Combinadas (Same Game Parlay)
        <InfoTooltip text="Selecione múltiplas linhas de projeção do mesmo confronto para calcular a probabilidade combinada. Lembre-se: eventos do mesmo jogo possuem correlações que o cálculo independente não captura." />
      </h3>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 mb-5">
        {parlayOptions.map(option => (
          <button
            key={option.id}
            onClick={() => toggleSelection(option.id)}
            className={`flex items-center gap-2 p-3 rounded-lg border text-left text-xs transition-all ${
              selections.includes(option.id)
                ? 'bg-purple-500/10 border-purple-500/30 text-foreground'
                : 'bg-muted/30 border-border/30 text-muted-foreground hover:border-border'
            }`}
          >
            <Checkbox
              checked={selections.includes(option.id)}
              onCheckedChange={() => toggleSelection(option.id)}
              className="pointer-events-none"
            />
            <div className="min-w-0">
              <p className="font-medium truncate">{option.label}</p>
              <p className="text-[10px] opacity-60 font-mono">{(option.prob * 100).toFixed(1)}%</p>
            </div>
          </button>
        ))}
      </div>

      {/* Combined Result */}
      <AnimatePresence>
        {selections.length >= 2 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-3"
          >
            <div className="grid grid-cols-3 gap-4 bg-muted/50 rounded-lg p-4">
              <div className="text-center">
                <p className="text-[10px] text-muted-foreground mb-1">Seleções</p>
                <p className="text-lg font-bold font-mono text-foreground">{selections.length}</p>
              </div>
              <div className="text-center">
                <p className="text-[10px] text-muted-foreground mb-1 flex items-center justify-center gap-1">
                  Teto Otimista
                  <InfoTooltip text="Este é o produto simples das probabilidades individuais, assumindo independência total entre os eventos. A probabilidade real tende a ser inferior a este valor." />
                </p>
                <p className="text-lg font-bold font-mono text-amber-400">{(combinedProb * 100).toFixed(2)}%</p>
              </div>
              <div className="text-center">
                <p className="text-[10px] text-muted-foreground mb-1">Odd Combinada</p>
                <p className="text-lg font-bold font-mono text-cyan-400">{combinedOdd > 999 ? '999+' : combinedOdd}</p>
              </div>
            </div>

            {/* Warning Banner */}
            <div className="rounded-lg p-3 bg-amber-500/5 border border-amber-500/20 flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <p className="text-xs text-amber-300/80 leading-relaxed">
                <strong>Atenção:</strong> Eventos de uma mesma partida possuem correlações inerentes. A probabilidade real tende a ser menor que o teto estatístico calculado de forma independente.
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}