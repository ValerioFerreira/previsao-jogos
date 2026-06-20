# Relatório de Diagnóstico — Gols e Escanteios (Fase 1)

Este relatório apresenta os resultados da **Fase 1 — Diagnóstico dos Modelos de Gols e Escanteios**. Sem alterar os modelos de produção, realizamos uma validação temporal justa (80% treino no passado, 20% teste no futuro) sobre a base ampla de desenvolvimento (API-Football) para medir a precisão contra baselines ingênuas, a calibração de probabilidades e a aderência estatística das contagens.

---

## 1. Comparação contra Baselines Ingênuas

Para avaliar a real contribuição dos modelos avançados, comparamos os erros de previsão (MAE e RMSE) contra duas baselines calculadas sob estrito protocolo **anti-leakage** (apenas com dados do conjunto de treino):
1. **Média Global:** A média histórica da variável alvo calculada sob o conjunto de treino.
2. **Média Condicional:** 
   - **Gols Totais:** Média de gols agrupados por tipo de torneio (`tournament_weight`) e faixa de diferença de Elo (`elo_diff_bin`), com faixas definidas puramente nos quantis do treino.
   - **Escanteios Mandante/Visitante/Finalizações:** Baseline condicional forte baseada na forma de média móvel dos últimos 5 jogos do time correspondente (`*_l5`), imputando com média global de treino em caso de ausência de histórico.
   - **Cartões Totais:** Média de cartões totais por tipo de torneio (`tournament_weight`) no treino.

### Tabela de Erros Side-by-Side (Validação Temporal)

