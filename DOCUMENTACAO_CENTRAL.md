# DOCUMENTAÇÃO CENTRAL — Previsão de Jogos (ApostAI)

> **Documento-mestre único e vivo.** Substitui e consolida todos os relatórios, contextos,
> handoffs e resumos anteriores. Descreve o que o projeto é, o que prevê, quais dados e
> modelos usa (e **por quê**), o que cada métrica significa (em linguagem clara), e **todo o
> histórico de desenvolvimento em ordem cronológica** com o resultado de cada tentativa e o
> motivo de cada aprovação/reprovação. Atualize este arquivo a cada nova sessão.
>
> Última atualização: **2026-07-18**. Branch de trabalho: `main` (pesquisa de clubes da branch
> `clubs`, §13, incorporada por merge) · produção: `main`.
> Companheiros mantidos: `README.md` (porta de entrada), `ARCHITECTURE.md` (infra/banco/e-mail)
> e `ESTADO_ATUAL_E_PROXIMOS_PASSOS.md` (handoff vivo — **leia primeiro ao retomar**).

---

## 1. O que é o projeto

Plataforma de **previsão probabilística de partidas de seleções** (futebol internacional
masculino adulto). Não prevê só "quem ganha": entrega a **distribuição de probabilidade** de
cada mercado, para comparar com odds de casas de aposta e medir valor.

**Monorepo:**
- **`/frontend`** — Next.js (TypeScript), deploy na **Vercel** (domínio de produção **`apostainfo.com.br`**).
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
| Contagem | Finalizações, Finalizações a gol, Escanteios, Cartões, **Impedimentos** — **total, por equipe e por tempo (1º/2º)** | modelos **NB/GP em cascata** |
| Derivados | Dupla chance, Empate anula (DNB), Handicap (linhas .5), Clean sheet, Vitória sem sofrer, Gols par/ímpar, Faixas de gols | **cortes exatos da matriz DC / PMFs de gols** |
| Apoio | Confiabilidade do jogo (cobertura de box-score), Confronto direto (H2H) | derivado |

> **Impedimentos** (`offsides_nb.joblib`, NB, exposto **cru** — a calibração isotônica não passou o gate) e os **mercados derivados** (transformações exatas de distribuições já validadas, sem gate próprio) foram adicionados em 2026-07-06 na fase de expansão de mercados.

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
2. ~~**Estender a calibração isotônica**~~ — **FEITO 2026-07-06.** Avaliados mandante/visitante e
   meio-tempo sob o mesmo gate walk-forward. **Promovidos (4/4 folds cada):** escanteios-mandante,
   gols_1t-total, gols_2t-total, cartões_1t (total+mandante+visitante), cartões_2t (total+mandante+
   visitante) — maior ganho em cartões de meio-tempo (ex.: cartões_1t-visitante ECE 6,8%→2,7%).
   Reprovados (BLL piora/inconsistente): escanteios-visitante, a-gol e finalizações por lado, gols
   de meio-tempo por lado. `ou_calibrators.joblib` agora tem 12 chaves `<mercado>_<home|away|total>`;
   `predictor._half(prefix)` aplica por lado. Chutes segue fora.
3. **xG denso / dados de tracking** (fora da API-Football) — única fonte plausível de sinal novo
   ortogonal ao Elo; o xG da API é esparso demais (~6%, só elite/2024).
4. **Ratings dinâmicos** (Dixon-Coles dinâmico / filtro de Kalman de força ataque-defesa evoluindo no
   tempo) — maior esforço, potencial incerto para placar exato.

**Já testado e fechado (não repetir):** GP vs NB de produção; forma de jogador no resultado;
calibração post-hoc do resultado; posse/passes/faltas; árbitro; XGBoost/LightGBM no λ; cadeia de
regressão; cópula bivariada; ataque×defesa força-pura; dispersão dinâmica de escanteios; time-decay
fora de finalizações; remover martj42; **prop "jogador a levar cartão"** (2026-07-08,
`scripts/test_player_cards.py`): bem calibrado (ECE 0,6%) e bate a taxa-base 4/4, mas **AUC 0,62**
(base 0,59) — muito abaixo do padrão do goleador (~0,74). Cartão de jogador é idiossincrático
(árbitro desconhecido pré-jogo + faltas aleatórias). **Não promovido** — não vale abrir o mercado.

> **Padrão dos props de jogador (2026-07-09):** ações **OFENSIVAS** (gols, finalizações) são
> **previsíveis** (AUC 0,74–0,77) porque refletem o papel no ataque, que é estável → **construídas
> (goleador + finalizações)**. Ações **defensivas/disciplinares** (cartões AUC 0,62; **faltas AUC
> 0,58** — `scripts/test_player_fouls.py`; assistência 0,64) são **aleatórias jogo-a-jogo → não
> passam**. O espaço de props de jogador está **exaurido**: só valem os ofensivos, já em produção.

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

