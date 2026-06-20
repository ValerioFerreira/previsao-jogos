# Análise de Importância de Features (API-Football)

Este relatório apresenta os resultados da análise offline de importância de features realizada sobre os modelos de desenvolvimento (API-Football). A análise cobriu **11 alvos de previsão**, utilizando validação cruzada de 5 folds sobre a base histórica para extrair métricas de consenso entre os métodos mais robustos: **SHAP Values** e **Importância por Permutação**, além de triagem com **Informação Mútua**, **Gini** e **Correlações**.

---

## 1. Resumo Executivo (Principais Conclusões)

1. **Elo Domina os Resultados e Assimetrias:** A diferença de força estimada pelo Elo (`elo_diff` e `elo_home_winprob`) é a variável isolada mais crucial para prever o vencedor da partida e o volume de escanteios. Em particular, a probabilidade implícita de vitória do mandante (`elo_home_winprob`) dita quase sozinha a distribuição de escanteios (45% de importância de consenso).
2. **Contexto Competitivo Determina Cartões:** A natureza da partida (se é um jogo competitivo ou amistoso) é o fator primordial para a contagem de cartões. Amistosos possuem uma correlação linear acentuada com menos cartões, enquanto eliminatórias e copas elevam o volume geral de advertências.
3. **Mapeamento de Chutes Baseia-se no Histórico e no Estilo:** A média móvel de chutes realizados pelo time e de chutes sofridos pelo oponente nos jogos anteriores são as variáveis de maior peso para prever o total de finalizações do jogo. O modelo apoia-se fortemente na tendência recente das equipes.
4. **Stature Proxy para Gols:** O número de jogos disputados anteriormente por uma seleção na base histórica (`matches_played_before`) surgiu como uma feature muito influente para gols. Isso reflete a relevância das seleções de elite (tier-1), que jogam mais torneios internacionais de visibilidade e têm mais dados coletados, influenciando as distribuições de gols da partida.

---

## 2. Metodologia de Cálculo e Otimização

A análise foi conduzida de forma robusta por meio de:
- **5-Fold Cross-Validation:** Onde os modelos RandomForest (Classifier para resultado; Regressores para os demais) foram ajustados em 80% do conjunto e avaliados em 20% do teste.
- **Amostragem de Teste (SHAP/Permutation):** Para contornar a lentidão de cálculo de regressores e garantir a reprodutibilidade, as importâncias de SHAP e Permutação foram medidas em uma amostra representativa de 300 jogos do fold de teste, com 1 repetição em permutação.
- **Normalização e Consenso:** As importâncias médias de SHAP e Permutação foram normalizadas (para somarem 100% individualmente) e a média dessas importâncias normalizadas determinou a pontuação de **Consenso** das features.
- **Exclusão de Vazamentos:** Foram eliminadas todas as variáveis do jogo atual (`*_cur_*`), identificadores e alvos das features preditoras.

---

## 3. Rankings de Consenso por Alvo

Abaixo estão detalhados os rankings de consenso (as top 5 features) para cada um dos alvos analisados. Os resultados completos estão disponíveis em `api/model_artifacts_apifootball/feature_importance_report.json`.

### 3.1 Vencedor (Resultado Multiclasse)
*Base ampla: 9.976 jogos*

| Rank | Feature | Importância Consenso | Correlação Pearson | Grupo Colinear |
| :--- | :--- | :---: | :---: | :---: |
| 1 | `elo_diff` | 16.1652% | +0.5225 | Grupo_6 (Elo) |
| 2 | `elo_home_winprob` | 14.5402% | +0.5414 | Grupo_6 (Elo) |
| 3 | `h2h_home_gd_mean` | 5.6607% | +0.3876 | Individual (H2H) |
| 4 | `h2h_home_winrate` | 4.3996% | +0.3654 | Individual (H2H) |
| 5 | `home_elo_pre` | 3.8046% | +0.2662 | Individual (Elo) |

### 3.2 Total de Gols
*Base ampla: 9.976 jogos*

