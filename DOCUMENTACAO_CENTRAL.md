# DOCUMENTAÇÃO CENTRAL — Previsão de Jogos (ApostAI)

> **Documento-mestre único e vivo.** Substitui e consolida todos os relatórios, contextos,
> handoffs e resumos anteriores. Descreve o que o projeto é, o que prevê, quais dados e
> modelos usa (e **por quê**), o que cada métrica significa (em linguagem clara), e **todo o
> histórico de desenvolvimento em ordem cronológica** com o resultado de cada tentativa e o
> motivo de cada aprovação/reprovação. Atualize este arquivo a cada nova sessão.
>
> Última atualização: **2026-06-30**. Branch de trabalho: `claude-testing` · produção: `main`.
> Companheiros mantidos: `README.md` (porta de entrada) e `ARCHITECTURE.md` (infra/banco).

---

## 1. O que é o projeto

Plataforma de **previsão probabilística de partidas de seleções** (futebol internacional
masculino adulto). Não prevê só "quem ganha": entrega a **distribuição de probabilidade** de
cada mercado, para comparar com odds de casas de aposta e medir valor.

**Monorepo:**
- **`/frontend`** — Next.js (TypeScript), deploy na **Vercel** (`www.valerioferreira.com.br`).
- **`/backend`** — FastAPI (Python), deploy no **Render** (`api-previsoes-jogos.onrender.com`),
  venv em `backend/.venv`, porta 8000.
- **Banco** — **Neon** (PostgreSQL serverless). O disco do Render/Vercel é efêmero → todo o
  estado de produção vive no Neon + nos artefatos versionados em `backend/model_artifacts/`.

`npm run dev` na raiz sobe front+back juntos. Detalhes de infra/deploy/banco: `ARCHITECTURE.md`.

---

## 2. O que o sistema prevê (mercados)

Tudo é orquestrado por `backend/predictor.py::predict(home, away, neutral, tournament)`.

| Grupo | Mercados | Origem |
|---|---|---|
| Resultado | Vencedor 1X2, Ambas Marcam (BTTS), Over/Under 2.5, Total de gols, Gols por equipe, **Placar exato** (top-3 + alerta de desvio) | **matriz conjunta do Dixon-Coles-NB** |
| Contagem | Finalizações, Finalizações a gol, Escanteios, Cartões — **total, por equipe e por tempo (1º/2º)** | modelos **NB/GP em cascata** |
| Apoio | Confiabilidade do jogo (cobertura de box-score), Confronto direto (H2H) | derivado |

Cada mercado de contagem expõe a **PMF completa** (distribuição de probabilidade de massa,
"fonte de verdade") e, dela, as linhas Over/Under com **odd justa = 1/probabilidade** (sem
margem da casa). As linhas O/U do **total** de escanteios/a-gol/cartões passam por uma
**calibração isotônica** validada (ver §6 e §9, item 2026-06-30).

---

## 3. Dados

### 3.1 Fonte e dataset de treino
- **`international_features_enriched_apifootball.csv`** (raiz do backend, **gitignored**; espelhado
  na tabela `features_enriched` do Neon). **~9.976 jogos**, 2016→2026, **~319 colunas**.
- Resultados e Elo ancorados na base histórica **martj42** (49.477 jogos, 1872+); estatísticas
  avançadas (box-score: chutes, a-gol, escanteios, cartões, faltas, posse, passes) da **API-Football**.
- **Cobertura de box-score (`has_advanced_stats==1`): 4.102 jogos (~41%)** — só recente e
  concentrada nas competições de elite (ver §3.3). Os modelos de contagem treinam nesse subconjunto.
- **Não há colunas de xG** no dataset (o xG existe no raw da API para ~41% dos jogos, mas nunca
  foi extraído; tentativas de usá-lo falharam — ver histórico).