---

## 12. Camada de Usuários / Monetização (2026-07)

Além do motor de previsão, o produto ganhou uma **camada completa de usuários, créditos,
apostas promocionais e administração**, construída na branch `feat/monetizacao` (mergeada na
`main`). O motor de previsão e seus modelos **não mudaram** (só ganharam a calibração O/U já
descrita e a odd mínima 1.00 na exibição).

### 12.1 O que existe
Backend **modular por domínio** (`backend/app/domains/*`), ORM 2.0 + **Alembic** (só tabelas
`app_*`, isoladas do pipeline de dados), **36 tabelas** já criadas no Neon (23 originais + 13 da
monetização de conversão, §12.7). Fluxo completo:
```
cadastro→OTP→senha→login  →  compra de créditos  →  análise (consome/reserva 1 crédito)
   →  "Monte sua Aposta" (odd ≤2,00, auto ~2,00, imutável)  →  liquidação pós-jogo
      (vence: consome o crédito · perde/anula: estorna)  —  Painel Admin gerindo tudo
```
- **Auth:** argon2, JWT de acesso + refresh rotativo, **OTP por e-mail real (ZeptoMail/Zoho)**,
  CPF (dígitos verificadores) + telefone, rate limiting, lockout, auditoria.
- **Carteira:** ledger de créditos (saldo só via lançamento, idempotência), disponível/reservado.
- **Pagamentos:** gateway abstrato — **Mercado Pago (Checkout Pro) implementado** (branch
  `monetization`, §12.7), mock segue disponível para dev; webhooks idempotentes com verificação de
  assinatura HMAC. 1 crédito = R$1,00. Cupons de desconto/bônus e comissão de afiliado aplicados no
  checkout, independentes entre si.
- **Análise:** grava **snapshot imutável** + versão do algoritmo/dados; independente consome 1
  crédito, partida futura reserva 1.
- **Aposta ("Monte sua Aposta"):** combina mercados da análise (O/U em colunas Acima/Abaixo),
  odd combinada **≤ 2,00**, **auto-seleção ~2,00** se o usuário não escolher, imutável.
- **Liquidação:** worker `scripts/settle_bets.py` / `POST /api/cron/settle-bets` — pós-jogo via
  API-Football, consome (venceu) ou estorna (perdeu/indeterminável) — promoção "Só Paga se Acertar".
- **Admin (backend + UI):** usuários (bloquear, creditar), financeiro, promoções, **cupons,
  pacotes, afiliados, banners, configurações, suporte** (§12.7), documentos legais versionados,
  **auditoria completa**.
- **Afiliados, campanhas, analytics, notificações, suporte** (§12.7): domínios novos da
  monetização de conversão.
- **Frontend:** página única **Análise** (`/`) com config → gerar (crédito) → previsão completa →
  **Construção da Aposta** (Monte sua Aposta + Explorador de Linha + Value Betting/De-Vig);
  `/carteira` (redesenhada, §12.7), `/perfil`, `/admin`, `/afiliado` (portal), `/documentos/[type]`,
  **`/como-funciona`** (doc interativo). Persistência da análise no `PredictionContext` (não some
  ao navegar). Auth no `AuthContext`.

### 12.2 Estado dos adapters (importante)
- **E-mail OTP:** adapter **real implementado** (2026-07-08, commit `e517740`) —
  `EMAIL_PROVIDER` = `mock` | `zeptomail` | `smtp`. **ZeptoMail** (transacional da Zoho) é o
  provedor de produção; SMTP do Zoho Mail é o fallback. Em dev o default segue `mock` (OTP no
  console). Desenho completo em **`ARCHITECTURE.md` §6**.
  - Provider desconhecido ou credencial ausente **levanta erro** em vez de cair em mock.
  - Falha de envio → **HTTP 502 + rollback** (nenhum usuário órfão); ver §6.2 do `ARCHITECTURE.md`.
  - `APP_ENV=production` faz o backend **recusar o boot** com config de e-mail/JWT inválida.
  - Validar antes de expor a usuários: `cd backend && python -m scripts.send_test_email voce@dominio.com`.
- **Gateway de pagamento:** adapter **Mercado Pago implementado** (`payments/gateways/
  mercadopago.py`, branch `monetization`) — falta só `MP_ACCESS_TOKEN`/`MP_WEBHOOK_SECRET` reais e
  `PAYMENT_PROVIDER=mercadopago` para sair do mock. `POST /payments/mock/confirm/{id}` continua
  disponível, mas só funciona quando `PAYMENT_PROVIDER=mock` (guarda de segurança). Ver §12.7.
