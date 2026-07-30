# HANDOFF — continuação em outra máquina

> **Escrito em**: 2026-07-28/29, ao fim de uma sessão que rodou numa máquina **sem** as
> credenciais de produção e **sem** a base completa de clubes.
> **Para**: o próximo agente/dev que continuar este trabalho em outra máquina.
> **Leia junto**: `DOCUMENTACAO_CENTRAL.md` §23 a §26 (nesta ordem) e `CLAUDE.md`.

---

## 0. TL;DR — o que aconteceu e o que falta

Uma bateria de hipóteses A/B/C (§23) tinha sido executada com **odds fabricadas** e um **modelo
de brinquedo**, produzindo números inflados que contradiziam a bateria séria já registrada (§20).
Isso foi **retirado** (§23 virou nota de retirada) e **refeito de forma honesta** (§24), com o
modelo de produção real e odds reais. O diagnóstico que explica os resultados está no §25. Uma
decisão de arquitetura de dados (armazenamento externo como fonte da verdade) foi tomada e a
camada foi construída e testada (§26).

> **Atualização 2026-07-30 (§28)**: dos 3 bloqueios abaixo, **2 já foram resolvidos** numa sessão
> posterior nesta mesma máquina — o mirror de competições avançou (326.386 jogos / 108 ligas, via
> `prefetch_clubs_parallel.py --include-expansion`, não via `DATABASE_URL` do Neon) e
> `football-data.co.uk` respondeu normalmente daqui (107.095 partidas com odds baixadas,
> **N do backtest saiu de 722 para 73.667**). O provedor de armazenamento também mudou: **era Zoho
> WorkDrive, agora é Google Drive** — nenhuma credencial de Zoho chegou a ser criada, então a troca
> não perdeu nenhum dado. As instruções abaixo já refletem o provedor novo.

**Bloqueios remanescentes:**

| # | Bloqueio | O que falta | Impacto |
|---|---|---|---|
| 1 | ~~Mirror de competições~~ | resolvido em 2026-07-30 (§28) | — |
| 2 | Armazenamento externo (Google Drive) | credenciais de service account | Dados ainda com cópia única local |
| 3 | ~~Odds históricas~~ | resolvido em 2026-07-30 (§28) | — |

---

## 1. Ative o Google Drive primeiro (§26, atualizado §28)

É o passo que impede a próxima máquina de repetir o problema desta.

```bash
# 1) credenciais em backend/.env (criar em https://console.cloud.google.com):
#    a) crie um projeto -> APIs & Services -> ative "Google Drive API"
#    b) IAM & Admin -> Service Accounts -> criar -> gerar chave JSON
#    c) crie/escolha uma pasta no SEU Google Drive normal e COMPARTILHE com o
#       e-mail da service account (campo "client_email" do JSON), papel Editor
#       -- sem isso a service account nao enxerga a pasta (nao tem Drive proprio)
#    d) pegue o ID da pasta na URL (https://drive.google.com/drive/folders/<ID>)
#
#    GOOGLE_SERVICE_ACCOUNT_JSON=/caminho/para/a-chave.json   (ou _B64= com o JSON em base64)
#    GOOGLE_DRIVE_FOLDER_ID=<ID da pasta compartilhada>

cd backend
DATA_STORE=gdrive python -m scripts.datastore_sync status   # o que existe local vs remoto
DATA_STORE=gdrive python -m scripts.datastore_sync push     # sobe tudo (~8 GB na 1a vez, ver §28)
DATA_STORE=gdrive python -m scripts.datastore_sync verify   # exit 1 se algo so existir local
```

**A máquina que tem os dados bons deve dar `push` ANTES de qualquer máquina dar `pull`.**
Em 2026-07-30 (pós-§28) o `status` acusa **~8 GB / 1255 arquivos** com cópia única local — mais
que os 952 MB de quando este documento foi escrito, porque a coleta avançou bastante nesse meio
tempo (expansão de competições, lesões, odds históricas, contexto de elenco).

