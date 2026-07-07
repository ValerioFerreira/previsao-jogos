# Bateria de hipóteses — Momentum, Jogador, Escalação, ROI (2026-07-06)

> Testes executados sob **validação temporal** (passado→futuro, CV expanding), sempre
> comparando contra o baseline real. Objetivo: achar oportunidades de melhoria.
> Scripts em `scratchpad/` (exploratórios). Dados de jogador vêm do `match_detail_cache`
> (Neon), alimentado pelo prefetch da Copa (histórico ~2010+ das 48 seleções).

## Resumo executivo (vereditos)

| Hipótese | Alvo | Veredito | Números-chave |
|---|---|---|---|
| **Momentum de EQUIPE** (pts cru, resíduo-vs-Elo, tendência-Elo) | Resultado (1X2) | ❌ **REPROVADO** | dLL −0.0002 a −0.0007, inconsistente; **pior nos equilibrados (+0.0011)** |
| **Momentum de JOGADOR** (forma recente) | Marcar / rating | ✅ **PASSA (forte)** | Marcar: dLL −0.0032, **AUC 0.68→0.71 (4/4)**; rating dRMSE −0.0013 (4/4) |
| **Força da ESCALAÇÃO** (XI fielded vs Elo) | Saldo de gols | 🟡 **PROMISSOR** (limitado por dados) | dRMSE −0.0203 (3/4, +forte no recente), coef +0.71; só 581 jogos |
| **Ratings dinâmicos / tendência de Elo** | Resultado | ❌ Reprovado (é subcaso do momentum de equipe) | dLL −0.0003, 3/4 |
| **Backtest ROI/RPS** | Valor vs odds | ⏳ **Inconclusivo (dados insuf.)** | ~14 apostas liquidadas → ruído; infra OK |

**Conclusão:** o momentum **não** vive no resultado do time (o Elo satura — confirmado de
novo, agora incluindo a variante "bate o spread"). Ele vive **no jogador**: a forma recente
prevê o output do jogador além da taxa-base dele → **oportunidade real em props de goleador**.
A **escalação** também carrega sinal ortogonal ao Elo, mas depende de cobertura de dados.

---

## 1. Momentum de equipe no resultado — REPROVADO
Features point-in-time por time (janelas 5/10): pontos recentes (cru), resíduo de saldo
vs. esperado pelo Elo ("bate o spread"), e tendência do próprio Elo. Injetadas no
**Dixon-Coles NB real**, CV temporal expanding (cortes 0.5→0.85).

| Variante | dLL médio | folds↓ | dECE |
|---|---|---|---|
| pts (cru) | −0.0002 | 2/4 | −0.08% |
| gd_resid (vs Elo) | −0.0005 | 3/4 | −0.06% |
| elotrend | −0.0003 | 3/4 | +0.03% |
| TODOS | −0.0007 | 3/4 | +0.13% |
| TODOS (só equilibrados |Elo|≤100) | **+0.0011** | 1/4 | −0.15% |

Ganho ~ruído e **piora justamente nos jogos equilibrados**, onde a forma deveria pesar mais.
Consistente com o histórico (momentum/EWMA/SoS-Elo já reprovados). **Encerrado.**

## 2. Momentum de jogador — PASSA (forte)
26.995 player-games (5.776 jogadores, 2015→2026). Por jogador, point-in-time: taxa-base
encolhida + forma recente (janelas 3/5/10 de marcar/rating/finalizações). CV temporal,
logística/ridge, base vs base+forma.

- **Marcar (goals>0):** dLL **−0.0032** (4/4 folds), **AUC 0.68→0.71 (+0.028, 4/4)**.
- **Rating do jogo:** dRMSE **−0.0013** (4/4 folds).

A forma recente adiciona sinal **out-of-time e consistente** além da propensão do jogador.
É o mercado onde o momentum não compete com o Elo. **→ construir modelo de goleador.**