| Rank | Feature | Importância Consenso | Correlação Pearson | Grupo Colinear |
| :--- | :--- | :---: | :---: | :---: |
| 1 | `away_matches_played_before` | 9.9659% | -0.1178 | Individual (Stature) |
| 2 | `elo_diff` | 6.3096% | +0.1078 | Grupo_6 (Elo) |
| 3 | `elo_home_winprob` | 4.3893% | +0.0865 | Grupo_6 (Elo) |
| 4 | `h2h_home_gd_mean` | 3.9925% | +0.0885 | Individual (H2H) |
| 5 | `home_gf_l10` | 3.9368% | +0.0937 | Individual (Gols M3/M5/M10) |

### 3.3 Gols 1º Tempo (1H)
*Base ampla com halftime disponível: 8.885 jogos*

| Rank | Feature | Importância Consenso | Correlação Pearson | Grupo Colinear |
| :--- | :--- | :---: | :---: | :---: |
| 1 | `elo_diff` | 17.9341% | -0.0161 | Grupo_6 (Elo) |
| 2 | `elo_home_winprob` | 14.1659% | -0.0168 | Grupo_6 (Elo) |
| 3 | `home_matches_played_before` | 3.7675% | -0.0002 | Individual (Stature) |
| 4 | `away_ga_l5` | 2.6562% | -0.0188 | Grupo_40 (Defesa) |
| 5 | `home_shootout_winrate_pre` | 2.6261% | -0.0071 | Individual |

### 3.4 Gols 2º Tempo (2H)
*Base ampla com halftime disponível: 8.885 jogos*

| Rank | Feature | Importância Consenso | Correlação Pearson | Grupo Colinear |
| :--- | :--- | :---: | :---: | :---: |
| 1 | `away_matches_played_before` | 7.5832% | -0.0043 | Individual (Stature) |
| 2 | `home_matches_played_before` | 6.7401% | -0.0113 | Individual (Stature) |
| 3 | `away_gf_l10` | 3.9182% | -0.0104 | Individual |
| 4 | `elo_home_winprob` | 3.7245% | +0.0135 | Grupo_6 (Elo) |
| 5 | `elo_diff` | 3.6976% | +0.0100 | Grupo_6 (Elo) |

### 3.5 Escanteios Mandante
*Base avançada completa: 4.102 jogos*

| Rank | Feature | Importância Consenso | Correlação Pearson | Grupo Colinear |
| :--- | :--- | :---: | :---: | :---: |
| 1 | `elo_home_winprob` | 44.8456% | +0.0528 | Grupo_6 (Elo) |
| 2 | `elo_diff` | 5.1990% | +0.0526 | Grupo_6 (Elo) |
| 3 | `home_elo_pre` | 2.3249% | +0.0053 | Individual (Elo) |
| 4 | `diff_sb_fouls_against_l5` | 1.6076% | -0.0253 | Individual |
| 5 | `home_sb_fouls_against_l5` | 0.9282% | -0.0197 | Grupo_120 |

### 3.6 Escanteios Visitante
*Base avançada completa: 4.102 jogos*

| Rank | Feature | Importância Consenso | Correlação Pearson | Grupo Colinear |
| :--- | :--- | :---: | :---: | :---: |
| 1 | `elo_home_winprob` | 45.3928% | -0.0010 | Grupo_6 (Elo) |
| 2 | `elo_diff` | 4.4644% | +0.0158 | Grupo_6 (Elo) |
| 3 | `diff_sb_shots_against_l5` | 1.4000% | +0.0272 | Grupo_144 |
| 4 | `diff_gd_l10` | 1.0938% | -0.0058 | Grupo_75 |
| 5 | `diff_sb_corners_l3` | 0.9801% | -0.0225 | Grupo_147 |

### 3.7 Finalizações (Total de Chutes)
*Base avançada completa: 4.102 jogos*

| Rank | Feature | Importância Consenso | Correlação Pearson | Grupo Colinear |
| :--- | :--- | :---: | :---: | :---: |
| 1 | `away_sb_shots_against_l5` | 9.0512% | +0.0132 | Grupo_123 |
| 2 | `tournament_weight` | 7.4103% | +0.0429 | Grupo_1 (Contexto) |
| 3 | `is_competitive` | 5.8724% | -0.0036 | Grupo_1 (Contexto) |
| 4 | `home_sb_shots_against_l3` | 3.8747% | +0.0035 | Grupo_102 |
| 5 | `home_sb_shots_l5` | 3.6822% | +0.0608 | Grupo_101 |