- **Nota fiscal:** adapter **noop** (`payments/invoicing.py`) — marca `invoice_status="pending"`
  sem emitir nada; trocar por NFE.io/Focus NFe quando decidido com o contador. **Emissão automática
  mantida para toda venda paga** (best-effort); desde 2026-07-13 a **exibição ao cliente é sob
  demanda** (`invoice_requested_at` + botão "Solicitar nota fiscal" na Carteira) — ver §12.8.

### 12.3 Onde está a documentação
- Desenho/arquitetura da camada: **`docs/ARQUITETURA_MONETIZACAO.md`**.
- Infra/deploy/env: **`ARCHITECTURE.md` §5**.
- **E-mail transacional (Zoho/ZeptoMail):** **`ARCHITECTURE.md` §6** — adapters, o porquê do 502
  com rollback, validação de boot, env vars e scripts de verificação.
- Estado atual + próximos passos (handoff vivo): **`ESTADO_ATUAL_E_PROXIMOS_PASSOS.md`** (raiz).

### 12.4 Integração com a Zoho (2026-07-08)
Decidido: **Zoho entra como cliente de e-mail, não como repositório de dados.** O ledger de
créditos (`app_credit_transactions`) depende de transação multi-registro e de `idempotency_key`
com unicidade atômica — garantias que uma API REST de CRM/Creator não oferece; movê-lo para lá
abriria caminho para gasto duplicado de crédito. O Postgres/Neon segue como system of record
transacional.

Envio de OTP: implementado (commit `e517740`), verificado contra um ZeptoMail simulado e
**confirmado em produção em 2026-07-08** — cadastro real concluído no site com o código chegando
por e-mail. Recebimento de e-mail: **não implementado**, decisão pendente (caixa no Zoho Mail é
configuração; leitura programática exigiria IMAP ou Zoho Mail API com OAuth2).

### 12.5 Sessão 2026-07-08 (parte 2) — UX da Análise + regras de crédito/aposta
Produção agora em **`apostainfo.com.br`**; cadastro por e-mail (ZeptoMail) **funcional**.

- **Bônus de boas-vindas:** toda conta nova nasce com **8 créditos grátis** — lançamento `bonus`
  no ledger na ativação (`auth/service.py::set_password`), idempotente por conta
  (`welcome-bonus:<user_id>`). Verificado no `verify_signup_flow`.
- **Persistência da análise (bug corrigido):** o `PredictionContext` agora persiste em
  `localStorage` (`apostai:prediction:v1`) — a análise sobrevive a **reload cheio**, não só à
  navegação client-side. Antes um F5/remontagem zerava a análise e forçava gasto de outro crédito.
- **Aposta — seleções interdependentes bloqueadas:** `bets/markets.py::base_market()` +
  `resolve_selections`/`auto_select` recusam duas seleções do **mesmo mercado-base** (ex.: Menos
  de 1,5 + Menos de 2,5 gols; duas linhas de escanteios/cartões), como as casas. Guarda no backend
  (autoritativa) + no `BetBuilder` (um por mercado-base no toggle).
- **"Jogador a levar cartão":** testado sob o gate (`scripts/test_player_cards.py`) e **reprovado**
  (AUC 0,62; ver §9). Mercado não aberto.
- **Redesign da página de Análise (frontend):** mercados secundários com **colapso individual**
  (título sempre visível); **"Jogador a Marcar" movido para dentro dos secundários**; cards de
  mercado com **só o nome da seleção, centralizado**; **Handicaps** com texto explicativo novo +
  cabeçalhos de coluna; **"Configuração do Confronto" recolhe** ao escolher a partida, com
  "Alterar Equipes" no cabeçalho flutuante; **FUNÇÕES AVANÇADAS acima do MONTE SUA APOSTA**;
  **últimos 5 jogos em linhas** num bloco (Resumo do Confronto Direto à esquerda, equipes
  empilhadas à direita, mesma largura/altura).

### 12.6 Sessão 2026-07-09 — props de finalizações, cópula, Série A
Duas melhorias VALIDADAS foram promovidas, e a coleta de seleções saturou.