## 3. Força da escalação (personnel) — PROMISSOR, limitado por dados
**Re-teste com histórico completo (1.647 jogos, 2026-07-07):** dRMSE −0.0074 (3/4 folds,
−0.019 no recente), coef_xi +0.98 — o XI escalado segue prevendo o saldo de gols ALÉM do Elo,
com mais poder estatístico. Modesto e ainda limitado à cobertura de escalação (não treinável no
DC amplo); vale como ajuste para partida futura/goleador, não como feature do DC de produção.

`xi_strength` = média (ponderada por minutos) do rating-base recente dos jogadores em
campo, point-in-time. 581 jogos casados (escalação+Elo+resultado). GD ~ elo_diff vs
GD ~ elo_diff + xi_diff (CV temporal): **dRMSE −0.0203 (3/4 folds, −0.050 no mais recente),
coef_xi +0.71 (>0)**. O XI escalado prevê o resultado **além do Elo**.
Limites: só ~581 jogos com escalação hoje; para uso ao vivo exige a **escalação confirmada**
(~1h antes). Revisitar conforme o cache enche.

## 4. ROI/RPS — inconclusivo (dados insuficientes)
`value_backtest.py` roda, mas só ~14 apostas liquidadas (odds de fechamento + desfecho) →
ROI +40%/−100% é ruído (o próprio script avisa). Calibração agregada (n≈38) razoável, mas
sem força estatística. **Deixar o `CollectOdds` acumular semanas** e revisitar. É a validação
que mais falta (diz onde há valor real).

---

## Oportunidades priorizadas (próximos passos)
1. **Modelo de goleador (props)** — a oportunidade nova mais clara. Momentum de jogador +
   defesa do adversário + minutos/escalação. Mercado de alta liquidez. Base já validada (AUC 0.71).
2. **Ajuste de força por escalação** — sinal ortogonal ao Elo; amadurece com a cobertura do prefetch.
3. **ROI/RPS** — foundational; esperar acúmulo de odds.

**Fechado / não repetir:** momentum de equipe no resultado (todas as variantes), ratings
dinâmicos como feature de forma. Ver também DOCUMENTACAO_CENTRAL §8-9.

---

## IMPLEMENTADO — Modelo de goleador (prop "jogador a marcar")
A oportunidade #1 foi construída end-to-end:
- **Modelo:** `scripts/build_scorer_model.py` → `model_artifacts/scorer_model.joblib`. GBM sobre
  base_scored + forma recente (3/5/10) + defesa do adversário (opp gols concedidos rolante) +
  mando + minutos; calibrador **isotônico**; estado de serving embutido (features recentes por
  jogador + defesa por time). **Validação temporal: AUC 0.706→0.737 (+0.031, 4/4 folds),
  LogLoss 0.269→0.262, ECE 1.12%.**
- **Serving:** `app/services/scorer_service.py` + `GET /api/scorers?home=&away=` (candidatos =
  elenco recente da seleção, ordenado por minutos; refina com escalação confirmada quando houver).
- **Frontend:** `components/platform/ScorersCard.tsx` — card "Prováveis Goleadores" na Análise
  (foto/posição/prob/odd justa). Validado ao vivo: Messi 54.5%, Salah 20.3%, goleiro ~0%.
- **Manutenção:** rebuild diário anexado a `scripts/prefetch_wc.cmd` (estado por jogador
  acompanha os dados novos do prefetch).
- **Pendências:** filtrar aos titulares quando a escalação for confirmada.

### Atualização com histórico COMPLETO (2026-07-07)
O prefetch terminou de baixar o histórico inteiro (2010→2026) das 48 seleções (~5.162 jogos
em cache, ~74k player-games). Rebuild do modelo com esses dados **melhorou**: **AUC 0.713→0.752
(+0.039), LogLoss 0.266→0.257, ECE 0.75%** (7.218 jogadores no estado).

**Diagnóstico multi-prop** (o momentum generaliza?): com features "stripped" (só forma do
próprio alvo), o sinal é **mais forte para gol** e **fraco para finalizações**: finalização a
gol AUC +0.001 (4/4), 2+ finalizações +0.005 (4/4) — base+posição dominam. Ou seja, outros
props (chutes/a-gol/cartões) são construíveis com a mesma infra, mas com edge de momentum
menor → **prioridade menor que o goleador**. Cartões/assistências exigem extrair esses campos.