**Regra de ouro**: nenhum dado pode ter cópia única em máquina local. Dado novo → registrar em
`data/MANIFEST.yaml` → acessar via `app/core/datastore.py::fetch()` → `push`.

⚠️ **Cuidado documentado**: o `GoogleDriveStore` foi escrito e testado contra `LocalStore` (fluxo
completo, incluindo `status`) mas **nunca foi executado contra a API real do Google Drive** — a
credencial ainda não existia quando o adapter foi escrito. Espere ajustar detalhes de
endpoint/paginação na primeira execução real, especialmente `_resolve()` (o Drive endereça por
**id**, não por caminho, e permite nomes duplicados na mesma pasta) e o upload resumível
(`upload()` faz streaming em blocos de 1 MiB via protocolo de 2 passos — `initiate` + `PUT` na
`Location` retornada — para não estourar memória com o `club_raw_cache.sqlite`, hoje ~7 GB). Valide
com um dataset pequeno (`--id reports`) antes de subir os gigabytes do `club_raw_cache`.

---

## 2. Destrave a base de clubes (§24.1, §24.5)

Esta máquina só tinha **4 competições** (21.130 jogos: Brasileirão A/B, Premier League,
Champions League). A produção usa **83 competições / 272.918 jogos / 72 torneios** — coletadas
em outra máquina e **inacessíveis daqui**. É exatamente o problema que o Drive resolve.

```bash
cd backend
# precisa de DATABASE_URL real do Neon (aqui só havia sqlite:///./dev_verify.db)
# e de APIFOOTBALL_KEY (checar cota antes: GET /status -> subscription.end)
python scripts/mirror_club_cache.py            # backfill do bruto via API, zero egress do Neon
python scripts/build_clubs_dataset.py --stage all
# validar: df['tournament'].nunique() ~= 72 e len(df) ~= 272918 (bate com
# model_artifacts_clubes/meta.json). Se der 4 torneios/21k, a base ainda está incompleta.
```

---

## 3. Refaça o backtest com a base completa (§24.5)

Cadeia exata, nesta ordem (todos os scripts já existem e funcionam):

```bash
cd backend
python scripts/backtest_train_frozen_model.py --cutoff 2025-07-01   # NUNCA sobrescreve produção
python scripts/backtest_odds_ingest.py --year 2025
python scripts/backtest_match_games.py
python scripts/backtest_generate_predictions.py
python scripts/adhoc_diagnostico_modelo_vs_mercado.py    # RODE ESTE PRIMEIRO (dá o benchmark)
python scripts/adhoc_hipotese_a_alfa_cotacao.py
python scripts/adhoc_hipotese_b_perfis_apostador.py
python scripts/adhoc_hipotese_c_desagregacao.py
```

Depois **atualize os números do §24 e do `docs/RELATORIO_HIPOTESES_A_B_C_v2.md`** — os valores
lá são de N=722 (2 ligas, 1 temporada) e devem ser substituídos, não somados.

---

## 4. Regras que NÃO podem ser quebradas (aprendidas na marra)

1. **Nunca fabricar odds a partir da probabilidade do próprio modelo.** É circular por
   construção — o "alfa" aparece garantido mesmo sem edge nenhum. Foi o erro que invalidou o
   §23 inteiro. Use odds de mercado independentes (`data-test/`, coleta forward).
2. **Nunca use `model_artifacts{,_clubes}/` (produção) para medir desempenho histórico.** Eles
   foram ajustados na base inteira, sem holdout (`meta.json["n_train"]` = 100% dos dados) —
   é vazamento garantido. Use um artefato **congelado** (`backtest_train_frozen_model.py`).
3. **Nunca use `Predictor.predict()` para backtest.** Ele usa o snapshot de **agora**. Use
   `predict_from_row(row)`, que consome features point-in-time da linha histórica.
