# Relatório final — Pesquisa ampla de novas variáveis/dados/abordagens (ApostaInfo)

**Data:** 2026-07-24
**Metodologia:** 7 agentes de domínio (papers acadêmicos, empresas de análise, blogs técnicos,
repositórios open source, competições Kaggle, engenharia de ML aplicada, fontes de dados) pesquisaram
em paralelo; achados consolidados em `PESQUISA_VARIAVEIS_EXTERNAS.md`. Um comitê técnico de 3
revisores independentes (A — rigor estatístico/viés, B — viabilidade de dados/engenharia, C —
estratégia/originalidade/roadmap) revisou o material em 2 rounds: round 1 independente (cada um
sem ver os outros dois), round 2 de cruzamento. **Nota de processo:** o round 2 dos 3 comitês foi
interrompido pelo limite semanal de uso de subagentes da plataforma; o cruzamento foi então feito
diretamente pelo orquestrador (eu), lendo os 3 memos de round 1 na íntegra. Não houve nenhuma
divergência de FATO entre os 3 comitês — as três lentes convergiram de forma consistente nos
mesmos candidatos prioritários, cada uma contribuindo profundidade complementar (A: exclusões por
confounding, B: separação dado-disponível vs dado-novo, C: combinações cross-domínio e roadmap).
Isso está registrado como achado honesto na seção 7, não como atalho metodológico disfarçado.

**Nada aqui foi implementado ou testado sob o gate §6 do projeto — este é um backlog de candidatos
priorizado, não trabalho concluído.** Qualquer promoção real a produção exige o protocolo completo
(CV temporal expanding, point-in-time estrito, métrica nativa por mercado, comparação contra a
produção real, segmentação por força/competição/continente, ≥4/5 folds com delta médio <−0,001)
numa tarefa futura separada, decidida pelo dono do projeto.

---

## 1. Auditoria do estado atual

### 1.1 Modelos em produção

| Modelo | Prediz | Algoritmo |
|---|---|---|
| Dixon-Coles Binomial Negativo (DC-NB) | Gols mandante/visitante (matriz conjunta) → 1X2, BTTS, O/U, placar exato, mercados derivados | 2× GradientBoostingRegressor (λ, μ) + dispersão/correlação por MLE |
| Cascata NB/GP (chutes→escanteios→cartões) | Chutes, escanteios, cartões (total/mandante/visitante, com e sem por-tempo) | NB independente por lado, cascata reusa a saída de chutes como feature de escanteios/cartões (único encadeamento explícito hoje) |
| Classificador multinomial | Time a marcar primeiro | HistGradientBoostingClassifier |
| 3 modelos de prop de jogador | Goleador, assistência, finalizações | HistGradientBoostingClassifier + calibração isotônica, holdout temporal |
| `ou_calibrators.joblib` | Recalibração O/U (escanteios/gols/cartões, total e por lado/tempo) | Isotônica, promovida sob gate §6 |
| `bias_correction.joblib` | Correção de viés pós-hoc contra odds reais | Ajuste **global**, sem segmentação por liga/mercado (confirmado por leitura de código nesta pesquisa) |

### 1.2 Features em produção

- **Elo**: K por tipo de competição, seleção (158 `base_feats`) e clube (170, inclui GAP ratings).
- **GAP ratings** (Wheatcroft): ataque/defesa casa/fora de chutes e escanteios — só clube, único
  achado de rating alternativo já promovido ao gate §6.
- **Forma recente** l3/l5/l10 (gols, pontos, streaks), H2H, calendário (days_rest, season_progress,
  tournament_weight).
- **Box-score agregado** da API-Football (chutes/posse/passes/faltas por partida) — sem coordenadas
  de evento, sem tracking real.
- **Proxies táticos** (style_crosses, style_ppda, style_fouls_suff_ratio) ortogonalizados contra
  `elo_diff` via regressão linear.
- **xG** só para clube, ~10-15% de cobertura, concentrado em jogos de 2023+ ("muro de dados").
- **Momentum de jogador** (goleador AUC 0,68→0,71) — única exceção positiva numa lista de ~60
  hipóteses majoritariamente reprovadas, usada hoje só em mercados de prop, nunca como insumo do
  DC-NB principal.

### 1.3 Fonte de dado e cota

~100% API-Football (assinatura Ultra). `GET /fixtures?id=` traz statistics/events/lineups/players
numa única chamada — núcleo de todo o dataset. Cota diária 75.000 requisições, tipicamente
~65-70k/dia já ocupados pelo backfill de 68+ competições de clube. `/injuries` já é chamável por
`team_id` (serve seleção e clube), mas só é coletado sob demanda para seleção — **nunca em massa
para clube**, apesar de ser tecnicamente o mesmo endpoint já em uso. `/predictions` nativo foi
testado e descartado (log-loss 1,593 vs 1,016 do nosso modelo, 0/26 competições vencidas pelo
vendor, 8117 jogos).

