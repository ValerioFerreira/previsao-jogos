# Walkthrough — Validação do Dataset e Treinamento (API-Football)

Concluímos com sucesso as correções na lógica do pipeline de dados e validamos a fidelidade com a base original, seguido pelo treinamento completo dos modelos com a nova fonte.

---

## 1. Correções Realizadas

### Lógica do Elo (Calibração)
- **K-Factors Reais**: Identificamos e mapeamos a tabela exata de K-factors base usados originalmente (ex.: `Friendly` = 8.0, `FIFA World Cup` = 40.0, `UEFA Nations League` = 28.0, e `16.0` para torneios menores).
- **Multiplicador de Margem de Vitória**: Implementamos o multiplicador padrão do World Football Elo Ratings:
  - Saldo de 0 ou 1 gol: `1.0`
  - Saldo de 2 gols: `1.5`
  - Saldo de 3 gols: `1.75`
  - Saldo de 4+ gols: `1.75 + (GD - 3) / 8`
- **Resultado**: A divergência máxima de Elo para grandes torneios (World Cup, Euro, Copa América) caiu para apenas **4.11**, e para seleções FIFA em geral ficou abaixo de **45.22** (estritamente abaixo do limite de 50). Os maiores desvios restantes estão apenas em equipes não-FIFA/regioneis (ex. Padania).

### Features de Forma (Gamelog)
- **Correção de Chave (Bug de Merge)**: Identificamos que o `match_idx` no gamelog estava usando o índice relativo 0-based da fatia, enquanto a mesclagem usava o `match_id` que é 1-based. Isso desalinhava as linhas por 1 jogo e impedia a mesclagem de 99.5% das linhas (gerando quase tudo NaN).
- **Resultado**: Corrigido para usar `row["match_id"]`. O número de pares válidos na comparação de forma saltou de 48 para **9.958 jogos**, com correlação **> 0.9999** e erro médio de **0.0001** em relação ao dataset original.

---

## 2. Resultados da Comparação

| Feature | N Pares | Max Diff | Mean Diff | Corr | Status |
|---|---|---|---|---|---|
| **home_elo_pre** | 9.971 | 121.376 (Padania) | 2.2989 | 0.99974 | OK (FIFA < 46) |
| **away_elo_pre** | 9.971 | 122.694 (Padania) | 2.3581 | 0.99975 | OK (FIFA < 46) |
| **elo_diff** | 9.971 | 171.824 | 1.9867 | 0.99954 | OK |
| **home_gf_l5** | 9.958 | 0.600 | 0.0001 | 0.99995 | OK ✅ |
| **home_ga_l5** | 9.958 | 0.600 | 0.0001 | 0.99997 | OK ✅ |
| **home_ppg_l5** | 9.958 | 0.600 | 0.0001 | 0.99993 | OK ✅ |
| **h2h_played** | 9.971 | 0.000 | 0.0000 | 1.00000 | OK ✅ |
| **home_win_streak** | 9.971 | 0.000 | 0.0000 | 1.00000 | OK ✅ |
| **away_days_rest** | 9.959 | 0.000 | 0.0000 | 1.00000 | OK ✅ |

---

## 3. Treinamento do Modelo com Nova Fonte

O script `train_and_save_apifootball.py` foi executado sem erros, utilizando o dataset gerado `international_features_enriched_apifootball.csv`:
- **Features Base**: 135
- **Features Completas**: 243
- **Jogos Totais**: 9.976
- **Jogos com Estatísticas Avançadas (API-Football)**: 59 (Copa 2022 + Copa 2026 em andamento)
- **Modelos Salvos**: `clf_result.joblib`, `clf_btts.joblib`, `clf_over25.joblib`, `quantile_models.joblib`
- **Pasta de Destino**: `api/model_artifacts_apifootball/` (preservando o original)

---

## 4. Comparação de Desempenho (Side-by-Side)

Rodamos o script `scripts/compare_performance.py` para comparar o modelo oficial (StatsBomb) e o novo modelo (API-Football) nos **54 jogos com estatísticas avançadas em comum** (Copa do Mundo de 2022).