4. **Nunca compare ROI contra zero.** O benchmark é o ROI-sem-edge dado o vig (§25.1). Com vig
   de 6.05%, o benchmark é **−5.71%**, não 0. Comparar contra zero fez um modelo são parecer
   quebrado.
5. **Sempre reporte N e IC95% (bootstrap).** Nenhum número pontual sem intervalo. E cheque o
   poder: detectar edge de 2% exige ~20.100 apostas (§25.3).
6. **Piso de amostra em tabelas por liga/ano** (usamos N≥100). Nunca uma linha "1 jogo, 100% de
   acerto" ao lado da Premier League — foi outro vício do §23.
7. **Antes de propor hipótese de odds/valor/EV:** ler §19, §20, §24, §25. Muita coisa já foi
   reprovada com amostra grande; não repita.

---

## 5. Onde o projeto está, cientificamente (§25)

Não há nada quebrado no modelo. Os números:

- **Vig 6.05%** → benchmark sem edge = −5.71%. ROI observado agregado = −5.85% (**−0.04σ**).
- **log-loss**: modelo 1.0219 vs mercado de-vigado 0.9975 → capturamos **~76%** da informação
  do mercado. **ECE 0.0199 = bem calibrado.**
- **Poder**: 722 apostas contra ~20.100 necessárias. Nada em §24 era conclusivo, em nenhuma
  direção.
- **Hipótese aberta e mais promissora**: eficiência de mercado difere por liga — capturamos 85%
  no Brasileirão (onde até ganhamos em acurácia: 52.0% vs 51.8%) e 65% na Premier League. Se há
  edge, é em mercados menos eficientes, não nas big five.
- **Métrica que deveria virar primária: CLV** (closing line value) — converge com N muito menor
  que ROI. Hoje **impossível de medir** porque o histórico de odds não é persistido (só o
  snapshot mais recente vai pro Neon; os `.jsonl` do Render são efêmeros). **Corrigir isso é o
  item de maior retorno depois do Drive.**

**Conclusão estratégica**: três baterias independentes (§19, §20, §25) convergem — bater o
mercado provavelmente não é o negócio. O que é defensável e já está no ar: *o usuário perde
menos, decide melhor e paga menos vig* (`/desempenho` + alfa de cotação do §24.2).

---

## 6. Pendências abertas (com dono e critério de pronto)

| Item | Bloqueado por | Pronto quando |
|---|---|---|
| Ativar Google Drive | credenciais de service account (§1) | `datastore_sync verify` sai com exit 0 |
| ~~Mirror de clubes~~ | resolvido 2026-07-30 (§28) — 326.386 jogos/108 ligas | — |
| ~~Odds históricas~~ | resolvido 2026-07-30 (§28) — `data-test/historical/` populado | — |
| Persistir histórico de odds | decisão de schema | CLV mensurável (§25.5) |
| Migrar blobs do Neon | Google Drive ativo | `match_detail_cache` fora do Neon |
| Rever §24 com base completa | Google Drive ativo (item 1) | números de N>10k no §24 e no v2 (ver §28, N já disponível: 73.667) |
| **Expansão de mercados** | ver `docs/PLANO_EXPANSAO_MERCADOS.md` | gate §6-C definido + candidatos julgados |

**Expansão de mercados (plano aprovado 2026-07-29, nada executado)**: há ~15 mercados novos
abertos com o dado que **já está no cache**, sem gastar cota de API — 7 estatísticas da API que
nunca viraram coluna, mais tudo que `events` (99,9% de cobertura, minuto exato) permite derivar.
O plano completo, com catálogo, armadilhas de dado e critérios, está em
**`docs/PLANO_EXPANSAO_MERCADOS.md`**. Achado central: **os mercados de contagem em produção
nunca passaram por gate nenhum** — a Fase 0 é definir o gate §6-C, a Fase 1 é aplicá-lo
retroativamente aos 7 mercados já no ar. As Fases 2 e 4 (clube) dependem do mirror completo.