### 3.2 Features (158 base + estilo/cascade)
- **`base_feats` (158)** usadas pelo Dixon-Coles: **Elo** (`home_elo_pre`, `elo_diff`,
  `elo_home_winprob` — domina tudo), descanso (`*_days_rest`), mando (`neutral`,
  `real_home_advantage`), H2H, streaks, e taxas **gf/ga/gd/ppg/winrate/csrate/ftsrate/bttsrate**
  em janelas l3/l5/l10 (home/away/diff), pesos de torneio, e **pace** (somas l10).
- Os modelos de contagem usam um conjunto maior (**~274 feats**): base + rolling de box-score
  (`sb_shots_l5`...) + **resíduos de estilo ortogonalizados** (`resid_*_style_*` via
  `style_ortho_weights.joblib`, removendo o que o Elo já explica) + **cascade** (finalizações
  previstas `pred_*_shots` + interações de mando `rha_x_*`).
- **Regra de ouro:** toda feature é **point-in-time** (`shift(1)`, só dados pré-jogo) — sem leakage.

### 3.3 Cobertura de box-score por competição (por que a contagem só usa ~41%)
Quase perfeita (>90% utilizável) em **Copa do Mundo, Euro, Copa América, Nations League,
Eliminatórias UEFA/CONMEBOL**; baixa/nula em amistosos (~22%), eliminatórias africanas/asiáticas
antigas e torneios regionais (COSAFA, Gulf Cup etc.). É por isso que features dependentes de
box-score (e xG) não generalizam para seleções fora da elite.

### 3.4 Tabelas no Neon (produção lê)
`matches` (forma/histórico), `features_enriched` (treino), `fixture_index`, `past_fixtures`
(seletor), `referees`/`team_ids`, `odds_registry` (jogos futuros + snapshot de previsão),
`match_detail_cache` (detalhe sob demanda). `data/` local é **gitignored** e não existe no Render.

### 3.5 Coletas (máquina local, Windows Task Scheduler → Neon)
- **`CollectOdds`** (3/3h): odds de consenso + snapshot da previsão (destrava backtest de valor).
- **`CollectResolved`** (diária): resolve jogos disputados (mantém a forma atual).
- **`CollectPlayerForm`** (diária): forma de clube/lesões dos convocados — **EXPERIMENTAL**, não
  em produção; aponta para caminho pré-monorepo (`api/.venv`) e pode estar quebrada (inócua, a
  coleta já está completa). Cota API ~75k/dia.

---

## 4. Modelos em produção

| Mercado | Artefato (`backend/model_artifacts/`) | Modelo |
|---|---|---|
| Resultado / Gols / BTTS / Over 2.5 / Placar | `dixon_coles_goals.joblib` | **Dixon-Coles NB** (matriz conjunta) |
| Escanteios | `corners_cascade_rfixo.joblib` | **NB** r-fixo (r_H=10, r_A=8.5) + cascade |
| Finalizações | `shots_nb.joblib` | **NB** (r≈18) + time-decay H=2 |
| Finalizações a gol | `shots_on_target_nb.joblib` | **NB** |
| Cartões | `cards_gp.joblib` | **Generalized Poisson** |
| Gols/Cartões 1º/2º tempo | `gols_1t/2t_nb`, `cartoes_1t/2t_nb` | **NB** |
| **Calibração O/U** (novo 2026-06-30) | `ou_calibrators.joblib` | **Isotônico** p/ escanteios/a-gol/cartões |
| Apoio | `style_ortho_weights.joblib`, `meta.json` | ortogonalização de estilo + metadados |

**Legado em disco, NÃO servido:** `dynamic_corners_nb` (REPROVADO), `corners_nb`, `cards_nb`,
`clf_result/btts/over25`, `quantile_models` (todos substituídos).