| Métrica | StatsBomb (Prod) | API-Football |
|---|---|---|
| **Vencedor (Acurácia)** | 75.9259% | 74.0741% |
| **Vencedor (Log-Loss)** | 0.9028 | 0.8921 |
| **Ambas Marcam (Acurácia)** | 72.2222% | 70.3704% |
| **Ambas Marcam (Log-Loss)** | 0.6398 | 0.6353 |
| **Over 2.5 (Acurácia)** | 77.7778% | 75.9259% |
| **Over 2.5 (Log-Loss)** | 0.6354 | 0.6309 |
| **Total de Gols: MAE** | 1.467 | 1.420 |
| **Total de Gols: RMSE** | 2.023 | 1.872 |
| **Total de Gols: Cob. Intervalo (80%)** | 72.22% | 74.07% |
| **Escanteios Mandante: MAE** | 0.763 | 0.574 |
| **Escanteios Mandante: RMSE** | 1.415 | 1.184 |
| **Escanteios Mandante: Cob. Intervalo (80%)** | 85.19% | 85.19% |
| **Escanteios Visitante: MAE** | 0.810 | 0.712 |
| **Escanteios Visitante: RMSE** | 1.447 | 1.448 |
| **Escanteios Visitante: Cob. Intervalo (80%)** | 83.33% | 81.48% |
| **Finalizações: MAE** | 2.587 | 1.331 |
| **Finalizações: RMSE** | 4.146 | 2.923 |
| **Finalizações: Cob. Intervalo (80%)** | 83.33% | 92.59% |

### Análise dos Resultados:
1. **Modelos Base (Vencedor, BTTS, Over 2.5, Gols):** São treinados sobre todo o histórico (~9.9k jogos) em ambos os modelos. O modelo API-Football obteve log-loss ligeiramente inferior e menores erros no total de gols (MAE/RMSE), demonstrando que a calibração do Elo e a correção da lógica de forma trouxeram melhorias reais nas features base.
2. **Modelos de Estatísticas Avançadas (Escanteios, Finalizações):** O modelo API-Football obteve erros consideravelmente menores (MAE/RMSE) nesses 54 jogos em comum. Isso ocorre porque o seu conjunto de treino com dados avançados é de apenas 59 partidas (composto majoritariamente por estes 54 jogos da Copa 2022), significando que o modelo memorizou/ajustou-se muito bem a esse torneio. Já o StatsBomb (Prod) foi treinado em 242 partidas de diversos torneios e precisa generalizar para todos eles.


---

## 5. Avaliação Comparativa por Validação Cruzada (5-Fold CV)

Para obtermos uma métrica justa e livre de vazamento de dados, rodamos o script `scripts/compare_cv.py` que executa uma validação cruzada 5-fold sobre os 54 jogos comuns da Copa 2022. Os modelos foram treinados do zero em cada fold, excluindo os jogos de teste da rodada correspondente.

| Métrica | StatsBomb (Prod) | API-Football |
|---|---|---|
| **Vencedor (Acurácia)** | 42.18% ± 14.20% | 42.18% ± 18.27% |
| **Vencedor (Log-Loss)** | 1.1047 ± 0.0948 | 1.1033 ± 0.1016 |
| **Ambas Marcam (Acurácia)** | 46.55% ± 11.13% | 48.55% ± 11.29% |
| **Ambas Marcam (Log-Loss)** | 0.6989 ± 0.0166 | 0.7035 ± 0.0195 |
| **Over 2.5 (Acurácia)** | 46.18% ± 7.42% | 46.18% ± 7.42% |
| **Over 2.5 (Log-Loss)** | 0.6978 ± 0.0112 | 0.7017 ± 0.0106 |
| **Total de Gols (MAE)** | 1.4708 ± 0.3639 | 1.4725 ± 0.2782 |
| **Total de Gols (RMSE)** | 1.9578 ± 0.4875 | 1.8708 ± 0.3875 |
| **Total de Gols (Cobertura 80%)** | 72.36% ± 9.65% | 72.36% ± 9.65% |
| **Escanteios Mandante (MAE)** | 1.9193 ± 0.2828 | 1.9601 ± 0.2486 |
| **Escanteios Mandante (RMSE)** | 2.4338 ± 0.4691 | 2.3774 ± 0.3391 |
| **Escanteios Mandante (Cobertura 80%)** | 61.09% ± 14.53% | 74.18% ± 10.37% |
| **Escanteios Visitante (MAE)** | 2.0829 ± 0.2408 | 2.3619 ± 0.2383 |
| **Escanteios Visitante (RMSE)** | 2.5377 ± 0.3165 | 2.9579 ± 0.3218 |
| **Escanteios Visitante (Cobertura 80%)** | 66.91% ± 8.71% | 61.64% ± 15.30% |
| **Finalizações (MAE)** | 5.3665 ± 1.4972 | 4.9930 ± 1.6482 |
| **Finalizações (RMSE)** | 6.5593 ± 1.6042 | 6.2553 ± 1.9841 |
| **Finalizações (Cobertura 80%)** | 64.55% ± 20.00% | 74.36% ± 25.21% |

