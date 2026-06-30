# Relatório 5 — Calibração O/U dos mercados de contagem (MELHORA PROMOVIDA)

> Branch: **`claude-testing`**. Primeira melhora **aprovada e promovida** desde o início
> da bateria de validações: calibração isotônica das linhas Over/Under do TOTAL de
> **escanteios, finalizações a gol e cartões** (chutes EXCLUÍDO — piora).

## A janela de oportunidade
A feature-importance e todas as baterias anteriores mostraram que **features novas não
ajudam** (o elo satura). Restava a **calibração**: a produção ajusta a dispersão NB/GP de
forma global; será que a probabilidade Over de cada linha está bem calibrada **fora do
tempo**? (Calibração = quando o modelo diz "70% Over", isso acontece ~70% das vezes.)

## Método (honesto, sem leakage temporal)
`count_calibration.py` (split 50/50 antigo→recente) e `count_calibration_walkforward.py`
(CV temporal expanding, 4 folds). Em cada fold: ajusta um **isotônico** em
`(prob_Over, desfecho)` de várias linhas no passado e **avalia no bloco seguinte**.
Métricas: **ECE** (erro de calibração esperado — distância média entre a probabilidade
dita e a frequência real) e **Bernoulli log-loss** da linha O/U.

## Resultado (walk-forward, deployável)
| Mercado | ECE médio (cru→calibrado) | ΔBernoulli-LL | Folds que melhoram ECE | Veredito |
|---|---|---|---|---|
| **Escanteios** | 4.5% → **2.8%** | **−0.0072** | **4/4** | ✅ Promovido |
| **Finalizações a gol** | 3.0% → **2.5%** | −0.0029 | 3/4 (recente ✓) | ✅ Promovido |
| **Cartões** | 2.8% → **2.1%** | −0.0017 | 2/4 (recente ✓) | ✅ Promovido |
| Finalizações (chutes) | 6.3% → 7.5% | +0.0015 | 1/4 | ❌ Excluído (piora) |

Escanteios é o ganho mais forte e **consistente em todos os folds**, com o melhor resultado
justamente no fold mais recente (3.8%→2.2%) — o regime mais relevante para produção. Como
o modelo deployado foi treinado em todos os dados, o ECE cru é uma estimativa **otimista**;
o ganho real out-of-sample tende a ser **maior**, não menor.

## Por que isotônico (e não Platt/temperatura)
A miscalibração das caudas NB/GP não é uma simples rotação logística — é uma curva
monótona irregular (a NB subestima levemente certas faixas de Over). O isotônico é a
recalibração **monótona livre** que captura exatamente isso, preservando a ordenação entre
linhas (Over cai conforme a linha sobe). Platt/temperatura assumem forma paramétrica e não
capturaram o padrão (testado antes no resultado, onde pioravam).

## Promoção (o que mudou)
- **Artefato:** `model_artifacts/ou_calibrators.joblib` — `{escanteios, finalizacoes_gol,
  cartoes}` → `IsotonicRegression` (ajustado no histórico completo, pooled sobre linhas).
  Gerado por `backend/scripts/build_ou_calibrators.py`.
- **`predictor.py`:** `_corners_market(..., calibrator=None)` recalibra a prob. Over de cada
  linha quando recebe um calibrador; aplicado **só ao TOTAL** de escanteios/a-gol/cartões
  (validado) — **não** ao mandante/visitante nem aos chutes. A distribuição/estimativa
  seguem da PMF crua (fonte de verdade); só as linhas O/U são calibradas e marcadas com
  `"calibrado": true`. Ausência do artefato = comportamento antigo (retrocompatível).
- **Monotonicidade** entre linhas preservada; smoke-test do predictor OK.

## Scripts e dados
`count_calibration.py`, `count_calibration_walkforward.py`, `build_ou_calibrators.py`
(em `backend/scripts/`). CSVs: `count_calibration.csv`, `count_calibration_wf.csv`.
Também nesta fase: `forma_dc_blend.py` — fechou o último fio âmbar (forma blendada no DC
**real** não melhora o resultado: dLL −0.0006, ECE pior; o sinal do proxy HGB era artefato).
