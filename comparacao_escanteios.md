# Comparação de Modelos de Contagem para Escanteios (Passo 2)

- **Corte de Validação Temporal:** 2024-10-12
- **Tamanho do Treino:** 3286 jogos (estatísticas avançadas válidas)
- **Tamanho do Teste:** 816 jogos (estatísticas avançadas válidas)
- **Tamanho da Grade:** $M_C = 25$ (grade conjunta $26 	imes 26$)

## Parâmetros Estimados por MLE no Treino
- **Abordagem A (Independente):**
  - $r_H$ (dispersão mandante): **20.7446**
  - $r_A$ (dispersão visitante): **21.0355**
- **Abordagem B (Acoplada):**
  - $r_H$ (dispersão mandante): **29.1659**
  - $r_A$ (dispersão visitante): **24.2142**
  - $\beta$ (correlação de Dixon-Coles): **-0.0397** (correlação negativa)
  - Tipo de Correlação: **Exponencial Pura (Sem Clamp)**

## Validação de Viés Global (Média Prevista vs Média Real)

| Mercado | Média Real | Média Prevista (Atual) | Média Prevista (Abordagem A) | Média Prevista (Abordagem B) |
|---|---|---|---|---|
| Mandante | 5.1679 | 4.8463 | 5.1958 | 5.1958 |
| Visitante | 3.8395 | 3.7449 | 4.0052 | 4.0052 |
| Total | 9.0074 | 8.8228 | 9.2010 | 9.2010 |

## Resultados Comparativos por Mercado

### Mercado: Escanteios Mandante (Linha Over 4.5)

| Abordagem | Log-Loss Contagem | Brier Score Over | ECE Over | Cobertura 80% | Largura Média | MAE | RMSE |
|---|---|---|---|---|---|---|---|
| Atual (Quantílica) | 2.41004 | 0.20649 | 2.59364% | 83.46% | 6.24 | 2.126 | 2.769 |
| Abordagem A (Indep) | 2.36975 | 0.20811 | 2.72539% | 82.97% | 6.41 | 2.173 | 2.773 |
| Abordagem B (Acoplada) | 2.37102 | 0.20819 | 3.18843% | 82.97% | 6.36 | 2.173 | 2.773 |

### Mercado: Escanteios Visitante (Linha Over 3.5)

| Abordagem | Log-Loss Contagem | Brier Score Over | ECE Over | Cobertura 80% | Largura Média | MAE | RMSE |
|---|---|---|---|---|---|---|---|
| Atual (Quantílica) | 2.23762 | 0.21516 | 5.93078% | 82.72% | 5.26 | 1.894 | 2.403 |
| Abordagem A (Indep) | 2.20007 | 0.21430 | 6.31374% | 84.19% | 5.45 | 1.924 | 2.398 |
| Abordagem B (Acoplada) | 2.19878 | 0.21451 | 6.19789% | 84.68% | 5.54 | 1.924 | 2.398 |

### Mercado: Escanteios Total (Linha Over 8.5)

| Abordagem | Log-Loss Contagem | Brier Score Over | ECE Over | Cobertura 80% | Largura Média | MAE | RMSE |
|---|---|---|---|---|---|---|---|
| Atual (Quantílica) | 2.67234 | 0.25490 | 4.80115% | 81.62% | 7.95 | 2.785 | 3.441 |
| Abordagem A (Indep) | 2.63082 | 0.25072 | 2.74734% | 83.95% | 8.59 | 2.760 | 3.409 |
| Abordagem B (Acoplada) | 2.65000 | 0.25276 | 5.10549% | 80.64% | 7.78 | 2.760 | 3.409 |

## Recomendação Acionável e Próximos Passos

Com base nos resultados probabilísticos observados out-of-sample:
1. **Escanteios do Mandante:** Recomenda-se usar **Abordagem A (Independente)** (Log-Loss A=2.36975 vs B=2.37102, ECE A=2.73% vs B=3.19%).
2. **Escanteios do Visitante:** Recomenda-se usar **Abordagem B (Acoplada)** (Log-Loss A=2.20007 vs B=2.19878).
3. **Escanteios Totais:** Recomenda-se usar **Abordagem A (Independente)** (Log-Loss A=2.63082 vs B=2.65000, ECE A=2.75% vs B=5.11%).

> [!NOTE]
> A convolução simples da **Abordagem A** empatou ou superou a modelagem acoplada. Isso sugere que a correlação entre os lados não é forte o suficiente para justificar o acréscimo de complexidade no cálculo da conjunta.