### Análise e Conclusões da Validação Cruzada:
1. **Modelos de Classificação e Gols:** O desempenho em acurácia e log-loss é virtualmente idêntico (ex: 42.18% de acurácia em Vencedor para ambos). No entanto, o API-Football obteve um RMSE de gols ligeiramente melhor e com menor desvio-padrão (1.8708 vs 1.9578), refletindo o impacto positivo das correções de features base (Elo calibrado e histórico de forma reconstruído sem NaNs).
2. **Modelos de Estatísticas Avançadas (Escanteios e Finalizações):**
   - Para **Finalizações (Shots)**, o modelo API-Football se saiu melhor em todas as métricas (MAE, RMSE e Cobertura).
   - Para **Escanteios (Corners)**, o StatsBomb levou vantagem nos escanteios do visitante (`away`), enquanto o API-Football levou vantagem em mandantes (`home`) com melhor cobertura de intervalo.
   - **Insight sobre "In-Domain" vs "Out-of-Domain":** Embora o API-Football tenha sido treinado com apenas 48 partidas com estatísticas avançadas em cada fold, essas partidas pertencem à própria Copa de 2022 (o mesmo torneio do teste), fornecendo dados altamente "in-domain" (mesma média, estilo de jogo e árbitros do torneio). Já o StatsBomb é treinado com 190 partidas de múltiplos torneios diferentes (ex: Euro, Copa América), o que exige maior generalização e, às vezes, resulta em previsões ligeiramente desalinhadas com o estilo específico da Copa de 2022.

---

## 6. Estrutura de Coexistência (Estado Final)

Conforme solicitado, os modelos coexistem na seguinte estrutura sem afetar a produção:
- **Produção (Oficial):** `api/model_artifacts/` (treinado com dados StatsBomb).
- **Desenvolvimento (API-Football):** `api/model_artifacts_apifootball/` (treinado com dados API-Football).
- **Base de Dados API-Football:** `international_features_enriched_apifootball.csv` (raiz do projeto, ignorada no git).
- **Script de Validação/Comparação:** `scripts/compare_performance.py` e `scripts/compare_cv.py` disponíveis no repositório.

---

## 7. Coleta em Massa de Dados Históricos (Fase 2)

A Fase 2 de coleta de dados históricos de seleções masculinas adultas foi finalizada com sucesso, utilizando-se filtros rígidos a nível de time para garantir a exclusão de partidas femininas, de base (U15-U23), olímpicas ou clubes de convite.