- **Mercado "Jogador a finalizar" (PROMOVIDO):** modelo de finalizações do jogador
  (`scripts/build_shots_prop_model.py` → `model_artifacts/shots_prop_model.joblib`): P(≥0,5/1,5/2,5
  finalizações | joga), calibrado. Validação temporal (linha ≥2): **AUC 0,773 (base 0,758), ECE
  1,06%, 4/4 folds** — no padrão do goleador. Serving em `app/services/shots_prop_service.py`;
  `get_scorers` anexa `finalizar` a cada jogador. Frontend: card **"Jogador"** com colunas
  **MARCAR | FINALIZAR (0,5/1,5/2,5)** separadas. Rebuild diário no `prefetch_wc.cmd`.
- **Cópula gaussiana na odd combinada (PROMOVIDO — EXP7/13/14):** `bets/markets.py::combined_odd`
  aplica a cópula às seleções ofensivas correlacionadas (gols/finalizações/a-gol/escanteios) —
  overs correlacionados têm odd combinada MENOR (mais justa/conservadora); demais mercados por
  independência. Σ = correlações residuais validadas, encolhidas. Ex.: over gols + over
  finalizações 3,60→3,20; over fin + over a-gol 3,61→2,71.
- **Fator Árbitro no modelo de cartões de EQUIPE (REPROVADO):** `scripts/exp15_referee_cards.py` —
  `ref_strictness` como feature dá dNLL +0,007 (3/7 folds), inconsistente. Cartão idiossincrático.
- **Coleta de seleções SATUROU:** o prefetch `--all-nations` parou por "tudo coberto" (todas as
  ~230 seleções, histórico 2010+). Sobra ~70k/75k de cota ociosa/dia. Por isso, conforme o foco,
  **começou a coleta do Campeonato Brasileiro Série A** (próxima adição) em tabela SEPARADA
  `serie_a_detail_cache` (`scripts/prefetch_serie_a.py`, anexado ao cron), sem contaminar os
  modelos de seleção.

### 12.7 Sessão 2026-07-11 — Monetização de conversão completa (7 fases), branch `monetization`

Objetivo: transformar a plataforma numa venda de créditos pronta para produção, com foco em
conversão (estilo e-commerce). Todas as 7 fases foram implementadas **reaproveitando** a
arquitetura existente (wallet ledger, `payment_orders`, `AdminAuditLog`) e testadas ponta a ponta
contra o Neon real — não é código não-verificado. Confirmado antes de implementar: o modelo é **só
consumo** (créditos gastos em análises, sem saque de dinheiro), o que evita a barreira de outorga
de apostas de quota fixa (Lei 14.790/2023) — a plataforma é ferramenta de análise paga por crédito,
não uma casa de apostas licenciada.

**Fase 1 — Gateway Mercado Pago real:** `payments/gateways/mercadopago.py` implementa o mesmo
`Protocol` do `MockGateway` (Checkout Pro — redirect, evita escopo de PCI compliance). Webhook
(`POST /payments/webhook/mercadopago`) valida assinatura HMAC (`x-signature`) contra
`MP_WEBHOOK_SECRET`; sem ela, a notificação é rejeitada. `confirm_mock` (usado só em dev) já era
gated por `payment_provider == "mock"` — nenhuma mudança necessária ali, mas o frontend foi
corrigido para só chamá-lo em modo mock; com gateway real, redireciona para o `init_point` do
Checkout Pro e faz polling do saldo ao voltar (`?status=success|pending|failure`).

**Fase 2 — Cupons + Carteira redesenhada:** `Coupon` (`app_coupons`) ganhou campos tipados
(`discount_type: percentage|fixed|bonus_credits`, `discount_value`, `bonus_credits`,
`min_purchase_brl`, `package_id`, `valid_from/valid_to`). Novo `promotions/service.py`:
`validate_coupon()` (preview, não incrementa uso) + `mark_redeemed()` (só quando o pagamento
confirma). `PaymentOrder` ganhou `coupon_id`. Carteira (`/carteira`) reorganizada: banner
promocional → pacotes com selos (`featured_badge`: mais_vendido/melhor_oferta/oferta_limitada) e
% de economia → campo de cupom → resumo de saldo → histórico. `CreditPackage` ganhou
`featured_badge`/`sort_order`.

**Fase 3 — Analytics:** domínio novo `analytics/` — tabela `app_events` (signup, login,
checkout_started, coupon_applied, credit_purchase, payment_failed, analysis_started/finished, etc.)
instrumentada inline nos services existentes (`auth`, `payments`, `analysis`), sem reescrever esses
fluxos. `GET /admin/analytics/dashboard` agrega faturamento hoje/mês/ano, ticket médio, receita por
pacote, créditos vendidos/promocionais/usados, funil de conversão, usuários ativos/pagantes — via
queries SQL diretas (padrão de `aggregates.py`), sem pipeline novo.