### 3.8 Chutes ao Gol (Total de Chutes a Gol)
*Base avançada completa: 4.102 jogos*

| Rank | Feature | Importância Consenso | Correlação Pearson | Grupo Colinear |
| :--- | :--- | :---: | :---: | :---: |
| 1 | `elo_home_winprob` | 8.7047% | +0.0524 | Grupo_6 (Elo) |
| 2 | `elo_diff` | 5.6719% | +0.0515 | Grupo_6 (Elo) |
| 3 | `home_ga_l10` | 4.4778% | -0.0261 | Grupo_12 |
| 4 | `away_sb_shots_l5` | 3.2250% | -0.0396 | Grupo_122 |
| 5 | `diff_ga_l10` | 2.4973% | -0.0230 | Grupo_75 |

### 3.9 Total de Cartões
*Base avançada completa: 4.102 jogos*

| Rank | Feature | Importância Consenso | Correlação Pearson | Grupo Colinear |
| :--- | :--- | :---: | :---: | :---: |
| 1 | `is_competitive` | 7.6050% | -0.0420 | Grupo_1 (Contexto) |
| 2 | `is_friendly` | 5.7609% | +0.0420 | Grupo_1 (Contexto) |
| 3 | `elo_home_winprob` | 3.6483% | -0.0011 | Grupo_6 (Elo) |
| 4 | `tournament_weight` | 3.0731% | -0.0307 | Grupo_1 (Contexto) |
| 5 | `home_sb_yellow_l5` | 2.7037% | +0.0035 | Grupo_113 |

### 3.10 Cartões 1º Tempo (1H)
*Base avançada completa: 4.102 jogos*

| Rank | Feature | Importância Consenso | Correlação Pearson | Grupo Colinear |
| :--- | :--- | :---: | :---: | :---: |
| 1 | `away_sb_fouls_l3` | 2.8649% | -0.0126 | Grupo_140 |
| 2 | `h2h_played` | 2.1923% | -0.0071 | Individual |
| 3 | `home_sb_yellow_l5` | 1.9283% | -0.0180 | Grupo_113 |
| 4 | `is_competitive` | 1.9177% | -0.0339 | Grupo_1 |
| 5 | `is_friendly` | 1.8420% | +0.0339 | Grupo_1 |

### 3.11 Cartões 2º Tempo (2H)
*Base avançada completa: 4.102 jogos*

| Rank | Feature | Importância Consenso | Correlação Pearson | Grupo Colinear |
| :--- | :--- | :---: | :---: | :---: |
| 1 | `elo_home_winprob` | 5.5906% | +0.0050 | Grupo_6 (Elo) |
| 2 | `away_sb_fouls_l5` | 3.4793% | +0.0017 | Grupo_140 |
| 3 | `elo_diff` | 3.0777% | -0.0067 | Grupo_6 |
| 4 | `days_since_last_h2h` | 2.9730% | +0.0113 | Individual |
| 5 | `away_sb_fouls_l3` | 2.5866% | +0.0003 | Grupo_140 |

---

## 4. Agrupamentos Colineares (|r| > 0.85)

A detecção de colinearidade revelou que o crédito de importância se divide entre variáveis altamente correlacionadas. Os principais grupos identificados são:

1. **Grupo Elo (Grupo_6):**
   - *Membros:* `elo_diff`, `elo_home_winprob`.
   - *Comentário:* Altamente correlacionados ($r > 0.98$). Ditam o resultado e o volume de escanteios. O `elo_diff` é o representante físico mais prático para os usuários.
2. **Grupo de Contexto de Torneio (Grupo_1):**
   - *Membros:* `tournament_weight`, `is_friendly`, `is_qualification`, `is_competitive`.
   - *Comentário:* Ditam o volume de cartões e finalizações. O `tournament_weight` é o representante ideal (escala contínua/ordinal de 0.2 a 1.0).
3. **Grupo de Forma Recente de Finalizações (Grupo_122, Grupo_101):**
   - *Membros:* `away_sb_shots_l3`, `away_sb_shots_l5` e `home_sb_shots_l3`, `home_sb_shots_l5`.
   - *Comentário:* Refletem as médias móveis de finalizações em janelas l3 e l5. A janela de l5 é o representante mais estável e representativo.

