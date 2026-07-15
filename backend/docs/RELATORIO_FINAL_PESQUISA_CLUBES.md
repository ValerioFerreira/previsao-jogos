# Relatório Final — Pesquisa de Modelos para Clubes

> Gerado automaticamente por `scripts/clubs_consolidate.py`. Consolida os resultados numéricos de todas as fases executadas na branch `clubs`. Decisões de promoção (exceção de push) ficam para revisão humana.

## Fase 1 — Bateria de resultado (ranking)

| modelo         |   logloss |      rps |    brier |       ece |   accuracy |
|:---------------|----------:|---------:|---------:|----------:|-----------:|
| A_dc_nb        |  0.99349  | 0.202871 | 0.592798 | 0.0144923 |   0.52268  |
| B1_cat_pi      |  0.99854  | 0.204172 | 0.595968 | 0.0175231 |   0.514827 |
| B3_ordlogit_pi |  0.999788 | 0.204803 | 0.597091 | 0.0163678 |   0.515613 |
| B2_cat_berrar  |  1.0072   | 0.205999 | 0.60109  | 0.0230053 |   0.508533 |
| B1_lgbm_pi     |  1.01345  | 0.207173 | 0.604231 | 0.0269558 |   0.509693 |
| B7_bivpois     |  1.04075  | 0.214462 | 0.617757 | 0.0296578 |   0.495147 |
| B4_dc_classic  |  1.04133  | 0.214392 | 0.617612 | 0.0284076 |   0.495387 |
| B4_dc_dynamic  |  1.05988  | 0.218449 | 0.626498 | 0.0402126 |   0.489693 |

## Fase 2 — Contagem, calibração, tuning DC
### Cascata de contagem (mercados)
- **cards**: log-loss=2.2249 MAE=1.824 cobertura80=0.839
- **corners**: log-loss=2.6328 MAE=2.698 cobertura80=0.882
- **shots**: log-loss=3.1902 MAE=4.615 cobertura80=0.866
- **shots_on_target**: log-loss=2.5502 MAE=2.494 cobertura80=0.855

### Tuning DC-NB — top 5 configs

|                |   logloss |      rps |
|:---------------|----------:|---------:|
| (100, 3, 0.05) |  0.993758 | 0.20296  |
| (200, 3, 0.03) |  0.993778 | 0.202962 |
| (100, 4, 0.05) |  0.993924 | 0.203012 |
| (100, 4, 0.03) |  0.994177 | 0.203052 |
| (100, 3, 0.03) |  0.99431  | 0.203077 |

Produção (100,3,0.05): log-loss médio = 0.9938

## Fase 3 — Transferência clubes -> seleções (Linha A)
| mode        |   logloss |      rps |       ece |
|:------------|----------:|---------:|----------:|
| pooled_w0.5 |  0.877209 | 0.172199 | 0.0323394 |
| baseline    |  0.877398 | 0.17225  | 0.0270515 |
| finetune    |  0.877398 | 0.17225  | 0.0270515 |
| zero_shot   |  0.896466 | 0.177237 | 0.0394993 |

- pooled_w0.5: delta log-loss vs produção = -0.0002 (MELHOR)
- finetune: delta log-loss vs produção = +0.0000 (pior)
- zero_shot: delta log-loss vs produção = +0.0191 (pior)

## Fase 4 — Hipóteses descartadas revisitadas
- **blend_btts**: 5 linhas (ver CSV)
- **calibration_result**: delta=+0.0098 | passou_todos_folds=False
- **elo_conditioned**: delta=+0.0003 | passou_todos_folds=False
- **gp_vs_nb_corners**: 5 linhas (ver CSV)
- **lgbm_lambda**: delta=+0.0029 | passou_todos_folds=False
- **momentum**: delta=+0.0001 | passou_todos_folds=False
- **referee**: delta=+0.0000 | passou_todos_folds=False
- **time_decay_H1**: delta=+0.0073 | passou_todos_folds=False
- **time_decay_H2**: delta=+0.0042 | passou_todos_folds=False
- **time_decay_H3**: delta=+0.0025 | passou_todos_folds=False
- **time_decay_H4**: delta=+0.0018 | passou_todos_folds=False
- **xg_feature**: delta=+0.0001 | passou_todos_folds=False
- **xgb_lambda**: delta=+0.0006 | passou_todos_folds=False

## Fase 5 — Features próprias de clubes (ablação)
- **altitude_travel**: delta log-loss = -0.0001
- **congestion**: delta log-loss = -0.0001
- **gap_ratings**: delta log-loss = -0.0022
- **match_importance**: delta log-loss = -0.0008
- **phase**: delta log-loss = -0.0000
- **squad_rotation**: delta log-loss = -0.0003
- **xg_overperf**: delta log-loss = +0.0001

### Combinação final dos grupos que passaram
delta = -0.0022

## Fase 6 — Bateria avançada Linha B
- **state_space**: 0/5 folds melhoram, delta=+0.0420
- **ensemble**: 0/5 folds melhoram, delta=+0.0016
- **deep_tabular**: 0/5 folds melhoram, delta=+0.0092
- **gap_counts (chutes)**: log-loss médio = 3.1891
- **sweep CatBoost**: melhor config (np.int64(4), np.int64(400), np.float64(3.0)) -> log-loss=0.9970

## Fase 8 — Backtest de valor
**Odds reais de clubes: 0 registros em `odds_registry`** (só seleções/Copa do Mundo). ROI real não pôde ser validado.

Backtest de papel (proxy, Kelly 1/4 contra frequência histórica): 28129 apostas simuladas, yield médio +5.64% — **não interpretar como ROI de mercado real**, é só diagnóstico de edge relativo.