**Fase 4 — Afiliados + Portal + Campanhas:** domínio novo `affiliates/` — `Affiliate` (código,
comissão % ou fixa), `AffiliateAttribution` (clique/cadastro, janela de dias configurável via
`app_platform_settings`, chave `affiliate_attribution_days`), `AffiliateCommission` (calculada só
quando o pagamento confirma, hook em `_credit_if_paid`). **Cupom e afiliado são independentes**:
`PaymentOrder.coupon_id` (benefício ao usuário) e `affiliate_attribution_id` (comissão ao
influenciador) coexistem sem se afetar — um pedido pode ter os dois, um só, ou nenhum. Portal
próprio em `/afiliado` (link exclusivo, cliques, cadastros, compradores, faturamento, comissão
devida/paga). Domínio novo `campaigns/` — `Campaign` (banner+pacotes+cupons+afiliados+prioridade,
entidade guarda-chuva para não espalhar configuração de promoção entre módulos) + scaffold de A/B
testing (`Experiment`/`ExperimentVariant`, `assign_variant()` determinístico por hash de
`user_id`+`experiment_key` — mesmo usuário sempre cai na mesma variante).

**Fase 5 — Painel admin expandido:** `frontend/src/app/admin/page.tsx` ganhou 6 abas novas
(Dashboard, Cupons, Pacotes, Afiliados, Banners, Configurações), além das 4 que já existiam
(Usuários, Financeiro, Promoções, Auditoria). Endpoints admin novos delegam para os services dos
domínios novos, sem duplicar regra de negócio (`app/domains/admin/service.py`).

**Fase 6 — Histórico, PIX pendente, notificações, suporte:** `GET /wallet/transactions` ganhou
filtros (`type`/`status`/`since`/`until`). `PaymentOrder.raw_payload` agora persiste o checkout
(init_point/QR) na criação do pedido — antes só era gravado na confirmação, o que impedia
recuperar um PIX pendente; `GET /payments/orders/pending` alimenta o banner "Continuar pagamento"
na Carteira, `GET /payments/orders` alimenta "Minhas compras". Domínios novos `notifications/`
(`app_notifications`, disparada automaticamente em `payment_approved`) e `support/`
(`app_support_tickets`, `POST /support/tickets` + CRUD admin).

**Fase 7 — Nota fiscal, recomendação, A/B, UX:** `payments/invoicing.py` — `NoopInvoiceProvider`
roda após todo pagamento confirmado (best-effort, nunca bloqueia a liberação do crédito), marca
`invoice_status="pending"`; trocar por adapter real (NFE.io/Focus NFe/Asaas) é troca de classe, sem
mexer no fluxo de pagamento. `recommend_package()` em `payments/service.py` — heurística (não-ML):
consumo médio dos últimos 90 dias → pacote mais próximo; sem histórico, sugere o de maior % de
bônus. `GET /campaigns/experiments/{key}/variant` expõe `assign_variant()` para o frontend.

**Migrations aplicadas no Neon** (nesta ordem): `7a1f3c9e2b40` (cupons/pacotes/pedidos),
`9c2e5a7b1d33` (`app_events`), `3f7d9b2c4e11` (afiliados+campanhas, 9 tabelas),
`5e8a1f4c7d22` (notificações+suporte). Total: **+13 tabelas `app_*`** (23→36).

**O que falta para vender de verdade** — não é código, são decisões/credenciais do dono:
credenciais reais do Mercado Pago, deploy + migração em produção, revisão jurídica dos
documentos legais (ainda são templates), decisão do emissor de nota fiscal com o contador. Detalhe
completo em `ESTADO_ATUAL_E_PROXIMOS_PASSOS.md` §2.1.

### 12.8 Sessão 2026-07-13 — merge da `monetization` na `main` + nota fiscal sob demanda

**Merge:** a branch `monetization` e a `main` compartilhavam o mesmo merge-base — a branch era
literalmente `main` + os 3 commits da §12.7 (mais o throttle de coleta `13a6954`). Fast-forward
puro, sem conflitos, com push para `origin/main`. A partir daqui, tudo descrito em §12.7 está na
`main` — só falta **deploy** (Render/Vercel) e rodar `alembic upgrade head` em produção.

**Nota fiscal sob demanda:** o dono pediu para o cliente só ver/receber a nota quando pedir
explicitamente, em vez de expor automaticamente para toda compra. Decisão de arquitetura adotada
(mais segura do ponto de vista fiscal): a emissão em si **continua automática** em
`_credit_if_paid` (best-effort, via `issue_invoice`) — o documento fiscal existe para 100% das
vendas, evitando faturamento sem nota. O que passou a ser sob demanda é só a **exposição ao
cliente**: nova coluna `app_payment_orders.invoice_requested_at` (migração `b4d6e1f8a9c2`), novo
`payments/service.py::request_invoice()` (idempotente — marca o pedido do cliente e tenta emitir
de novo se ainda não `issued`), rota `POST /payments/orders/{id}/request-invoice`, e botão
"Solicitar nota fiscal" na Carteira (`carteira/page.tsx`) que só aparece para pedidos pagos sem
`invoice_requested_at`.