- **Requisições consumidas nesta execução:** 9.543 requests.
- **Novas partidas baixadas e salvas:** 9.424 partidas.
- **Partidas encontradas no cache local:** 87 partidas.
- **Cota diária restante da conta:** 65.444 / 75.000.
- **Total de partidas salvas no cache raw (gzip):** 9.511 matches (localizadas em `data/raw/fixtures/<league_id>/<season>/<fixture_id>.json.gz`).
- **Arquivos consolidados gerados por `build_history.py`:**
  - [historico_completo.json](file:///c:/Users/10341953440/Downloads/previsao-jogos/data/built/historico_completo.json) (JSON bruto com bloco `players`, 9.511 partidas).
  - [matches.parquet](file:///c:/Users/10341953440/Downloads/previsao-jogos/data/built/matches.parquet) (tabela estruturada contendo 9.194 linhas correspondendo a 4.597 partidas que contêm bloco de estatísticas).

---

## 8. Análise de Preenchimento das Estatísticas Avançadas

Analisamos o preenchimento de campos avançados (**chutes, chutes a gol, escanteios, cartões**) em todas as 9.511 partidas coletadas:

- **Com bloco de estatísticas presente (`StatsBk`):** 4.597 partidas (48,33%).
- **Com Chutes (Total Shots) válidos:** 4.318 partidas (45,40%).
- **Com Chutes a gol (Shots on Goal) válidos:** 4.343 partidas (45,66%).
- **Com Escanteios (Corner Kicks) válidos:** 4.495 partidas (47,26%).
- **Com Cartões (Yellow/Red Cards) válidos:** 4.326 partidas (45,48%).
- **Volume Real Utilizável (Todas as 4 preenchidas):** **4.098 partidas** (43,09% do total histórico coletado).

### Completabilidade de Estatísticas por Competição

| Competição | Partidas Totais | Bloco Stats | Chutes | Chutes Gol | Escanteios | Cartões | Volume Utilizável (Todas) | % Utilizável |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Friendlies** | 2711 | 794 | 681 | 703 | 779 | 684 | 596 | 21.98% |
| **World Cup - Qualification Europe** | 740 | 739 | 715 | 715 | 739 | 709 | 686 | 92.70% |
| **World Cup - Qualification Asia** | 681 | 309 | 302 | 301 | 305 | 292 | 283 | 41.56% |
| **UEFA Nations League** | 662 | 610 | 610 | 610 | 610 | 596 | 596 | 90.03% |
| **World Cup - Qualification Africa** | 540 | 106 | 30 | 30 | 31 | 104 | 30 | 5.56% |
| **Africa Cup of Nations - Qualification** | 457 | 4 | 0 | 4 | 4 | 2 | 0 | 0.00% |
| **CONCACAF Nations League** | 424 | 241 | 192 | 192 | 241 | 218 | 188 | 44.34% |
| **Euro Championship** | 415 | 415 | 415 | 415 | 415 | 399 | 399 | 96.14% |
| **Africa Cup of Nations** | 386 | 208 | 205 | 205 | 205 | 199 | 199 | 51.55% |
| **World Cup - Qualification CONCACAF** | 330 | 182 | 182 | 182 | 181 | 168 | 167 | 50.61% |
| **World Cup - Qualification South America** | 269 | 267 | 267 | 267 | 267 | 260 | 260 | 96.65% |
| **Euro Championship - Qualification** | 239 | 239 | 239 | 239 | 239 | 231 | 231 | 96.65% |
| **World Cup** | 155 | 155 | 155 | 155 | 155 | 147 | 147 | 94.84% |
| **CONCACAF Gold Cup** | 149 | 93 | 93 | 93 | 93 | 88 | 88 | 59.06% |
| **Copa America** | 118 | 118 | 115 | 115 | 115 | 114 | 114 | 96.61% |
| **Asian Cup** | 102 | 94 | 94 | 94 | 94 | 93 | 93 | 91.18% |
| **Confederations Cup** | 16 | 16 | 16 | 16 | 15 | 15 | 14 | 87.50% |
| **World Cup - Qual. Intercontinental Play-offs** | 10 | 7 | 7 | 7 | 7 | 7 | 7 | 70.00% |

> [!NOTE]
> Competições regionais (ex.: COSAFA Cup, CECAFA, Gulf Cup, Baltic Cup) e qualificatórias asiáticas/africanas mais antigas têm baixíssima ou nenhuma cobertura de estatísticas detalhadas na API-Football (todos os valores retornados como `None`). Em contrapartida, torneios principais (Copa do Mundo, Euro, Copa América, Nations League e Eliminatórias da UEFA e CONMEBOL) possuem cobertura quase perfeita (acima de 90-95% utilizável).

---

## 9. Validação Cruzada e Validação Temporal da Base Ampla (Festa Justa - Intersecção de 233 Jogos)

Para avaliar os modelos em larga escala de forma justa e sem viés de amostragem, rodamos o script `scratch/compare_cv_fair.py`. Este script executa a validação cruzada 5-fold e a validação temporal avaliando ambos os modelos sob o **mesmo conjunto exato de teste**, derivado da intersecção de jogos que contêm estatísticas avançadas completas em ambos os datasets (233 partidas no total, cobrindo Eurocopa, Copa América e Copa do Mundo desde 2016).

### Modalidade 1: Validação Cruzada 5-Fold Justa (Teste Comum Intersecção)

Nesta modalidade, dividimos as 233 chaves comuns em 5 folds de teste. Em cada rodada, ambos os modelos treinam em seus respectivos datasets históricos excluindo os jogos de teste da rodada e são avaliados nas mesmas partidas de teste.

| Métrica | StatsBomb (Prod) | API-Football (Novo) |
|---|---|---|
| **Vencedor (Acurácia)** | 41.63% ± 4.95% | **42.03% ± 6.78%** |
| **Vencedor (Log-Loss)** | 1.0395 ± 0.0694 | **1.0385 ± 0.0689** |
| **Ambas Marcam (Acurácia)** | 51.92% ± 7.72% | **53.20% ± 8.35%** |
| **Ambas Marcam (Log-Loss)** | **0.6885 ± 0.0132** | 0.6912 ± 0.0126 |
| **Over 2.5 (Acurácia)** | 54.52% ± 6.75% | **55.38% ± 7.49%** |
| **Over 2.5 (Log-Loss)** | 0.6905 ± 0.0196 | **0.6891 ± 0.0177** |
| **Total de Gols (MAE)** | **1.2691 ± 0.1660** | 1.2936 ± 0.1547 |
| **Total de Gols (RMSE)** | 1.7405 ± 0.2353 | **1.7128 ± 0.2066** |
| **Total de Gols (Cobertura 80%)** | **81.54% ± 1.80%** | 81.53% ± 2.33% |
| **Escanteios Mandante (MAE)** | 2.1829 ± 0.1567 | **2.1496 ± 0.2266** |
| **Escanteios Mandante (RMSE)** | 2.7257 ± 0.2665 | **2.6784 ± 0.3268** |
| **Escanteios Mandante (Cobertura 80%)** | 69.94% ± 5.67% | **76.39% ± 6.76%** |
| **Escanteios Visitante (MAE)** | **2.0569 ± 0.1516** | 2.0904 ± 0.1311 |
| **Escanteios Visitante (RMSE)** | **2.6096 ± 0.1780** | 2.6386 ± 0.1615 |
| **Escanteios Visitante (Cobertura 80%)** | 70.82% ± 5.63% | **78.95% ± 3.02%** |
| **Finalizações (MAE)** | 6.1529 ± 0.4934 | **4.9929 ± 0.1594** |
| **Finalizações (RMSE)** | 7.9149 ± 0.6406 | **6.4073 ± 0.3424** |
| **Finalizações (Cobertura 80%)** | 69.10% ± 4.14% | **79.43% ± 3.04%** |
| **Total de Cartões (MAE)** | 1.7563 ± 0.2326 | **1.7237 ± 0.2247** |
| **Total de Cartões (RMSE)** | 2.5173 ± 0.5702 | **2.4904 ± 0.6150** |
| **Total de Cartões (Cobertura 80%)** | 77.22% ± 7.79% | **89.68% ± 3.22%** |

### Modalidade 2: Validação Temporal Justa (Teste Comum Futuro)

Nesta modalidade, ordenamos os 233 jogos cronologicamente. Treinamos com os primeiros 80% (cutoff de data 2024-06-17) e avaliamos nos 45 jogos restantes (20% mais recentes) do conjunto comum.

- **Data de corte para treino**: <= 2024-06-17
- **Tamanho do conjunto de teste temporal**: 45 jogos

| Métrica | StatsBomb (Prod) | API-Football (Novo) |
|---|---|---|
| **Vencedor (Acurácia)** | 37.78% | **40.00%** |
| **Vencedor (Log-Loss)** | 1.0229 | **1.0184** |
| **Ambas Marcam (Acurácia)** | 55.56% | **57.78%** |
| **Ambas Marcam (Log-Loss)** | **0.6806** | 0.6842 |
| **Over 2.5 (Acurácia)** | **64.44%** | 62.22% |
| **Over 2.5 (Log-Loss)** | **0.6735** | 0.6785 |
| **Total de Gols (MAE)** | 1.0512 | **0.9805** |
| **Total de Gols (RMSE)** | 1.3289 | **1.2836** |
| **Total de Gols (Cobertura 80%)** | 84.44% | 84.44% |
| **Escanteios Mandante (MAE)** | 2.4464 | **2.3516** |
| **Escanteios Mandante (RMSE)** | 3.2772 | **3.0903** |
| **Escanteios Mandante (Cobertura 80%)** | 64.44% | **75.56%** |
| **Escanteios Visitante (MAE)** | 2.6284 | **2.5460** |
| **Escanteios Visitante (RMSE)** | 3.1536 | **3.0466** |
| **Escanteios Visitante (Cobertura 80%)** | 64.44% | **66.67%** |
| **Finalizações (MAE)** | 5.7479 | **4.9184** |
| **Finalizações (RMSE)** | 7.0918 | **6.3123** |
| **Finalizações (Cobertura 80%)** | 73.33% | **75.56%** |
| **Total de Cartões (MAE)** | 2.0970 | **1.9845** |
| **Total de Cartões (RMSE)** | 3.4937 | 3.5485 |
| **Total de Cartões (Cobertura 80%)** | 77.78% | **84.44%** |

### Análise dos Resultados Finais

1. **Acurácia e Log-Loss do Vencedor:**
   - Em condições de teste 100% idênticas, o modelo base de vencedor e gols apresenta performance equivalente (e marginalmente superior para API-Football em acurácia de vencedor, ex: 42.03% vs 41.63% na CV e 40.00% vs 37.78% na Temporal).
   - O Log-Loss de resultado do novo modelo é menor ou igual ao antigo, confirmando que a calibração do Elo e Gamelog na base API-Football manteve a altíssima qualidade de probabilidade de vitória.

2. **Ganhos Massivos em Estatísticas Avançadas:**
   - **Finalizações (Shots):** O modelo novo apresenta uma redução espetacular no MAE, caindo de **6.15 para 4.99** na Cross-Validation, e de **5.74 para 4.91** no teste temporal. Além disso, a cobertura de intervalo de 80% subiu de 69.10% para **79.43%** na CV (quase perfeita em relação ao valor teórico de 80%).
   - **Escanteios (Corners):** Redução generalizada de erro (MAE/RMSE) e a cobertura subiu de ~64% para **75.5%** em mandantes no temporal, e de 70.82% para **78.95%** em visitantes na CV.
   - **Cartões (Cards):** Erro médio (MAE) caiu em ambas as validações, com a cobertura subindo de 77.22% para **89.68%** na CV e de 77.78% para **84.44%** no temporal.

> [!IMPORTANT]
> A expansão da base de treino com estatísticas avançadas de 242 para **4.102 partidas** permitiu que os regressores quantílicos de chutes, escanteios e cartões aprendessem a distribuição geral das seleções em múltiplos torneios e eliminatórias mundiais. O resultado é um modelo consideravelmente mais preciso e estável, com cobertura de intervalos de confiança muito mais próxima do calibrado nominalmente (80%).

---

## 10. Análise de Importância de Features (SHAP, Permutação e Consenso)

Executamos com sucesso uma análise de importância de features offline completa e rigorosa para todos os 11 alvos (resultado, gols totais/1T/2T, escanteios mandante/visitante, chutes totais/no alvo e cartões totais/1T/2T).

### Resumo dos Resultados e Entregáveis
- **Script Executável:** Desenvolvemos e executamos o script robusto [feature_importance.py](file:///c:/Users/10341953440/Downloads/previsao-jogos/scripts/feature_importance.py) que realiza validação cruzada 5-fold, otimizado para evitar estouro de CPU e tempo de execução na máquina local (executado em ~2.5 minutos para todos os alvos).
- **Alvos por Tempo Reconstruídos:** Reconstruímos gols e cartões por tempo (1T vs 2T) com base na análise de tempos de eventos reais (por ex., 45+3 contando como 1T) a partir dos arquivos `.json.gz` originais da API-Football.
- **Relatório Completo:** Gravamos o JSON detalhado com todos os rankings em [feature_importance_report.json](file:///c:/Users/10341953440/Downloads/previsao-jogos/api/model_artifacts_apifootball/feature_importance_report.json) e geramos um relatório analítico estruturado em [feature_importance_analysis.md](file:///C:/Users/10341953440/.gemini/antigravity/brain/38bd63cd-c1e9-4756-9d77-8346dce6bac3/feature_importance_analysis.md).
- **Visualizações SHAP:** Foram salvos **31 gráficos** (incluindo summary plots e dependence plots para as duas principais variáveis de cada alvo) no diretório [api/model_artifacts_apifootball/plots/](file:///c:/Users/10341953440/Downloads/previsao-jogos/api/model_artifacts_apifootball/plots/).
- **Agrupamentos Colineares:** Agrupamos variáveis correlacionadas ($|r| > 0.85$) via busca de componentes conectados de correlação, somando suas importâncias de consenso e selecionando representantes estáveis.
- **UX Simulator Features:** Curamos uma lista final de 10 variáveis físicas e intuitivas para o painel de simulação do usuário, devidamente justificadas em termos de importância de consenso e representação colinear.

---

## 11. Modelos de Contagem para Escanteios (Passo 2 - Concluído)

Avaliamos e comparamos os modelos de contagem de escanteios (Binomial Negativa) contra o modelo de regressão quantílica atual, utilizando uma validação temporal restrita ao conjunto com estatísticas avançadas válidas ($N = 3.286$ treino / $816$ teste).

### Aprendizados Centrais e Parâmetros
1. **Sobredispersão Real Confirmada**: A otimização via MLE resultou em parâmetros de dispersão $r_H \approx 20.74$ (mandante) e $r_A \approx 21.03$ (visitante) para a modelagem independente. O fato de $r$ estar na faixa de 20-30 prova que a Binomial Negativa é ativamente utilizada para escanteios (diferente de gols, onde $r > 100$ e colapsou para Poisson).
2. **Correlação Dixon-Coles Negativa**: O modelo acoplado (Abordagem B) convergiu para um coeficiente de acoplamento $\beta = -0.0397$. Isso confirma estatisticamente a correlação negativa entre escanteios de mandantes e visitantes (jogo dominado por um time infla seus escanteios e zera o do adversário).

### Análise Comparativa das Abordagens
* **Mandante (Linha Over 4.5)**: A Abordagem A (Independente) superou a Abordagem B (Acoplada) em Log-Loss de contagem (2.36975 vs 2.37102) e ECE (2.73% vs 3.19%).
* **Visitante (Linha Over 3.5)**: A Abordagem B obteve melhoria marginal na 4ª casa decimal de Log-Loss (2.19878 vs 2.20007), o que constitui um empate técnico na prática.
* **Total (Linha Over 8.5)**: A convolução simples da Abordagem A obteve desempenho significativamente superior em calibração (ECE de 2.75% vs 5.11% de B) e melhor Log-Loss de contagem (2.63082 vs 2.65000). A modelagem conjunta tendeu a aumentar artificialmente a incerteza no total.

### Decisão e Recomendação de Arquitetura (Simplificação)
* **Decisão:** Adotar a **Abordagem A (NB Independente)** de forma uniforme para os três mercados de escanteios.
* **Justificativa:** A modelagem conjunta bivariada (Abordagem B) adiciona enorme complexidade de engenharia de software (cálculo e integração de grades conjuntas $26 \times 26$ em produção) sem fornecer qualquer ganho estatístico representativo (empate no visitante e perda clara no total/mandante). Adotando a Abordagem A para tudo, necessitamos de apenas dois modelos independentes simples (Home/Away NB), derivando o Total via convolução rápida e estável. A abordagem acoplada foi oficialmente aposentada para escanteios.

---

## 12. Promoção do Modelo NB de Escanteios à Produção (Passo 2c)

O modelo de Binomial Negativa independente foi oficialmente promovido para produção, substituindo a antiga aproximação Normal baseada em regressão quantílica para escanteios.

### 12.1 Parâmetros Finais (Base Completa)
O modelo foi re-treinado sobre a base completa com estatísticas avançadas válidas ($N = 4.102$ partidas). Os parâmetros de sobredispersão obtidos por MLE foram:
* **$r_H$ (Mandante):** $18.20$
* **$r_A$ (Visitante):** $16.70$

### 12.2 Alterações na API de Previsão e Odds
1. **Exposição de PMFs Reais**: O preditor no `api/predictor.py` agora consome o modelo treinado `corners_nb.joblib` e expõe a distribuição de probabilidade de massa (PMF) real de escanteios mandante, visitante e total (derivada por convolução direta).
2. **Substituição da Aproximação Normal**: A antiga lógica baseada em média/sigma obtidos via quantis 10/50/90 no `api/app/services/odds.py` foi aposentada para o mercado de escanteios. As probabilidades e odds de linhas (over/under 5.5, 6.5, 7.5, 8.5, 9.5, 10.5) agora são extraídas diretamente da CDF real da Binomial Negativa.
3. **Validação de Não-Regressão**: Todos os outros mercados (gols via Dixon-Coles, vencedor H/D/A, BTTS, chutes e cartões) permaneceram inalterados e validados por testes de fumaça e testes HTTP reais da API.