**Odds históricas — RESOLVIDO em 2026-07-30 (§28)**: `backend/scripts/fetch_historical_odds.py`
rodou com sucesso **nesta mesma máquina**, 2 dias depois. O bloqueio de 2026-07-28 (DNS resolvia
mas o TCP era descartado em http/https especificamente pra `football-data.co.uk`) não se repetiu —
era transitório ou específico daquela janela de rede, não do domínio nem do script. Resultado: 305
arquivos, 33 MB, 16 temporadas × 22 divisões, em `data-test/historical/<temporada>/<div>.csv`. Se
isso voltar a acontecer numa máquina nova, tente de outra rede antes de assumir que o script está
errado — ele já está validado contra a fonte real.

---

## 7. Detalhes de ambiente que custaram tempo

- **`openpyxl`** foi instalado no venv nesta sessão (necessário para ler
  `data-test/new_leagues_data.xlsx`, onde está o Brasileirão). Não estava no `requirements`.
  Se `backtest_odds_ingest.py` falhar com `ImportError: openpyxl`, é isso.
- **`pyyaml`** é necessário para `datastore_sync.py` (lê o MANIFEST).
- **`APIFOOTBALL_KEY`** existia no `.env` da **raiz** mas não em `backend/.env` (que é o único
  que `fixture_fetch.py::_key()` lê). Foi copiada nesta sessão. Ambos os `.env` são gitignored.
- **Cota da API-Football** em 2026-07-28: 67.530/75.000 restantes, assinatura válida até
  **2026-08-19**. Cheque `GET /status` antes de planejar coleta de vários dias.
- **Bug de dados real**: no `new_leagues_data.xlsx` (Brasileirão) as odds só existem na coluna
  de **fechamento**. Filtrar apenas abertura zera o Brasileirão inteiro — os 3 scripts de
  hipótese usam fechamento com fallback para abertura por causa disso.

---

## 8. Estado do repositório

Commitado na `main` ao fim desta sessão: documentação (§23-§26), camada de dados
(`datastore.py`, `MANIFEST.yaml`, `datastore_sync.py`), scripts de hipótese e diagnóstico,
`fetch_historical_odds.py`, relatório v2, e o v1 marcado como descartado.

**Não commitado (mudanças de outra sessão, intocadas):** alterações em
`backend/app/domains/admin/*`, `frontend/src/**`, `AGENTS.md`, `docs/AUDIT_REPORT.md`,
`graphify-out/`. Se você não as reconhece, confirme com o dono antes de mexer.

### ⚠️ Armadilha real, custou meia sessão — não repita

`backend/model_artifacts_clubes_2025frozen/` **já estava commitado, treinado na base completa
(250.682 jogos / 5.365 times)**. Rodar `backtest_train_frozen_model.py --cutoff 2025-07-01`
nesta máquina o **sobrescreveu silenciosamente** por uma versão de apenas 19.574 jogos / 396
times — porque o script lê o `club_features_enriched.parquet` **local**, que aqui só tinha 4
ligas. Todo o backtest rodou com um modelo aleijado antes de o erro ser detectado; foi revertido
(`git checkout`) e tudo foi regerado com o artefato bom.

**Antes e depois de rodar qualquer `*_train_*`:**
```bash
python -c "import json,io; m=json.load(io.open('backend/model_artifacts_clubes_2025frozen/meta.json',encoding='utf-8',errors='replace')); print(m['n_train']['goals'], len(m['snapshot']))"
# esperado: 250682 5365  (ou mais, se a base tiver crescido). Se cair para ~19k/396, PARE.
```
Só retreine o congelado depois de confirmar que a base local está completa (~273k jogos/72
torneios). Um artefato congelado bom vale mais que um retreino ruim.