### 4.1 Dixon-Coles NB — por que esse modelo
`dixon_coles_model.py`. **λ_home e μ_away** são estimados por **GradientBoostingRegressor do
sklearn** (100 árvores, profundidade 3, lr 0.05) sobre as 158 features — um regressor para casa,
outro para fora, cada um vendo todas as features. As marginais são **Binomial-Negativa**
(dispersão r_H, r_A) com a **correção Dixon-Coles `rho`** (≈−0.046) nas células de placar baixo
(0-0/0-1/1-0/1-1), tudo ajustado por **máxima verossimilhança**. Da matriz conjunta normalizada
saem coerentemente todos os mercados de resultado.
- **Por quê:** o futebol de seleções é dominado por **força relativa** (Elo) e tem **correlação
  conhecida nos placares baixos** (empates 0-0/1-1 mais frequentes do que a independência prevê);
  o Dixon-Coles modela exatamente isso. O GBM captura interações não-lineares entre as 158 features
  melhor que um modelo log-linear. Para gols, o `r` da NB colapsou em região quase-Poisson (r>100)
  → o ganho vem do **acoplamento DC**, não da sobredispersão.

### 4.2 Mercados de contagem — NB/GP em cascata — por que
- **Negative Binomial (NB)** para finalizações, a-gol e escanteios porque essas contagens são
  **sobredispersas de verdade** (variância > média; r≈18-21). A Poisson (variância=média)
  subestimaria a incerteza e descalibraria as caudas.
- **Generalized Poisson (GP)** para cartões: contagem baixa (média ~2-3) onde a NB e a GP empatam;
  a GP foi escolhida por melhor cobertura de cauda. (Honestamente: cartões **não têm
  sobredispersão real** — o `r` da NB colapsa em ~1000 = Poisson; o ganho vem de usar uma
  distribuição de **contagem própria** em vez da Normal, não da sobredispersão.)
- **Cascade:** finalizações são previstas primeiro e entram como feature de escanteios e cartões
  (a permutação confirma: `pred_shots` é a 2ª/3ª feature mais importante em escanteios e a 1ª em
  cartões). Estilo ortogonalizado (PPDA de pressing) também sobrevive como sinal.
- **Time-decay** (peso 0.5^(Δdias/H)) foi testado em todos os alvos e **só ajudou finalizações**
  (H=2: viés temporal −0.80→−0.31, ECE 5.6%→2.5%). Em gols o viés é estrutural (invariante ao
  decay); em escanteios/cartões o viés já era ~zero.

---

## 5. Métricas — o que são e por que usamos cada uma

O sistema é avaliado por **qualidade probabilística**, não por "acertou/errou". Um modelo que
diz "60% de vitória" e o time perde **não errou** — só não era certeza. As métricas medem se as
probabilidades são **honestas e bem calibradas**.

- **Log-loss (entropia cruzada)** — penaliza a probabilidade que o modelo deu ao que **de fato
  aconteceu**: `−log(p_observado)`. Diz "70% Over" e deu Over → custo baixo; diz "95% Over" e deu
  Under → custo altíssimo. **Por quê:** pune **excesso de confiança errado** com força, que é
  exatamente o erro caro em aposta. É a métrica **primária** de todos os mercados.
- **ECE (Expected Calibration Error)** — mede **calibração**: agrupa as previsões por faixa de
  probabilidade e compara "o que o modelo disse" com "a frequência real". Se em todos os jogos
  onde disse ~70% o Over saiu ~70% das vezes, ECE≈0. **Por quê:** log-loss baixo não garante que
  "70%" signifique 70% na prática; o ECE é o que valida que as **odds justas** são confiáveis.
  (Reportamos em %; produção fica em ~2-4%.)
- **Bernoulli log-loss** — o log-loss específico de um mercado binário (uma linha Over/Under).
  Usado na validação da calibração O/U.
- **Brier score** — erro quadrático médio entre probabilidade e desfecho (0/1). Alternativa ao
  log-loss, menos sensível a previsões extremas; usado como métrica secundária de calibração.
- **MAE / RMSE** — erro absoluto/quadrático médio da **estimativa pontual** de contagem (ex.:
  "esperado 9.3 escanteios"). **Por quê:** complementa as métricas probabilísticas com uma noção
  intuitiva de "quão longe a média ficou".