Por quê essa decisão e não emissão 100% sob demanda: no Brasil, a obrigação de emitir NFS-e por
venda de serviço normalmente **independe** de o cliente pedir uma cópia — a prefeitura em geral
exige o documento para toda venda concluída, para fins de ISS/declaração de faturamento. "Só
emitir se o cliente pedir" arriscaria configurar faturamento sem nota fiscal para o resto das
vendas. Um texto foi preparado e enviado ao contador do dono para confirmar isso especificamente
para o município/CNAE dele — se ele confirmar que dá para declarar por outra via, a mudança para
emissão 100% sob demanda é trivial (só mover a chamada de `issue_invoice()` de `_credit_if_paid`
para dentro do `request_invoice()`).

**Fora de escopo (deliberado):** escolha do emissor real (NFE.io vs Focus NFe) — aguardando
resposta do contador sobre CNAE/Fator R/regime tributário (sócio único, sem funcionários CLT,
pró-labore conta para o Fator R). `NoopInvoiceProvider` segue em uso.

### 12.9 Sessão 2026-07-16 — Mercado Pago real + nota fiscal automática (NFE.io)

O dono decidiu o emissor (**NFE.io**) e já tem todos os dados fiscais. Código implementado e
testado (sem gastar dinheiro/nota real); falta só o runbook manual do dono (credenciais/painéis)
e `alembic upgrade head` em produção.

**Mercado Pago:** nenhuma mudança de código no gateway (já estava pronto). Único código novo:
`startup.py::_payment_problems()` — guarda de boot fatal em produção se `PAYMENT_PROVIDER=
mercadopago` e faltar `MP_ACCESS_TOKEN`/`MP_PUBLIC_KEY`/`MP_WEBHOOK_SECRET` (mesmo padrão do
e-mail). Runbook do dono: Render → env vars de produção (painel MP → Developers → Credenciais de
produção) + configurar o webhook no painel MP apontando para
`/payments/webhook/mercadopago` → copiar o segredo de assinatura para `MP_WEBHOOK_SECRET`.

**Nota fiscal (NFE.io):** construído do zero (não existia adapter nenhum):
- `payments/invoicing.py` — `InvoiceProvider` expandido (`customer_name`/`customer_cpf`/
  `competency_date`/`description` no `issue()`; novo `check_status()` para polling, já que a
  emissão da NFE.io é **assíncrona**: o POST devolve `pending` com um id, o status final
  (`issued`/`failed`) só existe segundos/minutos depois). `get_invoice_provider()` ramifica por
  `INVOICE_PROVIDER` (`nfeio` | `noop`), mesmo formato do `get_gateway()`.
- `payments/invoicing_nfeio.py` (novo) — adapter REST espelhando `gateways/mercadopago.py`
  (httpx, Basic Auth com a API Key, tabela de status). **Nomes exatos de campo não confirmados
  contra o Swagger real da NFE.io** (escrito a partir da doc pública) — conferir na primeira
  chamada real antes de apontar para a empresa/API key de produção; não afeta o resto do desenho.
- Migração `f7c1b2e9d4a3` (down_revision `e1f2a3b4c5d6`) — `app_payment_orders` ganha
  `invoice_provider_id` (id no provedor, chave de idempotência/polling) e `invoice_number`
  (número do município, só após `issued`).
- `request_invoice()` agora reconsulta (`check_status()`) em vez de reemitir quando já existe
  `invoice_provider_id` — nunca duplica a nota do mesmo pedido.
- Polling: `scripts/invoice_poll.py` + `POST /api/cron/poll-invoices` (mesmo formato do
  `settle_bets.py`/`cron_settle_bets`), já que não dá para confiar só num webhook da NFE.io de
  imediato — itera pedidos `invoice_status=pending` com `invoice_provider_id` setado.
- Guarda de boot (`startup.py::_invoice_problems()`): fatal em produção se `INVOICE_PROVIDER=
  nfeio` e faltar `NFEIO_API_TOKEN`/`NFEIO_COMPANY_ID`/dados fiscais da empresa. **`noop` em
  produção não é fatal** (diferente de e-mail/pagamento) — só `logger.warning`, porque não emitir
  nota real não deveria bloquear o lançamento das vendas.
