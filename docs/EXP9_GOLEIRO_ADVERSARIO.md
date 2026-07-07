# EXP 9 — Qualidade do goleiro adversário no modelo de goleador — 2026-07-07

## Hipótese
O modelo de goleador usa `opp_gc` (gols concedidos pelo time). A forma recente do **goleiro
adversário** (rating rolante) carregaria sinal ADICIONAL para P(atacante marca)?

## Método
Feature `opp_gk_form` = rating recente (média móvel 5, point-in-time) do goleiro do adversário
(jogador com posição "G"). Adicionada às features do scorer; CV temporal, base vs base+opp_gk.
Script: `scripts/exp9_gk_quality.py`.

## Resultado
| fold | AUC base | AUC +gk | LL base | LL +gk |
|---|---|---|---|---|
| 0.50 | 0.7433 | 0.7429 | 0.2593 | 0.2587 |
| 0.62 | 0.7519 | 0.7524 | 0.2530 | 0.2525 |
| 0.73 | 0.7572 | 0.7580 | 0.2702 | 0.2699 |
| 0.85 | 0.7556 | 0.7560 | 0.2442 | 0.2438 |

**dAUC +0.0003 | dLL −0.0004 (4/4 folds).**

## Veredito: POSITIVO mas NEGLIGÍVEL — não adicionar
Consistente em 4/4 folds, mas o efeito é minúsculo (+0.0003 AUC). O `opp_gc` já captura a
qualidade defensiva do time; o rating específico do goleiro é praticamente redundante. Não
compensa a dependência extra de dado para um ganho desprezível.