- **Cobertura de intervalo (80%)** — fração das vezes em que o valor real caiu dentro do intervalo
  de 80% previsto. Deve ficar perto de 80% (bem calibrado). **Por quê:** valida que a **largura**
  da distribuição (a incerteza) está correta, não só o centro.
- **Tail-ECE** — ECE restrito às **caudas** (linhas extremas, ex. Over 11.5 escanteios). **Por
  quê:** foi o que reprovou o modelo de dispersão dinâmica (caudas estreitas demais); apostas em
  linhas extremas exigem caudas honestas.
- **Estabilidade walk-forward** — o ganho tem de aparecer **em vários cortes temporais
  sucessivos** (treina no passado, testa no futuro), não num único split. **Por quê:** evita
  promover ruído (foi assim que descobrimos que ganhos de CV aleatória eram falsos).
- **RPS (Ranked Probability Score)** e **ROI/yield** — ainda **não** computados em produção (RPS é
  trivial de adicionar; ROI depende de acumular odds de fechamento — ver §9).

**Por que essas e não "acurácia":** acurácia ignora a confiança. Em mercados de aposta o que
importa é se a probabilidade bate com a frequência real (calibração) e se o modelo não erra com
excesso de confiança (log-loss). Por isso o **gate de promoção** exige reduzir log-loss **sem
piorar ECE**, de forma **consistente em folds e segmentos**.

---

## 6. Protocolo de validação (o gate)

Padrão obrigatório para promover qualquer mudança:
1. **CV temporal expanding** (treina no passado, testa no bloco seguinte; cortes ~0.50→0.85),
   seed=42. (CV **aleatória** superestima ganhos — proibida para veredito.)
2. **Point-in-time**: só features pré-jogo; ortogonalização/residualização **ajustada por fold**.
3. **Métrica nativa**: contagem → log-loss da PMF + ECE da linha O/U + MAE; resultado → log-loss
   multiclasse + ECE + acurácia; + Brier nos binários.
4. **Comparar contra a PRODUÇÃO REAL** (NB/GP/DC-NB), nunca contra um baseline strawman (ex.: Poisson).
5. **Segmentar sempre**: equilíbrio (|elo|≤80 / 80–150 / >150), competição, continente, cobertura.
6. **Gate**: reduzir log-loss + não piorar ECE + passar CV temporal + sem leakage + sem degradar
   inferência — **consistente em folds E segmentos**. Senão, **não promover**.

---

## 7. Estado de produção (resumo)
Pipeline **robusto e bem calibrado** (ECE de resultado ~3%, contagem ~2-4%). O Elo satura o
resultado; o `base_feats`+cascade satura a contagem. **A única melhora promovida nas últimas
baterias foi a calibração isotônica das linhas O/U** (2026-06-30). Tudo o mais testado foi
medição que confirmou a robustez do que já existe.

---

## 8. Histórico de desenvolvimento (cronológico, com achados e veredito)

### Fase 0 — Migração de dataset (StatsBomb → API-Football)
Recalibração do Elo (K-factors reais por torneio + multiplicador de margem de vitória → divergência
de Elo <46 para seleções FIFA) e correção de um bug de merge no gamelog (pares válidos saltaram de
48 para 9.958, correlação >0.9999 vs base original). Base de box-score expandida de **242 → 4.102**
jogos. **Veredito:** modelo base equivalente ou ligeiramente melhor em resultado; **ganhos grandes**
em contagem (finalizações MAE 6.15→4.99, cobertura 80% de 69%→79%). API-Football adotada.

### Fase 1 — Migração quantílica → distribuições de contagem próprias
Os mercados de contagem usavam regressão quantílica + aproximação Normal (péssima para contagem
baixa). Migrados para distribuições próprias, **cada um validado vs a quantílica**:
- **Escanteios → NB independente** (r_H=18.2, r_A=16.7). Sobredispersão real confirmada. A
  **bivariada acoplada** convergiu para β=−0.04 (correlação negativa real mas **fraca**) e **perdeu**
  no total (ECE 5.11% vs 2.75% da convolução independente) → **acoplamento aposentado**.