- Dados fiscais da empresa (CNPJ, razão social, endereço, inscrição municipal, CNAE, código de
  serviço municipal, regime tributário) viram env vars em `config.py` (não `PlatformSetting`) —
  são dados legais raramente alterados e precisam estar disponíveis no boot para a guarda fatal,
  mesmo padrão do `EMAIL_FROM`.

**Testes novos** (mesmo padrão do `verify_signup_flow.py` — servidor HTTP local fake, sem rede
real): `scripts/verify_startup_config.py` (7 cenários da validação de boot, cobrindo os dois
guardas novos) e `scripts/verify_invoice_flow.py` (checkout mock → paga → nota `pending` → poll
→ `issued`, caminho de erro do provedor, e não-duplicação do `request_invoice()`) — os dois
passam 100%. `verify_signup_flow.py` também rodado de novo como regressão.

**Runbook do dono (fora de código):**
1. Painel NFE.io (`app.nfe.io`): cadastrar/confirmar a empresa com os dados fiscais já prontos;
   subir o certificado digital A1 (só pelo painel, não por API); copiar Company ID + API Key.
2. Render → env vars: `PAYMENT_PROVIDER=mercadopago` + credenciais MP; `INVOICE_PROVIDER=nfeio` +
   `NFEIO_API_TOKEN`/`NFEIO_COMPANY_ID` + os `COMPANY_*` (ver `backend/.env.example`, seção nova).
3. Redeploy; conferir no log `[config] OK — ... payment_provider=mercadopago
   invoice_provider=nfeio` ou o `ConfigError` listando o que falta.
4. `alembic upgrade head` em produção (pendente desde a sessão anterior + a migração desta).
5. Cron novo: `POST /api/cron/poll-invoices?token=$CRON_TOKEN` a cada 15-30 min (mesma cadência
   do `settle-bets`).

---

## 13. Pesquisa de Modelos para Clubes (2026-07-15, branch `clubs`)

Com a coleta de seleções saturada, a coleta de **clubes** (13 competições, Brasil→Europa→América
do Sul, 2010→2026) chegou a **54.072 jogos**. Isso abriu uma pesquisa dedicada — **duas linhas
paralelas, sob o mesmo protocolo único** (5 folds temporais expanding, seed 42; métricas
log-loss/RPS/Brier/ECE/tail-ECE/cobertura80) — para responder duas perguntas: *(1) a arquitetura
atual de seleções continua a melhor quando treinada com muito mais dados? (2) o conhecimento de
clubes melhora as previsões de seleções?* Diário completo, literatura revisada e todos os números
em **`backend/docs/PESQUISA_CLUBES.md`**; relatório consolidado automático em
**`backend/docs/RELATORIO_FINAL_PESQUISA_CLUBES.md`**. Infra reprodutível: **§7 do
`ARCHITECTURE.md`**.

### 13.1 Linha A — arquitetura atual retreinada em clubes
Mesma classe `DixonColesNBRegressor` (GBM→λ/μ + acoplamento DC + NB), sem mudança estrutural,
treinada nas mesmas 158 `base_feats`. **Venceu tudo**: bateu os 7 candidatos da Linha B (Fase 1),
a bateria avançada (Fase 6) e o tuning de hiperparâmetros (Fase 2.5, 18 configs × 5 folds)
confirmou que a config de produção (100 árvores, prof.3, lr=0.05) já é a **melhor do grid**
(log-loss 0,9938) — 5-9× mais dados de clubes não deslocou o ponto ótimo de complexidade.
Cascata de contagem (finalizações/a-gol/escanteios/cartões) replicada com sucesso sobre 35.208
jogos com box-score (8,6× mais que seleções), cobertura de intervalo 80% honesta em todos os
mercados (83,9%-88,2%).

**9 hipóteses reprovadas/inconclusivas em seleções, revisitadas com a base maior**: 8 continuam
reprovadas/inconclusivas (time-decay, momentum, XGBoost/LightGBM p/ λ, calibração pós-hoc,
árbitro, perfil Elo-condicionado, xG-feature — prejudicado por baixa cobertura histórica —, GP≈NB
em escanteios). **1 achado novo**: o blend DC+HistGBM no mercado de **BTTS passou a valer**
(4/5 folds, era só marginal em seleções) — candidato a investigar no pipeline de seleções (fora
do escopo desta pesquisa).

**Transferência clubes→seleções (Fase 3): NÃO ajudou.** Zero-shot (só clubes) piora bastante
(0/5 folds); treino combinado (pooled) é um empate estatístico (delta≈0); hiperparâmetros já são
os mesmos. **Sem exceção de push** — nada bateu a produção real de seleções sob o gate §6.