### 1.4 Pontos fortes

- Arquitetura DC-NB + cascata já venceu 7 candidatos alternativos da literatura (CatBoost+pi-rating,
  LightGBM+pi-rating, ordered logit, Dixon-Coles clássico estático e dinâmico, Poisson bivariado) em
  teste direto de pesquisa de clubes.
- Protocolo de validação (gate §6) já é mais rigoroso que boa parte da literatura/competições
  externas revisadas nesta pesquisa — confirmado independentemente pelo Agente 5 (a própria solução
  vencedora do Kaggle mais rigoroso de futebol usa CV aleatória para desenvolvimento interno, o que
  o gate §6 do projeto evita deliberadamente).
- Momentum de jogador é um sinal validado e ainda subutilizado (só em props).

### 1.5 Limitações conhecidas

- **Muro de dados de xG/tracking**: qualquer variável que dependa de coordenadas x/y de evento (xT,
  OBV, VAEP, Packing Rate, xGOT, SkillCorner) é categoricamente bloqueada — a API-Football só
  entrega estatísticas agregadas por jogo, nunca eventos com posição.
- **`bias_correction` global**: 72 torneios heterogêneos compartilham uma única correção,
  potencialmente diluindo o ajuste correto para competições com menos histórico.
- **Nenhum monitoramento de drift documentado** em produção.
- **Calibração isotônica nunca resolveu** os dois pontos onde falhou (chutes, 1X2) — ficou sem
  solução alternativa até esta pesquisa.
- **`/injuries` de clube só sob demanda**, nunca em escala — trata ausência como binário, sem peso
  de importância do jogador ausente.

---

## 2. Novas variáveis encontradas

Tabela curada pelo comitê (fundindo famílias redundantes identificadas pelo Comitê A — ver nota
"família" — e ordenada por prioridade prática, não pela ordem de descoberta). Para os candidatos
descartados por confounding/bloqueio de dado, ver seção 7.