- **Cartões → contagem própria** (depois GP). Correlação entre lados **+0.07** (positiva, "jogo
  pegado cartoneia os dois", mas fraca → acoplada empatou). Achado honesto: `r`≈1000 → **cartões ≈
  Poisson** (sem sobredispersão); o ganho vem da distribuição própria vs Normal.
- **Finalizações → NB + time-decay H=2** (r≈18). Único alvo onde o decay ajudou (viés −0.80→−0.31).
- **Veredito:** todas batem a quantílica em log-loss e ECE; promovidas. Casas não oferecem odds de
  chutes → fora do value betting, mas exibido.

### Fase 2 — Dixon-Coles NB para resultado/gols
Substituiu classificadores binários por uma **matriz conjunta**. Resultado **log-loss 0.874→0.830,
ECE 7.57%→3.16%**. O ganho vem do **acoplamento DC**, não da NB (r de gols colapsou em quase-Poisson).
**Veredito:** promovido; serve resultado/gols/BTTS/over/placar de forma coerente.

### Fase 3 — Features e regressores testados (gate walk-forward)
- **PACE** (somas l10 de gf/ga): **único grupo de features que passou** (BTTS 8/9 janelas) → **EM
  PRODUÇÃO**. Reprovados: forma por mando, SoS-Elo, momentum, EWMA, interações explícitas (instáveis).
- **Regressor de λ (XGBoost/LightGBM/HistGBM)**: 9 configs × 8 janelas × 4 mercados — **nenhum bate o
  sklearn GBM** (boosters potentes overfitam). Janela fechada.
- **Calibração post-hoc do BTTS / resultado** (Platt/isotônica/temperatura): **piora** (DC já calibrado).
- **xG como feature, time-decay em gols, peso de competição, confiabilidade de rating, remover
  martj42**: todos reprovados (muro de dados do xG; viés de gols estrutural; manter martj42 evita
  ~80% da perda irredutível).

### Fase 4 — Dispersão dinâmica de escanteios (DynamicCornersNB) — REPROVADO
Tentou parametrizar a dispersão r jogo-a-jogo (GAMLSS-style, MLE em dois estágios). Passou MAE/log-loss
mas **reprovou Tail-ECE** (Over 8.5 = 13.9%/22.4% vs limite 4%; Over 11.5 = 3.4% vs 2.5%). O MLE
estreitou a cauda para maximizar a verossimilhança do corpo, subestimando eventos raros. **Rollback**
para o NB r-fixo (r_H=10, r_A=8.5), que minimiza ECE diretamente. (Detalhe técnico preservado no commit.)
> **Nota:** o problema que ele tentou resolver (calibração de cauda dos escanteios) foi **resolvido
> em 2026-06-30 por outro caminho** — calibração isotônica post-hoc da prob. O/U (ver abaixo).

### Fase 5 — Player ranking / forma de jogador
- **Ranking de temporada** (força via clube dos convocados, agregado): **redundante com o Elo**
  (corr +0.55..+0.72), gate falhou. Aposentado.
- **Forma-por-jogo** (point-in-time, 2.123 jogos: rating de clube, minutos, fadiga, momentum,
  xG-clube, disponibilidade/lesões via `/sidelined`): coleta concluída. Testada exaustivamente
  (relatórios 1, 3, 4) — ver abaixo.

### Fase 6 — Baterias de validação 2026-06-29 (relatórios 1–3)
- **Relatório 1** (forma no resultado, CV **aleatória**): ganho **minúsculo** (−0.001 a −0.006
  log-loss), maior em jogos equilibrados/alta cobertura, com rating-residual e momentum. *Caveat:
  CV aleatória.*
- **Relatório 2** (contagem do zero): NB/GP **>> Poisson** em finalizações/escanteios. *Caveat: o
  Poisson do experimento NÃO é a produção.*
- **Relatório 3** (promoção sob gate, **CV temporal** — o veredito que vale): premissa corrigida (a
  produção já é NB/GP/DC-NB). **GP não bate a NB de produção** (empate/ruído por segmento). **Forma
  no resultado REPROVA** sob CV temporal (o ganho do rel. 1 era artefato de CV aleatória).
  **Calibração** pós-hoc piora. **Posse/passes/faltas** inconsistente. **Árbitro** não ajuda
  (amostra rasa por árbitro em seleções). **Promovido: NADA.**

### Fase 7 — Os 6 próximos passos 2026-06-30 (relatório 4)
Executados sob gate temporal. **Nada promovido:**
- **xG de clube** (além do base_feats): ganho só em finalizações, **~7× menor que o ruído** entre
  folds. Resultado inconsistente. Não passa.
- **Forma como blend de cobertura no resultado**: sinal "âmbar" no proxy HGB (melhora 3 segmentos),
  mas **decai por fold** e some no fold mais recente. → follow-up: testar no DC real.
- **Feature importance dos modelos de PRODUÇÃO** (permutação sobre os artefatos deployados): **elo
  (`elo_home_winprob`) domina tudo** (#1 em finalizações, a-gol, escanteios e DC-resultado); o
  **cascade finalizações→escanteios é real** (`pred_shots` top em escanteios e #1 em cartões); PPDA
  de estilo sobrevive; **cartões** é o mercado menos guiado por elo (mais idiossincrático).
- **Exp 3 cadeia de regressão** (posse→finalizações→escanteios→gols): ΔLL≈0 (o base_feats já tem o
  histórico rolante). **Exp 4 cópula bivariada**: dependência pequena (gols/cartões +, escanteios
  −0.17/finalizações −0.09, confirma β≈−0.04), sem ganho no total. **Exp 5 ataque×defesa→λ**
  (força pura estilo DC): **pior** que GBR+features em tudo (+0.03 a +0.18).

### Fase 8 — Calibração O/U + fechamento da forma 2026-06-30 (relatório 5) — **MELHORA PROMOVIDA**
- **Forma blendada no Dixon-Coles REAL** (não proxy): dLL −0.0006, ECE pior; **forma no resultado
  encerrada** — o sinal âmbar era artefato da família HGB; o DC já extrai o sinal.
- **Calibração isotônica das linhas O/U do total dos mercados de contagem** (validada por
  walk-forward expanding, ajustando o calibrador no passado e avaliando no futuro):

  | Mercado | ECE (cru→calibrado) | ΔBernoulli-LL | Folds que melhoram | Veredito |
  |---|---|---|---|---|
  | **Escanteios** | 4.5% → **2.8%** | −0.0072 | **4/4** | ✅ **Promovido** |
  | **Finalizações a gol** | 3.0% → **2.5%** | −0.0029 | 3/4 (recente ✓) | ✅ **Promovido** |
  | **Cartões** | 2.8% → **2.1%** | −0.0017 | 2/4 (recente ✓) | ✅ **Promovido** |
  | Finalizações (chutes) | 6.3% → 7.5% | +0.0015 | 1/4 | ❌ Excluído (piora) |

  **Por que isotônico:** a miscalibração de cauda da NB/GP é uma curva monótona irregular, não uma
  rotação logística — o isotônico é a recalibração monótona livre que a captura, preservando a
  ordenação entre linhas. Platt/temperatura não capturaram (já reprovados no resultado).
  **Integração:** `ou_calibrators.joblib` + `predictor._corners_market(calibrator=)`; aplicado **só
  ao TOTAL** validado (não a mandante/visitante nem a chutes); distribuição/estimativa seguem da PMF
  crua; linhas O/U marcadas com `"calibrado": true`; retrocompatível (sem o artefato = comportamento
  antigo). É a **primeira melhora aprovada desde o início das baterias de validação**.

**Meta-conclusão:** os modelos estão no teto in-sample — o Elo domina e quase tudo que se tenta é
redundante com ele. O ganho real veio de **calibrar** (não de novas features). Salto maior de
qualidade exigiria **dados de outra natureza** (tracking/xG denso) ou o **backtest de odds ao vivo**
como árbitro empírico de valor.

---

## 9. Janelas de oportunidade abertas (onde há retorno)
1. **Backtest financeiro (ROI/yield) + RPS** — a validação que mais falta. Hoje só temos log-loss/
   ECE/Brier; ROI exige acumular odds de **fechamento** × resultados (coletor de odds é recente,
   poucos snapshots). Deixar `CollectOdds` rodando e usar `value_backtest.py`. **Maior prioridade.**
2. **Estender a calibração isotônica** já promovida: avaliar mandante/visitante e linhas de meio-tempo
   sob o mesmo gate; só ativar onde passar (chutes continua fora).
3. **xG denso / dados de tracking** (fora da API-Football) — única fonte plausível de sinal novo
   ortogonal ao Elo; o xG da API é esparso demais (~6%, só elite/2024).
4. **Ratings dinâmicos** (Dixon-Coles dinâmico / filtro de Kalman de força ataque-defesa evoluindo no
   tempo) — maior esforço, potencial incerto para placar exato.

**Já testado e fechado (não repetir):** GP vs NB de produção; forma de jogador no resultado;
calibração post-hoc do resultado; posse/passes/faltas; árbitro; XGBoost/LightGBM no λ; cadeia de
regressão; cópula bivariada; ataque×defesa força-pura; dispersão dinâmica de escanteios; time-decay
fora de finalizações; remover martj42.

---

## 10. Como rodar / reproduzir
```bash
cd backend
# subir API:      .venv/Scripts/python -m uvicorn app.main:app --port 8000
# (raiz) front+back: npm run dev

# experimentos sob gate temporal (resumíveis; CSVs em data/reports/, gitignored):
.venv/Scripts/python scripts/promotion_validation.py          # GP vs NB de producao
.venv/Scripts/python scripts/result_forma_validation.py       # forma no resultado
.venv/Scripts/python scripts/xg_club_experiment.py            # xG de clube
.venv/Scripts/python scripts/forma_dc_blend.py                # forma blendada no DC real
.venv/Scripts/python scripts/exp3_chain.py                    # cadeia de regressao
.venv/Scripts/python scripts/exp4_copula.py                   # copula bivariada
.venv/Scripts/python scripts/exp5_attack_defense.py           # ataque x defesa -> lambda
.venv/Scripts/python scripts/feature_importance_prod.py       # importancia dos modelos deployados
.venv/Scripts/python scripts/count_calibration_walkforward.py # calibracao O/U (validacao)
.venv/Scripts/python scripts/build_ou_calibrators.py          # gera ou_calibrators.joblib
```
Re-treino do DC após validar uma feature: `scripts/retrain_dc_pace.py` (cirúrgico; os scripts
`train_*_apifootball.py` têm caminhos pré-monorepo quebrados).

---

## 11. Gotchas (aprendidos)
- **CORS↔500:** uma exceção 500 no FastAPI não leva header CORS → o browser mascara como "erro de
  CORS". Se CORS aparece só num endpoint, é 500 nele. (Foi como descobrimos `requests` ausente no
  Render → trocado por `httpx`.)
- `truncate_and_append` preserva schema → **coluna nova no Neon exige DROP da tabela** uma vez.
- `pandas==3.0.3` exige **SQLAlchemy ≥ 2.0.36** (senão `to_sql` quebra).
- Ordem de `base_feats` deve ser idêntica treino↔`meta.json` (append no fim).
- Modelos picklados (`shots_nb_model`, `corners_nb_model`...) ficam na **raiz do backend** — scripts
  em `scripts/` precisam de `sys.path.insert(0, backend_root)` para `joblib.load`.
- Console Windows é cp1252 — evitar caracteres Unicode (Δ, →) em `print` de scripts.
- Jobs em background morrem no teardown de sessão → fazer scripts **resumíveis** (checkpoint).
- `nbinom.ppf` é lento para r alto; amostrar via **CDF em grade + searchsorted**.