### 13.2 Linha B — pesquisa aberta (sem viés da arquitetura atual)
Revisão de literatura (Soccer Prediction Challenges 2017/2023, Bunker/Yeung/Fujii 2024,
Koopman-Lit): confirma que **GBM sobre ratings dinâmicos (CatBoost+pi-ratings) é o SOTA** em
datasets só-de-gols — implementado e testado, mas **perdeu** para a arquitetura de produção
mesmo após sweep extensivo de hiperparâmetros (melhor config 0,9970 vs 0,9938 do DC-NB).
Também testados e reprovados: Dixon-Coles clássico (estático e com time-decay), Poisson
bivariado Karlis-Ntzoufras, ratings GAP (Wheatcroft) plugados direto como λ de NB (empata com a
cascata GBM, não bate), **state-space score-driven** (GAS, na linha de Koopman-Lit — único
modelo da literatura com lucro comprovado contra odds; 0/5 folds aqui), **stacking/ensemble**
(quase empate) e **MLP tabular** (torch CPU; confirma a literatura — DL não bate GBM em futebol).

**Engenharia de atributos própria de clubes** (congestão de calendário, altitude+viagem,
mata-mata ida/volta, rotação de elenco, xG over/under-performance, GAP ratings, importância da
partida via tabela corrente simulada): só **GAP ratings passou isolado** (5/5 folds, delta
-0,0022 — pequeno mas consistente); os demais deram resultado misto ou nulo.

### 13.3 Backtest de valor (Fase 8) — achado operacional
`odds_registry` tinha **ZERO cobertura de clubes** (só Copa do Mundo) — o backtest de ROI real
de clubes é hoje impossível. Corrigido nesta sessão: `backend/scripts/collect_club_odds_forward.py`
(novo) passa a coletar odds futuras das ligas de clubes. Backtest de papel (proxy contra
frequência histórica, **não é ROI real**) deu edge positivo em 5/5 folds, yield médio +5,64% —
só diagnóstico de calibração relativa, não validação de rentabilidade.

### 13.4 Conclusão
**Meta-achado da pesquisa:** a arquitetura de produção não só sobrevive à escala — ela é
**comprovadamente ótima** dentro do espaço de hipóteses testado (estatístico clássico, GBM+ratings,
state-space, ensemble, deep learning), mesmo com quase 10× mais dados e diversidade de ligas/
continentes. Não há promoção para `main`; todo o trabalho fica documentado e commitado (agora mesclado na
`main`) para referência futura (evita retestar as mesmas hipóteses).

### 13.5 Sessão 2026-07-18 — expansão de coleta (34 novas competições) + merge na `main`
Com a assinatura da API-Football expirando em 2026-07-19T01:21 UTC, a cota diária ociosa (seleções
saturadas) foi usada para diversificar ainda mais a coleta de clubes: **+34 competições** (26→60
no total), priorizadas por fama editorial em 4 tiers (grandes ligas asiáticas/2ªs divisões
europeias → ligas europeias tradicionais → ligas sul-americanas → outras ligas notáveis) — ver
lista completa em `backend/scripts/prefetch_clubs.py::LEAGUES`.

**Gargalo de throughput identificado e corrigido:** o prefetch sequencial mede ~15-20 chamadas/min
na prática (não ~450/min teórico do plano Ultra) porque `httpx.get()` sem keep-alive paga
handshake TCP/TLS completo a cada chamada. Novo `backend/scripts/prefetch_clubs_parallel.py`
(N workers + rate limiter compartilhado, mesmo padrão do `mirror_club_cache.py`) recupera a banda
real (~380 req/min sustentado). Duas armadilhas encontradas e corrigidas durante o ajuste: (1)
`--rps` acima de 450/min real (teto do plano) causa tempestade de 429 — default seguro fixado em
6.5 rps (390/min) + retry com backoff exponencial; (2) escritor único fazia Neon+SQLite por
registro e virava gargalo sob paralelismo — corrigido paralelizando a escrita no Neon dentro de
cada worker (pool de conexões do SQLAlchemy suporta, `pool_size=5 + max_overflow=10`), mantendo só
o espelho SQLite local serializado no escritor único (não aceita escrita concorrente).

**Merge `clubs` → `main` (2026-07-18):** sem sobreposição de arquivos com o trabalho recente da
`main` (parceiros/nota fiscal/frontend, §12.8/§12.9) — branches divergiram no mesmo ponto e
tocaram áreas totalmente distintas, merge automático limpo (só conflito nos docs de índice, por
edição concorrente das mesmas seções). Pesquisa de clubes (§13.1-§13.4) e infra de coleta agora
vivem na `main`.