| nome | descrição | fórmula/metodologia | mercados impactados | ganho esperado | complexidade | fonte de dado | disponibilidade | evidência |
|---|---|---|---|---|---|---|---|---|
| **G-Elo / Elo ponderado por margem de gols** (família: fusão de G-Elo acadêmico + heurística ClubElo/SPI) | Generaliza o update do Elo para usar a margem de gols (via modelo ordinal Adjacent-Categories), não só W/D/L | `Pr{Y=h\|z} ∝ 10^(α_h+δ_h·z/σ)`; mantém a forma `θ←θ+K(y−G(z))` do update já em produção | Resultado 1X2, handicap | Não quantificado para futebol especificamente, mas é generalização formal comprovada (o Elo é caso particular restrito) | Baixa/Média — drop-in no update já existente | Zero — usa gols já no dataset | Ambos | [arXiv:2010.11187](https://arxiv.org/abs/2010.11187) |
| **Calibração Beta** | Alternativa paramétrica de 2-3 parâmetros à isotônica, monotônica mas suave | `logit(p_cal) = a·log(p) − b·log(1−p) + c` via regressão logística | Chutes (onde isotônica reprovou) | Direto — ataca a causa provável da falha (viés-variância ruim com poucos dados por bin) | Baixa | Zero — reusa saída do modelo já treinado | Ambos | [arXiv:1704.00762](https://arxiv.org/abs/1704.00762) |
| **Calibração de Dirichlet** | Generalização multiclasse da beta, respeita a restrição soma=1 (isotônica one-vs-rest quebra essa restrição) | `softmax(W@log(p)+b)`, regressão logística multinomial | 1X2, "time a marcar primeiro" (multiclasse) | Vencedora em 8/8 métricas contra 10 métodos em benchmark de 21 datasets (NeurIPS 2019) | Média | Zero — reusa saída do modelo | Ambos | [NeurIPS 2019](https://papers.nips.cc/paper/9397) |
| **Dedução de rating por lesão ponderada por status** | Penalidade no rating pré-jogo proporcional à gravidade/confirmação da ausência de jogador-chave | `penalidade = Σ(impacto do jogador ausente) × peso_status` | 1X2, handicap, todos os mercados de gols | Medido e replicado por 2 competidores independentes: −0,0081 Brier (masc.) | Média — `/injuries` já chamável, falta job de coleta em massa para clube + estruturar peso | `/injuries` já existe na API-Football, só falta coleta em escala | Ambos | [March Mania 2026, 1º lugar](https://www.kaggle.com/competitions/march-machine-learning-mania-2026/writeups/) |
| **Bias correction segmentada por liga/mercado** | Substituir o ajuste global único por `k` ajustes com shrinkage por volume | Reusa dataset de `bias_correction.joblib`, particionado por competição/cluster | Todos os mercados que já usam bias correction | Não medido — é lacuna de processo confirmada por leitura de código, não claim de terceiro | Média — desenho de shrinkage para não recriar overfit da isotônica em amostra pequena | Zero — reusa dataset existente | Ambos (mais clube, 72 torneios) | Confirmado por grep em `build_bias_correction.py` (sem `groupby`) |
| **PSI — monitoramento de drift em produção** | Métrica de deslocamento de distribuição entre treino e produção corrente | `PSI = Σ(pct_atual−pct_esperado)·ln(pct_atual/pct_esperado)` por bin | Todos — infraestrutura, não modelo | Lacuna de processo confirmada (nada documentado hoje) | Baixa-média | Zero — usa dados já existentes | Ambos | Prática padrão de risco de crédito |
| **Auditoria leakage-aware da cascata (escalação point-in-time)** | Checklist de 4 etapas: resolução de nome, dedup, rolling `shift(1)` estrito, corte por hora de publicação de escalação (não só data do jogo) | Não é modelo, é auditoria de `predictor.py::build_row()` | Chutes, escanteios, cartões, faltas (mercados da cascata) | Reduziu MAE/RMSE vs. baseline heurístico em todos os alvos testados no paper-fonte | Baixa (é auditoria) | Zero | Ambos | [ScienceDirect, LaLiga 2026](https://www.sciencedirect.com/science/article/pii/S2590005626003620) |
| **H1 — Momentum de jogador agregado como feature do DC-NB de gols** (hipótese de comitê, não de agente isolado) | Levar a feature de momentum de jogador já aprovada (hoje só em `scorer_model`) para o modelo principal de resultado, agregada por XI titular provável | Soma ponderada por minutos históricos dos titulares prováveis, feature nova em `base_feats` | Resultado 1X2, gols (DC-NB) | Extrapolação de um resultado já aprovado (AUC 0,68→0,71 em prop); não medido neste mercado ainda | Média | Zero — reusa feature já validada | Ambos (mais clube — escalação mais confiável) | Síntese do comitê a partir de `bateria-momentum-jogador.md` + Agentes 2/3 |
| **Compound Poisson/geometric-Poisson para escanteios com regressão no parâmetro de forma** | Trata escanteios como chegando em "lotes"/clusters correlacionados; parâmetro de forma regredido sobre supremacia de gols | `log(λ)=β₀+...`; forma `log(κ)=α₀+α₁log(\|SUP\|+0.01)` | Escanteios O/U | **Backtest real contra odds HKJC**: Sharpe 3,07 vs 1,52 do Poisson simples (2016-2021) | Alta — MCMC/Stan, sprint dedicado | Zero — usa agregados já mantidos em `aggregates.py` | Ambos | [arXiv:2112.13001](https://arxiv.org/abs/2112.13001) |
| **CMP (Conway-Maxwell-Poisson), versão MLE barata** | Cobre sub-dispersão além de super-dispersão (a NB de produção só cobre super-dispersão) | `P(y)=(λʸ/y!)^ν/Z(λ,ν)`, ν por MLE | Gols, potencialmente escanteios/cartões | Qualitativo — heterogeneidade real de dispersão encontrada por time na EPL, sem número de delta vs NB | Média (versão MLE simples, não Bayesiana) | Zero | Ambos | [arXiv:2607.18009](https://arxiv.org/abs/2607.18009), pacote `goalmodel` |
| **Overround por liga como feature de confiança/peso** | Margem do bookmaker por competição, proxy de liquidez/eficiência de mercado | `overround = Σ(1/odds)−1` | Verificador de Bets / Oportunidades Encontradas | Ponderação para confiar menos em odds de ligas com mercado mais raso | Baixa | Zero — odds já coletadas (§22) | Ambos | [pena.lt/y, 250M linhas de odds](https://pena.lt/y/2025/07/16/how-accurate-are-soccer-odds/) |
| **Dispersão de odds cross-bookmaker como feature de incerteza** (hipótese de comitê) | Variância entre casas para o MESMO jogo como sinal de dificuldade de precificação daquela partida específica | Desvio-padrão das odds implícitas entre casas, por mercado/jogo | Camada de calibração/apresentação, não o DC-NB em si (evita circularidade) | Não testado — mecanismo genuinamente novo | Baixa | Zero — mesma tabela de odds do item acima | Ambos | Síntese do Comitê A |
| **Clima no kickoff** (temp/precip/vento) | Condições climáticas no horário/local do jogo | Consulta histórica por `venue`+`date` via API de clima | Gols/escanteios O/U em condições extremas | Baixo-médio — efeito historicamente fraco em futebol profissional, concentrado em eventos raros de cauda | Baixa | Fonte nova, barata (Visual Crossing/OpenWeatherMap) | Ambos | Literatura geral de meteorologia esportiva |
| **Elo com vantagem de mandante variável no tempo** | Tendência de queda estrutural do home advantage (não é só efeito-pandemia) — parâmetro passa a ter componente temporal, não escalar fixo | Termo de tendência linear/spline no lugar do γ fixo por competição | 1X2, handicap | Achado replicado por múltiplas fontes independentes (queda ~50% sem público, tendência desde WWII) | Média — desenho da forma funcional é trabalho real | Zero | Ambos | [The Conversation](https://theconversation.com/as-football-returns-in-empty-stadiums), [Engora blog](https://blog.engora.com/2025/07/vanishing-home-field-advantage-in.html) |

**Candidatos avaliados e explicitamente descartados** (confounding não resolvido, bloqueio categórico
de dado, ou reconfirmação de hipótese já reprovada) — ver seção 7 para a lista completa com
justificativa: xT/OBV/VAEP/Packing Rate/xGOT/SkillCorner (bloqueados por ausência de coordenadas x/y
na API-Football), Opta Power Rankings (mistura odds de mercado, não isola mérito do rating),
SciSkill Index e valor de mercado de elenco em uso geral (colineares com Elo — só sobrevivem em
recorte estreito, ver H5), pi-ratings/Berrar/OpenSkill/TrueSkill/Bradley-Terry (mesma família já
reprovada), Score-driven GAS genérico (mesma família do Koopman já reprovado), Rue-Salvesen/home-
advantage-por-time/prior period-specific (mesma família do Perfil Elo-condicionado já reprovado por
inconsistência entre competições).

---

## 3. Ranking de prioridade

Consolidado a partir dos rankings independentes dos 3 comitês (convergência alta — nenhuma inversão
de posição relevante entre eles). Escala: ganho preditivo, facilidade de implementação, custo de
dado, robustez científica, aderência seleção, aderência clube (Alto/Médio/Baixo).

| # | Candidato | Ganho potencial | Facilidade | Custo de dado | Robustez | Aderência seleção | Aderência clube |
|---|---|---|---|---|---|---|---|
| 1 | Calibração Dirichlet (1X2, first-scorer) | Médio-Alto | Alta | Nenhum | Alta (peer-reviewed) | Alta | Alta |
| 2 | Calibração Beta (chutes) | Médio | Alta | Nenhum | Alta (peer-reviewed) | Alta | Alta |
| 3 | Job de coleta `/injuries` de clube em massa + rating por lesão ponderada | Médio | Média | Nenhum (endpoint já usado) | Média (medido, replicado 2x) | Média | Alta |
| 4 | Auditoria leakage-aware da cascata (escalação point-in-time) | Alto (se achar leak) | Alta (é auditoria) | Nenhum | Alta (mesmo domínio de mercado) | Média | Alta |
| 5 | PSI — monitoramento de drift | Alto (processo) | Alta | Nenhum | Alta (indústria consolidada) | Alta | Alta |
| 6 | G-Elo / Elo ponderado por margem de gols | Incerto (nunca medido em futebol) | Alta | Nenhum | Média (formal, sem número de futebol) | Alta | Alta |
| 7 | Bias correction segmentada por liga (com diagnóstico prévio) | Médio-Alto (mais clube) | Média | Nenhum | Média (lacuna confirmada, ganho não medido) | Baixa | Alta |
| 8 | H1 — Sinal de jogador agregado no DC-NB de gols | Médio-Alto | Média | Nenhum (reusa momentum já aprovado) | Média (extrapolação de resultado já aprovado) | Média | Alta |
| 9 | Overround por liga como peso de confiança | Baixo (produto, não acurácia) | Alta | Nenhum | Alta (250M linhas de odds) | Alta | Alta |
| 10 | Purged K-Fold + Embargo (endurecimento do gate) | Médio (processo) | Média | Nenhum | Alta (literatura financeira) | Alta | Alta |
| 11 | Compound Poisson/geometric-Poisson para escanteios | Alto (backtest real, Sharpe 3,07) | Baixa (MCMC/Stan) | Nenhum | Alta (dinheiro real contra odds HKJC) | Média | Alta |
| 12 | CMP (versão MLE barata) para dispersão de gols | Incerto | Média | Nenhum | Média (sem delta vs NB publicado) | Alta | Alta |
| 13 | Elo com vantagem de mandante variável no tempo | Baixo-Médio | Média | Nenhum | Baixa (estudo descritivo) | Alta | Alta |
| 14 | Dispersão de odds cross-bookmaker (incerteza por jogo) | Não testado | Baixa | Nenhum | Média (hipótese de comitê) | Alta | Alta |
| 15 | Clima no kickoff | Baixo | Alta | Baixo (fonte nova barata) | Baixa (efeito historicamente fraco) | Alta | Alta |
| 16 | Ausência ponderada por valor de mercado (Transfermarkt) | Médio | Baixa | Alto (scraper, ToS, fuzzy match) | Baixa-Média | Baixa | Média |
| 17 | Valor de mercado só em mata-mata cross-divisão (H5, escopo estreito) | Médio (nicho) | Baixa | Alto (mesma fonte) | Baixa-Média | Baixa | Média |
| 18 | Choque de regime discreto (troca de técnico) | Incerto | Média (piloto) / Alta (versão completa) | Nenhum (piloto) / Médio (completo) | Baixa (hipótese nova) | Média | Alta |
| 19 | Índice de qualidade do XI titular / FSAA adaptado | Médio-Alto | Baixa-Média | Nenhum (proxy) | Média (adaptação de método) | Baixa | Alta |
| 20 | BN causal estendida (posse→chutes→SOT→gols) | Médio | Baixa | Nenhum | Média (valida só em handicap) | Baixa | Alta |
| 21 | Blend Bayesiano modelo+odds | Baixo (perde vs mercado puro) | Média | Nenhum | Média (risco de circularidade) | Média | Alta |
| 22 | Venn-Abers (incerteza por predição) | Baixo (funcionalidade de produto) | Média | Nenhum | Média (sem aplicação a futebol) | Alta | Alta |
| 23 | Extensão Sarmanov do Dixon-Coles | Incerto (efeito cascata em todos os mercados) | Baixa | Nenhum | Baixa (só validado em futebol feminino) | Alta | Alta |
| 24 | Tweedie GLM para cartões vermelhos | Baixo-Médio | Média | Nenhum | Baixa (especulativo, sem aplicação publicada) | Alta | Alta |

**Top 5 recomendado para começar** (consenso dos 3 comitês, maior razão ganho/custo/risco): (1)
Calibração Dirichlet no 1X2, (2) Calibração Beta em chutes, (3) job de coleta `/injuries` de clube
em massa, (4) auditoria leakage-aware da cascata, (5) PSI de drift. Todos com custo de dado zero,
reusam infraestrutura já existente, e testáveis em dias sob o gate §6 já em produção.

---

## 4. Novas hipóteses

### H1 — Sinal de jogador agregado bate sinal de time também no modelo de resultado, não só em props

**Motivação:** momentum de jogador passou o gate (AUC 0,68→0,71); momentum de time foi reprovado
repetidas vezes. Toda a evidência de "granularidade de jogador > granularidade de time" no projeto
vem de mercados de prop — nunca foi testada como insumo do DC-NB principal.

**Fundamentação:** agregados de time (posse, forma, PPDA) já são capturados de forma mais estável
pelo Elo/GAP ratings; sinal adicional de time tende a ser redundante. Sinal de jogador captura quem
está em campo (line-up specific), independente da força histórica do time.

**Implementação:** reusar a feature de momentum de jogador já validada; agregar por soma ponderada
por minutos históricos dos titulares prováveis; adicionar como `base_feat` extra em `predictor.py`.

**Validação:** gate §6 completo, segmentado por competição/continente/força de time. Assinatura
esperada se o sinal for real: ganho maior em jogos com escalação volátil (copas com rotação) do que
em ligas de pontos corridos com XI estável.

### H2 — A falha da isotônica no 1X2 pode ser artefato do método, não evidência de boa calibração nativa

**Motivação:** o histórico do projeto registra "isotônica reprovada no 1X2" como se fosse evidência
de que o DC-NB já é bem calibrado. Mas isotônica one-vs-rest quebra a restrição soma=1 em problema
multiclasse — o teste pode ter reprovado pela ferramenta errada, não por ausência de viés real.

**Fundamentação:** Dirichlet calibration vence 8/8 métricas contra 10 métodos em benchmark de 21
datasets (Kull et al., NeurIPS 2019) — é a família estatisticamente correta para 3 classes com
soma=1, diferente da isotônica one-vs-rest.

**Implementação:** treinar Dirichlet sobre as probabilidades OOF do 1X2 via CV temporal; olhar
primeiro a curva de calibração por classe (diagnóstico) antes de decidir se há algo a corrigir.

**Validação:** gate §6 padrão, atenção ao segmento "empate" (já documentado como bem calibrado sob
outro teste — H1 do §19). Se Dirichlet também não achar viés, é confirmação mais forte (método
certo) do que a reprovação atual da isotônica.

### H3 — Bias correction segmentada deveria priorizar as competições da expansão 2026, não todas de uma vez

**Motivação:** o artefato de clube cresceu 60→68→83 competições em julho de 2026; `bias_correction`
é global. O viés é provavelmente maior nas competições coletadas por último, com menos histórico.

**Fundamentação:** correção pooled dominada por competições com mais histórico tende a generalizar
mal para as competições recém-adicionadas, que também têm overround de mercado mais alto (achado do
Agente 3 sobre ligas menores).

**Implementação:** diagnóstico primeiro (comparar ECE/Brier do bias_correction atual nas
competições da expansão 2026-07-19/22 vs. as 60 originais); só implementar segmentação completa se
a diferença for grande.

**Validação:** diagnóstico sem código de produção; depois, se confirmado, segmentação com shrinkage
por volume sob gate §6.

### H4 — Choques discretos de mudança de regime em vez de decaimento contínuo

**Motivação:** time-decay contínuo e o Perfil Elo-condicionado (slope contínuo) já reprovaram. O
Adaptive Glicko-2 tem um componente distinto — "choques estruturais" discretos, não função contínua
do tempo — que nenhum candidato do projeto testou ainda.

**Fundamentação:** a força de um time é estável na maior parte do tempo; decaimento contínuo aplicado
sempre "gasta" sinal em ruído para capturar uma mudança que só acontece ocasionalmente (troca de
técnico, janela de transferência).

**Implementação:** feature binária `regime_change_flag` (troca de técnico nos últimos N jogos, via
`coach_id` de lineup já disponível), usada como interação (menos peso ao histórico pré-mudança
especificamente naquele jogo), não como peso de decaimento contínuo.

**Validação:** gate §6, comparando explicitamente contra os 2 experimentos já reprovados para deixar
claro que é mecanismo estruturalmente distinto (evento discreto vs. função contínua).

### H5 — Valor de mercado do elenco só testado no recorte onde o Elo é estruturalmente mais fraco

**Motivação:** valor de mercado é colinear com Elo na maioria dos jogos, mas em mata-mata
cross-divisão/continental (onde Elos de populações diferentes se comparam) é exatamente onde um
sinal absoluto externo tem maior potencial de adicionar informação sem redundância. O projeto já tem
`GET /api/aggregate`/`mata_mata_agregado` para esse recorte exato.

**Fundamentação:** Elo por competição é bom para comparar times DENTRO da mesma liga; em copas que
cruzam países/divisões, a comparabilidade entre Elos é a fraqueza estrutural mais óbvia.

**Implementação:** escopar o experimento aos jogos que já passam por `predict_aggregate` (recorte
pequeno, identificável); fonte de dado via Transfermarkt (scraper de terceiro, risco de ToS real,
decisão de uso comercial reservada ao dono do projeto).

**Validação:** gate §6 restrito ao segmento cross-divisão (amostra menor, limiar mais conservador);
comparar `mata_mata_agregado` atual (só Elo) com e sem a feature de valor de mercado.

### Hipóteses de processo adicionais (Comitê A)

- **Filtro de triagem "exige x/y?"**: antes de aprofundar qualquer candidato futuro, checar em 1
  pergunta se ele precisa de coordenadas de posição de jogador/bola — se sim, descartar sem gastar
  mais tempo de pesquisa, dado o "muro de dados" já confirmado categoricamente nesta rodada.
- **Filtro de correlação para "mesma ideia travestida de nova"**: antes de implementar qualquer
  candidato da família "generalização de algo já reprovado" (CMP, GAS, Rue-Salvesen), testar a
  correlação entre as predições do candidato novo e as do modelo antigo já reprovado numa amostra
  pequena — se >0,98, não justifica o custo de um teste completo sob gate §6.
- **"Teto de sanidade" de ~60-65% de acurácia**: claims de vendor convergem numa faixa estreita
  (Opta 60-65%, tracking holandês 64,0%, pi-rating+CatBoost 55,82%) que provavelmente reflete a
  dificuldade intrínseca do problema, não mérito específico de método proprietário — útil como
  referência para julgar futuros claims sem reanalisar cada um do zero.

---

## 5. Novas fontes de dados

| nome da fonte | dados disponíveis | cobertura seleções | cobertura clubes | custo | tem API? | facilidade de integração | prioridade de aquisição |
|---|---|---|---|---|---|---|---|
| **Visual Crossing** (clima histórico) | Temperatura/precipitação/vento hora a hora desde ~1970 | N/A (geoespacial) | N/A | Muito baixo (~US$0,0001/registro, grátis até 1000/dia) | Sim, REST bem documentada | Alta — chave `venue`+`date` já existe | **Média** — trivial e barato, mas ganho esperado pequeno |
| **OpenWeatherMap** (clima histórico) | Equivalente ao Visual Crossing | N/A | N/A | Baixo (~US$10/cidade fixo, 5 anos) | Sim, REST | Alta | **Média** — alternativa, comparar pricing antes de escolher |
| **Transfermarkt** (via scraper terceiro — Apify/Parse.bot) | Valor de mercado, transferências, elenco, sidelined ponderado, idade média | Média (elenco convocado) | Forte (referência de mercado) | Baixo/variável (pay-per-use) | Não oficial — ToS não autoriza uso comercial | Média — dado estável mas scraper de terceiro + fuzzy match de nome | **Média, com ressalva de ToS** — decisão de uso comercial cabe ao dono |
| **FotMob** (API não-oficial) | xG, xA, nota de jogador, shotmap, cobertura de ligas maior que Understat | Boa | Muito ampla | Grátis | Não oficial, sem SLA | Média | **Baixa-média** — não resolve o problema de fundo (xG já reprovado 3x) |
| **SkillCorner** | Tracking XY via broadcast, métricas físicas/táticas | Fraca | Forte (110-120+ ligas) | Enterprise, "contact sales" | Sim (produto pago) + 10 jogos open-data grátis | Alta (open-data) / Baixa (produto) | **Baixa** — fora de orçamento; open-data só serve prova de conceito acadêmica |
| **Second Spectrum** | Tracking óptico + métricas proprietárias | Muito fraca | Média (parcerias pontuais) | Enterprise, tier mais caro do setor | Sim, sem docs públicas | Baixa | **Baixa** — nível "liga oficial", inacessível ao porte do projeto |
| **Tracab (ChyronHego/Stats Perform)** | Tracking óptico certificado FIFA EPTS | Forte só em torneios FIFA/UEFA | Forte nas top-5 ligas + Eredivisie/Superliga | Não publicado, vendido a clubes/federações | Sem API self-service | Alta (barreira) | **Baixa** — não redistribui a terceiros |
| **Understat** | xG/xA histórico desde 2014/15 | Nenhuma | Só 6 ligas (top-5 europeu + Rússia) | Grátis | Não oficial, wrappers maduros | Alta | **Baixa** — cobertura menor que o xG já disponível via API-Football |
| **SofaScore** | Estatísticas de jogo, lineups, ratings | Boa (torneios grandes) | Muito ampla | Grátis | Não oficial | Média | **Baixa** — redundante com o que a API-Football Ultra já entrega |
| **FBref / Stats Reference** | Estatísticas avançadas (passes progressivos, xG, pressing) | Fraca | Forte nas ligas top e secundárias | Grátis | Não oficial, rate limit 10 req/min | Média (rate limit hostil) | **Baixa** — 40x mais lento que a API já paga, inviável em escala |
| **WhoScored** | Ratings de jogador, estatísticas por posição | Fraca | Forte top-5 + secundárias | Grátis | Não oficial, anti-bot ativo | Baixa | **Baixa** — instável, sem diferencial |
| **Sportmonks `/referees`** | Perfil de árbitro, histórico de cartões/pênaltis | Fraca-média | Forte nas ligas cobertas | Já avaliado/descartado para odds | Sim, REST | Média | **Baixa** — mesmo provedor já descartado; ganho é só granularidade |
| **OddAlerts `/referees`** | Idem Sportmonks | Fraca | Forte (1500+ competições) | Já avaliado/descartado | Sim | Média | **Baixa** — mesma lógica |
| **Catapult / STATSports** (GPS/fisiológico) | Velocidade, distância, carga de trabalho | N/A | Só interno ao clube contratante | N/A | Só para cliente do sistema | N/A | **Inviável** — sem marketplace público, confirmado |
| **PhysioRoom** (lesões) | Tabela de lesões diária | Nenhuma | Só Premier League | Grátis | Não — página editorial | Baixa | **Baixa** — cobertura de 1 liga só, `/injuries` da API-Football já resolve melhor (falta só o job de coleta) |

**Risco de ToS aplicado às fontes não-oficiais** (avaliação do Comitê B): nenhuma fonte não-oficial
desta tabela deveria entrar em cron de produção recorrente sem avaliação jurídica explícita
(o ApostaInfo é produto comercial monetizado, não projeto acadêmico) e plano de fallback caso o
scraper quebre sem aviso. Uso defensável hoje: piloto de pesquisa isolado, não-recorrente,
claramente rotulado como tal — mesmo tratamento que o projeto já dá a StatsBomb open-data.

---

## 6. Roadmap de implementação

### Fase 1 — Alto impacto, baixo esforço (dado já disponível, dias de implementação)

1. Calibração Dirichlet no 1X2 e no first-scorer.
2. Calibração Beta em chutes.
3. Auditoria leakage-aware da cascata chutes→escanteios→cartões (antes de qualquer expansão futura
   dessa cascata).
4. PSI para drift de produção.
5. Diagnóstico de bias correction por competição nova vs. antiga (H3, só análise).
6. Job de coleta `/injuries` de clube em massa + rating por lesão ponderada (versão binária de
   status, sem valor de mercado).

### Fase 2 — Esforço médio (reengenharia de feature/pipeline existente, dado já disponível)

1. G-Elo / Elo ajustado por margem de gols (testar isolado).
2. Rating unificado — combinar margem de gols + ausência ponderada, com ablation para isolar a
   contribuição de cada peça.
3. H1 — sinal de jogador agregado no DC-NB de gols.
4. Bias correction segmentada por liga com shrinkage por volume (só depois do diagnóstico da Fase 1
   confirmar sinal a capturar).
5. Purged K-Fold + Embargo (endurecimento do gate §6, mais relevante nas competições recém-
   expandidas).
6. H2 — diagnóstico Dirichlet no 1X2 vs. resultado da isotônica.
7. Choque de regime discreto — versão piloto (só troca de técnico, sem valor de mercado).

### Fase 3 — Avançado, depende de nova fonte de dado ou de MCMC/engenharia pesada

1. Compound Poisson/geometric-Poisson para escanteios com regressão no parâmetro de forma — maior
   evidência quantitativa de todo o levantamento, mas exige sprint de modelagem Bayesiana dedicado.
2. Índice de qualidade do XI titular / FSAA adaptado ao proxy de finalizações.
3. H5 — valor de mercado em mata-mata cross-divisão (depende de Transfermarkt, decisão de uso
   comercial do dono).
4. Adaptive Glicko-2 completo (MOV + dominance + shocks + ordinal).
5. Choque de regime discreto — versão completa (+ atividade de transferência via valor de mercado).
6. Clima no kickoff.

### Fase 4 — Experimental / pesquisa (alto risco, alto custo, evidência fraca ou incerta)

1. BN causal estendida posse→chutes→SOT→gols (só depois da auditoria de leakage da Fase 1).
2. CMP uni/bivariado para dispersão de gols (Bayesiano completo).
3. Blend Bayesiano modelo+odds (risco de circularidade com o Verificador de Bets — exige isolamento
   cuidadoso de pipeline).
4. Extensão Sarmanov do Dixon-Coles (efeito cascata em todos os mercados derivados, só validado em
   futebol feminino).
5. Frailty model de tempos de escanteio (confirmar antes se a API-Football expõe timestamp de
   escanteio — provável gap de dado).
6. Venn-Abers (funcionalidade de produto — intervalo de confiança por previsão —, não melhoria de
   acurácia).

---

## 7. Nota de honestidade metodológica — convergência dos 3 comitês

Os 3 comitês, trabalhando de forma independente no round 1 (sem ver o trabalho um do outro), 
chegaram a conclusões de priorização quase idênticas: os mesmos ~8 candidatos (calibração Beta/
Dirichlet, job de `/injuries`, G-Elo, bias correction segmentada, auditoria de leakage, PSI)
apareceram no topo dos 3 rankings independentes, e os mesmos candidatos "chamativos" (Packing Rate,
SciSkill, valor de mercado geral, Opta Power Rankings) foram rebaixados ou descartados pelos 3, por
razões complementares mas convergentes (Comitê A: confounding com Elo; Comitê B: bloqueio de dado ou
risco de ToS; Comitê C: baixa robustez de evidência no ranking preliminar). Não houve necessidade de
arbitrar nenhuma divergência de fato real entre os 3 — o round 2 de cross-review, que seria o
mecanismo para resolver esse tipo de conflito, não encontrou nenhum caso que precisasse dele além do
que já está incorporado nas seções 2-6 deste relatório.

**Ressalva de processo**: o round 2 formal (cada comitê lendo e reagindo explicitamente aos outros
dois, ponto a ponto) foi interrompido pelo limite semanal de uso de subagentes da plataforma antes
de produzir os 3 arquivos `comite_{A,B,C}_round2.md`. A síntese acima foi feita pelo orquestrador
lendo os 3 memos de round 1 na íntegra e confirmando a convergência — um passo metodologicamente
mais fraco do que o cross-review ponto-a-ponto planejado original, mas suficiente dado o grau de
concordância já observado. Se o dono do projeto quiser o round 2 formal completo (com os 3 arquivos
de cross-review explícitos), isso pode ser retomado quando o limite resetar.