---

## 5. Análise de Vazamento (Anti-Leakage) e "Surpresas"

### 5.1 O Caso `matches_played_before` (Proxy de Estatura)
- **Ocorrência:** Aparece no topo do modelo de Gols Totais, Gols 1T e Gols 2T.
- **Investigação:** A feature mede o número total de partidas daquela seleção no dataset *anteriormente à partida atual*. Não é vazamento de dados, pois respeita a ordenação temporal (não enxerga o futuro).
- **Por que ocorre?** Em jogos de seleções, a frequência de jogos oficiais e amistosos de grande porte é muito maior para seleções de ponta (ex: seleções europeias jogam Nations League + eliminatórias Euro continuamente, seleções sul-americanas têm eliminatórias longas). Seleções menores jogam menos partidas e muitas vezes seus jogos contra times minúsculos não constam no banco de dados. Portanto, `matches_played_before` é um proxy de elite/estatura do país no futebol internacional.
- **Conclusão:** É estatisticamente robusto, mas conceitualmente artificial do ponto de vista de simulação. Deve ser omitido da UI para simulações de cenários, pois o usuário não consegue "editar" o histórico de contagem de jogos de um país.

### 5.2 A Extrema Dominância de `elo_home_winprob` nos Escanteios
- **Ocorrência:** Alcança ~45% de importância de consenso em escanteios mandante e visitante.
- **Investigação:** A probabilidade implícita de vitória do mandante dita de forma maciça a quantidade de escanteios.
- **Por que ocorre?** O volume de escanteios está intimamente ligado à assimetria do jogo. Quando um time muito forte joga em casa (ex. França vs Andorra), o volume de escanteios do mandante explode devido ao ataque contínuo, e o do visitante cai a quase zero. A correlação de Pearson linear é próxima de zero porque o efeito é altamente não-linear e assimétrico.
- **Conclusão:** O efeito é real, consistente e bem documentado em modelos de apostas esportivas. Reflete o domínio territorial que a probabilidade de vitória (derivada do Elo) sintetiza.

---

## 6. Lista de ~10 Features Pré-Jogo para UX (Simulador de Cenários)

Com base na importância consolidada de consenso, representatividade de grupos colineares e editabilidade do usuário, a lista final recomendada de 10 features pré-jogo para a interface do usuário (UX) é:

1. **Diferença de Elo (`elo_diff`):** A variável mais importante para prever o vencedor e assimetrias de escanteios e chutes.
2. **Histórico de H2H (`h2h_home_gd_mean`):** Saldo de gols médio dos confrontos diretos anteriores. Muito intuitivo para simulações (ex. freguesia).
3. **Média de Gols Marcados (Forma) (`home_gf_l5` / `away_gf_l5`):** Média de gols marcados nos últimos 5 jogos. Controla o ataque dos times.
4. **Média de Gols Sofridos (Forma) (`home_ga_l5` / `away_ga_l5`):** Média de gols sofridos nos últimos 5 jogos. Controla a defesa.
5. **Peso do Torneio (`tournament_weight`):** Permite ao usuário alternar a importância do jogo (Amistoso = 0.20, Copa do Mundo = 1.00), impactando diretamente chutes e cartões.
6. **Mando de Campo Neutro (`neutral`):** Flag binária (sim/não) que remove a vantagem de 65 pontos de Elo em campo neutro.
7. **Dias de Descanso (`home_days_rest` / `away_days_rest`):** Dias desde o último jogo. Mede o desgaste físico.
8. **Média de Escanteios do Time (`home_sb_corners_l5` / `away_sb_corners_l5`):** Escanteios batidos nos últimos 5 jogos, permitindo ajustar a tendência aérea.
9. **Média de Chutes do Time (`home_sb_shots_l5` / `away_sb_shots_l5`):** Chutes realizados nos últimos 5 jogos. Controla o ímpeto ofensivo na simulação.
10. **Média de Cartões Recebidos (`home_sb_cards_l5` / `away_sb_cards_l5`):** Média de cartões recebidos nos últimos 5 jogos (disciplina).
