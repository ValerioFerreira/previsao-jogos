# Relatório de Comparação - Modelo de Cartões
- Corte temporal: 2024-10-12 | Treino: 3286 | Teste: 816
- baseline: CardsNB (NB independente, ~Poisson)
- Novo: CardsGP (Poisson Generalizada + Cascade + Ortho)

## Parâmetros Estimados por MLE no Treino
- **CardsNB**: r_H = 1000.0000, r_A = 1000.0000
- **CardsGP**: gp_lambda_H = -0.1208, gp_lambda_A = -0.1283 (underdispersão confirmada!)

## Viés Global no Teste temporal (Média Prevista vs Real)
| Mercado | Real | CardsNB | CardsGP |
|---|---|---|---|
| Mandante | 1.787 | 1.777 | 1.776 |
| Visitante | 2.096 | 2.067 | 2.066 |
| Total | 3.882 | 3.844 | 3.842 |

## Métricas de Performance Global (Log-Loss e Cobertura)
| Mercado | Modelo | LogLoss | Cob 80% | Largura | MAE | RMSE |
|---|---|---|---|---|---|---|
| Mandante | CardsNB | 1.58451 | 92.77% | 3.38 | 0.994 | 1.268 |
| Mandante | CardsGP | 1.58941 | 89.22% | 2.98 | 0.996 | 1.269 |
| Visitante | CardsNB | 1.69448 | 91.42% | 3.68 | 1.112 | 1.419 |
| Visitante | CardsGP | 1.70556 | 87.75% | 3.15 | 1.113 | 1.417 |
| Total | CardsNB | 2.07395 | 88.11% | 4.92 | 1.650 | 2.043 |
| Total | CardsGP | 2.09870 | 83.82% | 4.43 | 1.647 | 2.043 |

## Calibração em Linhas Alternativas (Brier e ECE/Tail ECE)
### Mandante
| Linha | Modelo | Brier | ECE | Tail ECE |
|---|---|---|---|---|
| Over 1.5 | CardsNB | 0.22979 | 1.22% | 3.26% |
| Over 1.5 | CardsGP | 0.23067 | 2.98% | 2.63% |
| Over 2.5 | CardsNB | 0.18348 | 1.67% | 2.24% |
| Over 2.5 | CardsGP | 0.18345 | 1.97% | 2.94% |

### Visitante
| Linha | Modelo | Brier | ECE | Tail ECE |
|---|---|---|---|---|
| Over 1.5 | CardsNB | 0.23084 | 3.88% | 33.05% |
| Over 1.5 | CardsGP | 0.23060 | 3.74% | 7.26% |
| Over 2.5 | CardsNB | 0.20980 | 3.51% | 3.67% |
| Over 2.5 | CardsGP | 0.21037 | 1.64% | 1.70% |

### Total
| Linha | Modelo | Brier | ECE | Tail ECE |
|---|---|---|---|---|
| Over 3.5 | CardsNB | 0.24352 | 5.44% | 18.07% |
| Over 3.5 | CardsGP | 0.24473 | 5.70% | 27.36% |
| Over 4.5 | CardsNB | 0.21270 | 1.75% | 2.70% |
| Over 4.5 | CardsGP | 0.21161 | 1.89% | 0.97% |
| Over 5.5 | CardsNB | 0.15442 | 1.67% | 1.12% |
| Over 5.5 | CardsGP | 0.15590 | 3.11% | 2.43% |
