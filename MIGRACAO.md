# Migração de máquina — checklist para continuar sem perder avanços

> Manual para retomar o projeto numa máquina nova. Atualizado 2026-06-21.
> O **código e a documentação já estão no remoto** (push até `cc8fa7c`). O que NÃO
> viaja pelo git são os **dados locais (gitignored)** e o **estado de máquina** —
> abaixo está o que copiar e o que recriar.

## TL;DR
1. `git clone` (código já está seguro no remoto).
2. Copiar 3 pastas de dados insubstituíveis/caras (abaixo).
3. Recriar `.env` (a chave da API — só você tem) e a venv.
4. Re-registrar a tarefa agendada de odds.
5. Retomar a coleta (resume do cache copiado).

---

## 1. O que JÁ ESTÁ seguro no remoto (git) — só clonar
- Todo o código de produção (`api/`, `web/`), os modelos `api/model_artifacts/*.joblib`,
  os scripts (`scripts/`), o pipeline novo (`player_ranking/src/`) e toda a documentação
  (`docs/`, `*.md`, `RESUMO_*`, `ESTADO_*`, `ESPEC_*`).
- Na máquina nova: `git clone https://github.com/ValerioFerreira/previsao-jogos.git`

## 2. Dados locais que NÃO viajam pelo git — COPIAR fisicamente (USB/rede/nuvem)
São gitignored de propósito (grandes ou sensíveis). Da raiz do projeto:

| Caminho | Tamanho | Por que copiar | Prioridade |
|---|---|---|---|
| `data/odds/` | 1,3 MB | **Insubstituível** — coleta forward de odds do Passo 4 (forward-only, não dá p/ refazer) | **CRÍTICA** |
| `player_ranking/data/` | 76 MB | ~9,3k perfis de jogadores já baixados = ~9,3k requests já gastos; copiar evita re-gastar | **ALTA** |
| `international_features_enriched_apifootball.csv` | 17 MB | Dataset de produção (Elo/forma/resultado) — base de tudo | **ALTA** |
| `data/raw/` | 71 MB | 9.511 fixtures crus (escalações p/ o elenco-base; fonte) — recoletar custa milhares de requests | Média |
| `data/built/` | 205 MB | `historico_completo.json` + `matches.parquet` (deriváveis do raw, mas pesados) | Média |
| `data/state/` | 4 KB | estado do coletor histórico | Baixa |

> **Alternativa simples (menos erro):** copiar a pasta **inteira** `previsao-jogos`
> EXCETO `api/.venv/` e `web/node_modules/` (recriar essas — ver §4). Isso preserva
> git + todos os dados + `.env` de uma vez.

## 3. Segredo — RECRIAR (nunca viaja pelo git)
- `.env` na raiz com a chave: `APIFOOTBALL_KEY=<sua_chave>` (49 bytes; só você tem).
  Também usado por `web/.env.local` (`NEXT_PUBLIC_API_URL=http://localhost:8010`).

## 4. Ambiente — RECRIAR (não copiar venv: o histórico do projeto mostra que venv
   copiada aponta para path inexistente e quebra)
```bash
# API
py -3.12 -m venv api/.venv
api/.venv/Scripts/python -m pip install -r api/requirements.txt
# (player_ranking usa a mesma venv da api; precisa de pandas/pyarrow/requests, já em requirements)
# Front (se for usar)
cd web && npm install
```

## 5. Estado de máquina — RECRIAR
- **Tarefa agendada de odds** (coleta 3/3h do Passo 4):
```powershell
schtasks /Create /SC HOURLY /MO 3 /TN "PrevisaoJogos\CollectOdds" `
  /TR "<repo>\scripts\collect_odds_task.cmd" /F /RL LIMITED
```
- **Subir o sistema (validar):** `uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload`
  (de dentro de `api/`) + `npm run dev` (de `web/`). Front aponta p/ porta 8010.

## 6. Retomar de onde paramos (frente player_ranking)
A coleta de forma-de-clube estava em ~9,3k/13,2k perfis. Com `player_ranking/data/`
copiado, ela **resume do cache** (não re-gasta o que já foi baixado):
```bash
api/.venv/Scripts/python player_ranking/src/collect_players_fast.py   # termina os ~3,9k restantes
api/.venv/Scripts/python player_ranking/src/build_features.py
api/.venv/Scripts/python player_ranking/src/experiment.py             # o GATE: Elo vs player vs Elo+player
```
Se `player_ranking/data/` NÃO for copiado, a coleta recomeça do zero (re-gasta ~13k
requests — cabe na cota diária de 75k, mas é evitável copiando 76 MB).

## 7. Ponto exato de retomada (estado intelectual)
Ver `RESUMO_SESSAO_2026-06-21_parte2.md`, `ESTADO_E_PROXIMOS_PASSOS.md` e
`docs/ESPEC_player_power_ranking.md` (§9.1 = resultado do Passo 0). Resumo:
- Produção intacta; Passo 3 (UX) e harness do Passo 4 prontos; campanha de calibração/
  rating/xG deu negativo (modelos no teto in-sample).
- **Frente player_ranking: CONCLUÍDA (gate FALHOU).** Coleta completa (13,2k perfis),
  features e gate rodados. Ver `player_ranking/RELATORIO.md`: o player-ranking de
  **agregado-de-temporada é redundante com o Elo** (corr +0,55..+0,72) e não melhora a
  previsão em nenhum subconjunto. **Não promover.** Em aberto (não testado): forma
  **recente por jogo** (ortogonal ao Elo), que exige coleta por jogo e só vale se o
  backtest ao vivo indicar.
- Próximo passo real do projeto: deixar o **backtest de odds ao vivo** acumular (árbitro
  empírico de edge); não há alavanca in-sample pendente.
