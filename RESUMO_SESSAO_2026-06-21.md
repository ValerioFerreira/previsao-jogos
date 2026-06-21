# Resumo da Sessão — 2026-06-21

> Passo a passo completo de tudo que foi feito nesta conversa e o estado atual do
> sistema. Documento-âncora para retomar sem reabrir o histórico. Detalhes perenes em
> `walkthrough.md`; mapa de estado em `ESTADO_E_PROXIMOS_PASSOS.md`.

---

## 0. Contexto inicial

Retomada do projeto de ML de previsão de jogos de seleções **numa máquina nova**
(ThinkStation P2, 20 threads, 64 GB). Objetivo da sessão: validar ambiente, fechar os
modelos de contagem, e deixar **todo o backend pronto** antes do UX.

## 1. Validação de ambiente e reparo da venv

- Python 3.12.0 OK; scikit-learn **1.5.2** (travado) e demais libs presentes na `.venv`.
- **Problema:** a `.venv` veio da máquina antiga e apontava para um path inexistente.
  **Reparada in-place** (`py -3.12 -m venv .venv`, preservando `site-packages`).
- Dataset (`international_features_enriched_apifootball.csv`: 9.976×282, 4.102 com stats),
  `data/`, e os `model_artifacts*` íntegros. `APIFOOTBALL_KEY` só no `.env` (não no env).

## 2. Migração git (recuperação de arquivos órfãos)

- A máquina antiga sincronizou para o remoto (commits `101caea`, `fc95234`). Pull final
  feito com **disciplina de segurança**: backup completo do projeto (`previsao-jogos-prepull-backup/`),
  verificação por hash de que os 59 arquivos não-rastreados eram byte-idênticos ao remoto,
  e merge fast-forward. Recuperados: `compare_corners.py`, `comparacao_escanteios.md`,
  `reports/`, `compare_cv_fair.py`, `validate_unification.py`, etc.

## 3. Ciclo de modelos de contagem (fechado nesta sessão)

Migração de cada mercado para uma **distribuição de contagem própria** (PMF real),
expondo estimativa + intervalo 80% + grade de linhas O/U + odds da CDF. Disciplina:
comparação justa (split temporal), gate de calibração (log-loss/ECE), backup, não-regressão
byte-idêntica dos demais mercados, teste HTTP real.

| Mercado | Modelo | Achado-chave |
|---|---|---|
| **Escanteios** (2c) | NB independente (`corners_nb.joblib`) | Sobredispersão real (r≈17-21); acoplado aposentado (β=−0,04 fraco) |
| **Cartões** (2b) | NB independente (`cards_nb.joblib`) | r colapsou (~1000) → **na prática Poisson**; ganho vem da contagem vs Normal. Correlação +0,07 (positiva mas fraca) |
| **Chutes** | NB independente + **time decay H=2** (`shots_nb.joblib`) | Sobredispersão real (r≈18); **único alvo onde o decay ajuda** |

Resultado: log-loss e ECE melhores que a quantílica em todos; quantílica + aproximação
Normal **totalmente aposentadas**.

## 4. Análises estratégicas (decisões fundamentadas em medição)

- **Experimento martj42 (história completa vs só 2016+):** medimos o custo de remover a
  base histórica martj42 (que ancora resultados/Elo). Conclusão: a história profunda tem
  **valor real e ~80% irredutível** (Elo de seleções não "lava" o passado porque jogam
  pouco). Um modelo construído de propósito para 2016+ (Elo provisional) recuperou só ~18%
  do gap. **Decisão: manter a martj42.**
- **Auditoria do guia de modelagem vs api-football:** os dados da api-football bastam para
  o nível **box-score** (shots, corners, cards, fouls, posse, passes, Elo) mas **não** para
  os features de tracking do guia (xG histórico — só 2023+; entradas no terço final;
  cruzamentos; PPDA real; stats robustas de árbitro — só 22% têm país). Registrado o
  descasamento "guia de clubes vs seleções".
