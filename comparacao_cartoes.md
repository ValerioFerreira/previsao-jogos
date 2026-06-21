# Comparacao de Modelos de Contagem para CARTOES (Passo 2b)

- Corte temporal: 2024-10-12 | treino 3286 | teste 816
- Grade M=15

## Parametros estimados (MLE no treino)
- Independente: r_H=1000.0000, r_A=1000.0000
- Acoplada: r_H=471.1530, r_A=563.1815, **beta=0.0721** (correlacao POSITIVA), forma exponencial

## Vies global (media prevista vs real)
| Mercado | Real | Atual | A (indep) | B (acopl) |
|---|---|---|---|---|
| Mandante | 1.787 | 1.711 | 1.782 | 1.782 |
| Visitante | 2.096 | 1.847 | 2.067 | 2.067 |
| Total | 3.882 | 3.601 | 3.849 | 3.849 |

## Mandante (linha Over 1.5)
| Abordagem | LogLoss | Brier | ECE | Cob80% | Largura | MAE | RMSE |
|---|---|---|---|---|---|---|---|
| Atual (Quantilica) | 1.67052 | 0.24462 | 7.32% | 85.78% | 2.98 | 0.978 | 1.312 |
| A (Independente) | 1.58375 | 0.23023 | 1.63% | 92.40% | 3.38 | 0.996 | 1.266 |
| B (Acoplada) | 1.58494 | 0.23025 | 1.57% | 92.65% | 3.43 | 0.996 | 1.266 |

## Visitante (linha Over 1.5)
| Abordagem | LogLoss | Brier | ECE | Cob80% | Largura | MAE | RMSE |
|---|---|---|---|---|---|---|---|
| Atual (Quantilica) | 1.81468 | 0.25038 | 8.91% | 84.56% | 3.02 | 1.112 | 1.489 |
| A (Independente) | 1.69291 | 0.22942 | 3.37% | 91.54% | 3.66 | 1.109 | 1.416 |
| B (Acoplada) | 1.69349 | 0.22943 | 3.08% | 92.16% | 3.72 | 1.109 | 1.416 |

## Total (linha Over 3.5)
| Abordagem | LogLoss | Brier | ECE | Cob80% | Largura | MAE | RMSE |
|---|---|---|---|---|---|---|---|
| Atual (Quantilica) | 2.11958 | 0.25029 | 7.80% | 89.09% | 5.09 | 1.664 | 2.099 |
| A (Independente) | 2.06998 | 0.24239 | 5.81% | 87.99% | 4.92 | 1.639 | 2.035 |
| B (Acoplada) | 2.07111 | 0.24172 | 4.64% | 91.05% | 5.34 | 1.639 | 2.035 |

## Recomendacao por mercado (LogLoss; ECE como desempate)
- **Mandante:** A (indep) (LL atual=1.67052 · A=1.58375 · B=1.58494)
- **Visitante:** A (indep) (LL atual=1.81468 · A=1.69291 · B=1.69349)
- **Total:** A (indep) (LL atual=2.11958 · A=2.06998 · B=2.07111)