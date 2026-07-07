# EXP 11 — Cobrador de pênalti no modelo de goleador — 2026-07-07

## Hipótese
O cobrador designado marca mais (pênaltis convertem ~75%). Adicionar `pk_rate` = taxa
histórica de cobrança do jogador (point-in-time, dos eventos do cache) melhora o scorer?

## Resultado (64k player-games; 1.894 cobranças, 1.001 cobradores)
| fold | AUC base | AUC +pk | LL base | LL +pk |
|---|---|---|---|---|
| 0.50 | 0.7425 | 0.7454 | 0.2596 | 0.2589 |
| 0.62 | 0.7523 | 0.7541 | 0.2531 | 0.2521 |
| 0.73 | 0.7554 | 0.7551 | 0.2714 | 0.2714 |
| 0.85 | 0.7548 | 0.7549 | 0.2444 | 0.2443 |

**dAUC +0.0011 | dLL −0.0004 (3/4 folds).**

## Veredito: MARGINAL — opcional
Positivo e quase consistente, mas pequeno: a `base_scored` já embute que cobradores marcam
mais. Ganho ~3× o do goleiro adversário (EXP9), ainda assim modesto. Pode ser incluído (barato,
não piora), mas não é um salto. Script: `scripts/exp11_penalty_taker.py`.