- **Peso temporal + mando/competição testados:** time decay só ajuda chutes; peso de
  competição negativo; mando triplo tem um resíduo real em escanteios no campo neutro
  (item 2 abaixo).

## 5. Itens finais de backend (autônomos)

### Item 2 — Escanteios em campo neutro (`7c166a9`)
Verificado com poder (OOF CV, 1016 neutros): o modelo super-creditava ~0,2 escanteios ao
mandante nominal em campo neutro (**resíduo real, ~2,4σ**), porque as flags `neutral`/
`real_home_advantage` sozinhas não bastavam. **Fix:** 2 features de interação de mando
(`api/corner_interactions.py`), determinísticas, usadas idêntico no treino e na inferência.
Resíduo cai (mandante −0,30→−0,23, visitante +0,09→+0,01), ECE mandante 2,73%→1,98%,
log-loss total melhora. Não-regressão OK.

### Item 3 — Odds de mercado + value betting (`2091a12`)
- `api/value_betting.py`: núcleo offline (UX-ready) — compara prob do modelo vs odd da
  casa → **edge/EV**, de-vig de 2 vias, odd justa. EV>0 = valor.
- `scripts/fetch_odds.py`: coletor `/odds` da api-football mapeando os bet ids dos nossos
  mercados (resultado=1, gols O/U=5, BTTS=8, escanteios=45/57/58, cartões=80/82/83),
  consenso por mediana entre casas. **Validado ao vivo** num jogo da Copa 2026.
- **Limitação:** api-football só dá odds 1-14 dias antes e 7 dias de histórico → **sem
  backtest retroativo**; a coleta é forward-only e **deve ser agendada** (1×/3h). Chutes
  não têm odds (casas não oferecem).

### Item 4 — Limpeza (`7ee5b0a`)
Removido o carregamento morto da quantílica (`self.qm`, `_quantile`, `_num`) do
`predictor.py` — todos os mercados migraram. `_conf_label` preservado.

## 6. Estado atual do sistema

- **Produção (`api/model_artifacts/`):** Dixon-Coles (resultado/gols/BTTS/over) + NB de
  escanteios/cartões/chutes. Todos expõem PMF + linhas O/U + odds justas da CDF.
  `predictor.py` + `odds.py` servindo; API FastAPI testada via HTTP.
- **Branch:** `main`. Commits desta sessão: 2c (escanteios, `126fcfc`), 2b (cartões,
  `139e7e7`), chutes (`e940da9`), item 2 (`7c166a9`), item 3 (`2091a12`), item 4 (`7ee5b0a`).
- **Backups (fora do repo):** `previsao-jogos-prepull-backup/` e
  `_backup_model_artifacts_pre_*` (manter até uso real confirmado).
- **Experimentos** (working tree, não-commitados ou em `scripts/experiment_*`): história,
  decay, mando/competição, escanteios-neutro. `scratch/experimento_historico/` com datasets
  e relatórios (gitignored).

## 7. Pendências e próximos passos

1. **Passo 3 — UX/UI** (próximo grande bloco): slider probabilidade-alvo→linha, value
   betting (módulo pronto em `value_betting.py`), combinadas com "teto otimista", edição
   das 10 features, estatísticas/destaques das equipes. **Estender os tipos TS do front**
   (ainda não declaram `cartoes`/`distribuicao`/`linhas`).
2. **Agendar a coleta de odds** (`fetch_odds.py`) para acumular histórico e, no futuro,
   validar value contra mercado (Passo 4 retroativo só será possível com histórico próprio).
3. **Melhoria localizada não-promovida:** resíduo de escanteios no neutro foi corrigido;
   resíduos análogos em gols/cartões no neutro existem mas menores — não atacados.
4. **Cosméticos:** duplicata `scripts/dixon_coles_model.py` vs `api/` (fonte de verdade é
   `api/`); `quantile_models.joblib` no disco mas não mais carregado.