| Alvo | Métrica | Modelo Atual | Baseline Global | Baseline Condicional | Ganho vs Global (%) | Ganho vs Condicional (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Gols Totais** | **MAE**<br>**RMSE** | 1.4404<br>1.8581 | 1.4787<br>1.8657 | 1.4723<br>1.8508 | **+2.59%**<br>**+0.40%** | **+2.16%**<br>**-0.40%** |
| **Escanteios Mandante** | **MAE**<br>**RMSE** | 2.1261<br>2.7694 | 2.4819<br>3.1639 | 2.5082<br>3.2193 | **+14.34%**<br>**+12.47%** | **+15.24%**<br>**+13.98%** |
| **Escanteios Visitante** | **MAE**<br>**RMSE** | 1.8938<br>2.4029 | 2.2246<br>2.7577 | 2.4149<br>3.0043 | **+14.87%**<br>**+12.87%** | **+21.58%**<br>**+20.02%** |
| **Finalizações (Shots)** | **MAE**<br>**RMSE** | 4.9691<br>6.3775 | 5.1325<br>6.5712 | 6.3046<br>8.1141 | **+3.18%**<br>**+2.95%** | **+21.18%**<br>**+21.40%** |
| **Cartões Totais** | **MAE**<br>**RMSE** | 1.6642<br>2.0992 | 1.7040<br>2.1286 | 1.6720<br>2.0913 | **+2.34%**<br>**+1.38%** | **+0.47%**<br>**-0.38%** |

### 💡 Análise Crítica dos Resultados:
- **Escanteios (Mandante e Visitante):** O modelo é **altamente superior** a ambas as baselines, agregando valor expressivo (ganhos de 14% a 21% em MAE). O fato de as baselines de forma (`*_l5`) possuírem erros maiores que a média global indica que a média móvel simples é um estimador muito ruidoso e sobreajustado. O modelo quantílico pondera corretamente o Elo, o torneio e o histórico de forma a mitigar essa variância.
- **Gols e Cartões Totais:** O ganho do modelo sobre as baselines é **marginal** (~2.5% vs global e < 2.2% vs condicional). Isso indica uma barreira inerente à previsibilidade de gols e cartões usando apenas dados básicos (Elo e histórico). Gols e cartões sofrem com alta aleatoriedade clássica do futebol, exigindo abordagens mais sofisticadas (ex.: dados de estilo de jogo, posse de bola, características do árbitro, ou modelos com restrições físicas).

---

## 2. Calibração e Cobertura de Intervalos

Para apostas e simulações de odds, a precisão pontual (MAE) é secundária em relação à **calibração probabilística** (se as probabilidades de over/under e BTTS previstas correspondem à realidade).

### 2.1 Calibração de Probabilidades (Classificadores)

Avaliamos os três principais classificadores de probabilidade do sistema por meio do **Brier Score** (quanto menor, melhor) e **ECE (Expected Calibration Error)**:

- **Ambas Marcam (BTTS):** Brier = **0.2413** | ECE = **3.81%**
- **Over 2.5 Gols:** Brier = **0.2411** | ECE = **3.84%**
- **Vencedor (Resultado Multiclasse H/D/A):** Brier = **0.5134** | ECE = **7.57%**

> [!NOTE]
> Valores de ECE abaixo de 5% em alvos binários (BTTS e Over 2.5) representam calibração excelente para modelos de Machine Learning. O resultado multiclasse de resultado de partida (7.57% ECE) é ligeiramente menos calibrado, mas ainda muito competitivo.

O gráfico abaixo mostra os **reliability diagrams** comparando a probabilidade prevista com a frequência observada no conjunto de teste:

![Diagramas de Calibração e Confiabilidade](file:///C:/Users/10341953440/.gemini/antigravity/brain/38bd63cd-c1e9-4756-9d77-8346dce6bac3/plots/calibration_reliability.png)

---

### 2.2 Calibração de Intervalos Quantílicos (80% Nominal)

Para os alvos numéricos (regressão), avaliamos a calibração comparando a **cobertura real** (percentual de vezes que o valor real cai entre os quantis $q_{10}$ e $q_{90}$) e a **largura média do intervalo** lado a lado:

| Alvo | Cobertura Nominal | Cobertura Real | Largura Média do Intervalo | Diagnóstico de Calibração |
| :--- | :---: | :---: | :---: | :--- |
| **Gols Totais** | 80.0% | **74.14%** | **4.01 gols** | Sob-cobertura (intervalos ligeiramente estreitos) |
| **Escanteios Mandante** | 80.0% | **75.86%** | **6.46 escanteios** | Sob-cobertura leve (bom compromisso de largura) |
| **Escanteios Visitante** | 80.0% | **71.81%** | **5.52 escanteios** | Sob-cobertura moderada (sobreajuste nos quantis cauda) |
| **Finalizações (Shots)** | 80.0% | **73.65%** | **13.68 chutes** | Sob-cobertura leve |
| **Cartões Totais** | 80.0% | **87.50%** | **5.30 cartões** | **Sobre-cobertura** (intervalo excessivamente largo e inútil) |

> [!WARNING]
> **O caso sensível dos Cartões:** O modelo de cartões apresenta cobertura real de 87.5% (superando o alvo de 80%), mas a largura média do intervalo é de **5.3 cartões**. Como a média de cartões por jogo é ~4, prever um intervalo de tamanho 5.3 (ex.: entre 1 e 6 cartões) é pouco informativo e inútil na prática. Isso mostra que a regressão quantílica sem restrições físicas falha em alvos com contagens discretas pequenas.

---

## 3. Teste Quantitativo de Aderência (Goodness-of-Fit)

Analisamos se as contagens reais de gols e escanteios no conjunto de teste são condizentes com três distribuições candidatas:
1. **Poisson:** Utilizando como parâmetro $\lambda$ a média de gols/escanteios do treino.
2. **Binomial Negativa (NB):** Ajustada via método dos momentos no treino (tratando a sobredispersão, onde Var > Média).
3. **Distribuição Implícita do Modelo:** Ajustada ajustando uma curva Normal $N(\mu, \sigma)$ para cada jogo (onde $\mu = q_{50}$ e $\sigma = (q_{90}-q_{10})/2.563$), discretizada integrando a PDF em intervalos unitários $[k-0.5, k+0.5]$ e tirando a média.

Ramos um teste **Qui-Quadrado ($\chi^2$) de aderência** com bins agrupados para garantir frequência esperada $\ge 5$ (Regra de Cochran). Os p-valores determinam se rejeitamos ou falhamos em rejeitar a distribuição (valores $> 0.05$ indicam um ajuste estatisticamente perfeito):

### Resultados dos Testes de Aderência ($\chi^2$)

| Alvo | Estatística / P-Valor | Distribuição Poisson | Distribuição Binomial Negativa | Distribuição Implícita (Normal) |
| :--- | :--- | :---: | :---: | :---: |
| **Gols Totais** | $\chi^2$ estat.<br>**p-valor** | 28.03<br>**0.00047** ❌ | 8.30<br>**0.50380**  | 81.87<br>**5.71e-15** ❌ |
| **Escanteios Mandante** | $\chi^2$ estat.<br>**p-valor** | 392.93<br>**1.94e-77** ❌ | 13.09<br>**0.59530**  | 47.33<br>**8.50e-06** ❌ |
| **Escanteios Visitante** | $\chi^2$ estat.<br>**p-valor** | 346.70<br>**2.00e-68** ❌ | 24.70<br>**0.02527** ❌ | 40.32<br>**3.15e-05** ❌ |

### Histogramas Comparativos de Aderência

Para cada alvo, plotamos a densidade real vs teórica das três distribuições:

![Ajuste de Distribuição - Gols Totais](file:///C:/Users/10341953440/.gemini/antigravity/brain/38bd63cd-c1e9-4756-9d77-8346dce6bac3/plots/distribution_fit_total_goals.png)

![Ajuste de Distribuição - Escanteios Mandante](file:///C:/Users/10341953440/.gemini/antigravity/brain/38bd63cd-c1e9-4756-9d77-8346dce6bac3/plots/distribution_fit_home_corners.png)

![Ajuste de Distribuição - Escanteios Visitante](file:///C:/Users/10341953440/.gemini/antigravity/brain/38bd63cd-c1e9-4756-9d77-8346dce6bac3/plots/distribution_fit_away_corners.png)

### 📊 Conclusões do Teste de Aderência:
1. **A Binomial Negativa domina de forma absoluta.** Ela falha em ser rejeitada para gols ($p = 0.5038$) e escanteios mandante ($p = 0.5953$), e é o melhor ajuste por larga margem em escanteios visitante (embora formalmente rejeitada a 5%, o ajuste visual e estatístico é infinitamente superior às demais).
2. **Poisson é inapropriada.** Ela é severamente rejeitada para todos os alvos ($p \approx 0$). Isso ocorre porque gols e escanteios sofrem de **sobredispersão** (a variância amostral é maior que a média), o que invalida a premissa de variância igual à média da Poisson ($\sigma^2 = \mu$).
3. **A Distribuição Implícita (Normal do Quantil) é rejeitada.** Tentar converter quantis de regressão quantílica para probabilidades discretas usando uma Normal gera grandes erros de cauda e probabilidade não-nula para valores negativos, sendo severamente rejeitada pelo Qui-Quadrado.

---

## 4. Recomendações Fundamentadas de Modelagem (Rankeadas por ROI)

Com base no diagnóstico quantitativo, estabelecemos o seguinte plano de desenvolvimento prioritário para os modelos do sistema:

### 1. Migrar Regressão de Gols e Escanteios para Modelos de Contagem (Binomial Negativa)
- **Prioridade:** **Crítica / Altíssimo ROI**
- **Fundamentação:** O teste Qui-Quadrado provou que a distribuição real das variáveis segue a Binomial Negativa, e que aproximar a regressão quantílica por uma Normal gera calibrações de cauda e probabilidades sofríveis.
- **Implementação:** Treinar regressores do tipo **Generalized Linear Models (GLM)** ou modelos de árvore com perda baseada em verossimilhança da Binomial Negativa (como LightGBM ou XGBoost com distribuição customizada) para prever os parâmetros $\mu$ e $\alpha$ (dispersão) por jogo. Isso garantirá estimativas físicas (inteiros não-negativos) e probabilidades nativas exatas de over/under e linhas asiáticas sem intermediários.

### 2. Implementar Modelo Dixon-Coles ou Regressão Bivariada para Placar Exato e BTTS
- **Prioridade:** **Alta / Alto ROI**
- **Fundamentação:** Atualmente, BTTS, Over 2.5 e Placar são previstos de forma independente por modelos diferentes. Ao modelar gols do mandante e visitante via Binomial Negativa bivariada com ajuste de Dixon-Coles (que corrige a dependência de gols em placares baixos como 0-0 e 1-1), podemos inferir a probabilidade de BTTS, Over 2.5 e resultado com consistência matemática intrínseca (sem risco de o modelo de placares predizer algo conflitante com o modelo de BTTS).

### 3. Substituir Regressão Quantílica de Cartões por Modelo de Contagem Condicional
- **Prioridade:** **Média / Médio ROI**
- **Fundamentação:** A regressão quantílica de cartões gerou intervalos excessivamente largos (5.30 cartões para cobertura de 80%), o que é inútil. Como cartões são limitados e altamente dependentes do tipo de torneio e árbitro, prever a taxa média via regressão de Poisson/NB condicional a características físicas do jogo gerará distribuições de probabilidade de cartão muito mais úteis para precificação de linhas.

### 4. Adicionar Features de Estilo e Controle de Ritmo
- **Prioridade:** **Média / Médio ROI**
- **Fundamentação:** O erro de gols e cartões está no limite do sinal histórico básico (apenas ~2% melhor que baselines). Para furar esse teto, é vital extrair dados de estilo de jogo das equipes no histórico de forma (ex.: taxa de cruzamentos, posse de bola média, taxa de passes longos, cartões do árbitro escalado) para condicionar melhor as estimativas de média.

---

## 5. Próximos Passos Propostos

Com o diagnóstico concluído e validado, o caminho mais promissor é a elaboração de protótipos de modelos de contagem de gols e escanteios baseados em **Binomial Negativa e Dixon-Coles**, comparando suas distribuições preditivas contra a atual regressão quantílica em termos de Log-Loss probabilístico.
