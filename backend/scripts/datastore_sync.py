#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/datastore_sync.py — sincroniza os dados do projeto com a fonte da verdade.
==================================================================================

A fonte da verdade oficial é o Zoho WorkDrive (`DATA_STORE=workdrive`). O provedor
`local` (default) permite exercitar todo o fluxo sem credencial.

Comandos:
  status              mostra, por dataset do MANIFEST, o que existe local vs remoto
  push [--id X]       envia local -> remoto (só o que mudou, por checksum)
  pull [--id X]       traz remoto -> local (só o que mudou)
  verify              confere se todo dataset do manifesto tem cópia remota (a regra de
                      ouro: nenhum dado com cópia única em máquina local)

Exemplos:
  python -m scripts.datastore_sync status
  DATA_STORE=workdrive python -m scripts.datastore_sync push --id club_raw_cache
  DATA_STORE=workdrive python -m scripts.datastore_sync pull

Sync incremental: compara sha256 local com o checksum registrado em
`backend/data/.datastore_state.json` (atualizado a cada push/pull bem-sucedido). Sem isso
subiríamos 583 MB a cada execução.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.core.datastore import get_datastore, sha256_file  # noqa: E402

MANIFEST = REPO_ROOT / "data" / "MANIFEST.yaml"
STATE = BACKEND_ROOT / "data" / ".datastore_state.json"

# Camadas que devem ter cópia no provedor remoto.
REMOTE_LAYERS = {"workdrive", "git", "derived"}


def load_manifest() -> dict:
    if not MANIFEST.exists():
        raise SystemExit(f"MANIFEST não encontrado: {MANIFEST}")
    try:
        import yaml  # type: ignore
    except ImportError:
        raise SystemExit("PyYAML ausente. Instale: pip install pyyaml")
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def expand(ds: dict) -> list[tuple[Path, str]]:
    """Expande a entrada do manifesto em pares (arquivo_local, caminho_remoto)."""
    raw = ds["path"]
    remote = ds["remote"].rstrip("/")
    out: list[tuple[Path, str]] = []

    if "*" in raw:                              # glob (ex.: built/backtest_*.parquet)
        base = REPO_ROOT / Path(raw).parent
        pattern = Path(raw).name
        if base.exists():
            for p in sorted(base.iterdir()):
                if p.is_file() and fnmatch.fnmatch(p.name, pattern):
                    out.append((p, f"{remote}/{p.name}"))
        return out

    local = REPO_ROOT / raw
    if raw.endswith("/"):                       # diretório inteiro (recursivo)
        if local.exists():
            for p in sorted(local.rglob("*")):
                if p.is_file() and not p.name.startswith("."):
                    rel = p.relative_to(local).as_posix()
                    out.append((p, f"{remote}/{rel}"))
        return out

    if local.exists():
        out.append((local, remote))
    return out


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024.0
    return f"{n:.1f}TB"


def cmd_status(manifest: dict, args) -> None:
    store = get_datastore()
    state = load_state()
    print(f"Provedor: {store.name}   (DATA_STORE={os.environ.get('DATA_STORE', 'local')})")
    print("=" * 96)
    total_local = total_missing = 0
    for ds in manifest["datasets"]:
        if args.id and ds["id"] != args.id:
            continue
        files = expand(ds)
        n_local = len(files)
        size = sum(p.stat().st_size for p, _ in files)
        total_local += size
        remote_ok = sum(1 for _, r in files if state.get(r, {}).get("pushed"))
        missing = n_local - remote_ok
        total_missing += missing
        flag = "OK " if (n_local and not missing) else ("-- " if not n_local else "!! ")
        print(f"{flag}{ds['id']:26s} camada={ds['layer']:9s} local={n_local:4d} arq "
              f"({human(size):>7s})  sincronizado={remote_ok:4d}  pendente={missing:4d}")
        if not n_local:
            print(f"   ausente localmente: {ds['path']}")
    print("=" * 96)
    print(f"Total local: {human(total_local)} | arquivos pendentes de envio: {total_missing}")


def cmd_push(manifest: dict, args) -> None:
    store = get_datastore()
    state = load_state()
    sent = skipped = 0
    seen: set[str] = set()
    for ds in manifest["datasets"]:
        if args.id and ds["id"] != args.id:
            continue
        if ds["layer"] not in REMOTE_LAYERS:
            continue
        for local, remote in expand(ds):
            if remote in seen:      # entradas do manifesto podem se sobrepor
                continue            # (ex.: reports/ contém reports/performance/)
            seen.add(remote)
            digest = sha256_file(local)
            if state.get(remote, {}).get("sha256") == digest and not args.force:
                skipped += 1
                continue
            print(f"  -> {remote}  ({human(local.stat().st_size)})")
            if not args.dry_run:
                store.upload(local, remote)
                state[remote] = {"sha256": digest, "size": local.stat().st_size, "pushed": True}
            sent += 1
    if not args.dry_run:
        save_state(state)
    print(f"\nEnviados: {sent} | inalterados (pulados): {skipped}"
          + ("  [DRY-RUN]" if args.dry_run else ""))


def _local_dest(ds: dict, remote_path: str) -> Path:
    """Caminho local de um arquivo remoto, PRESERVANDO a estrutura de subpastas.

    Cuidado (bug real pego em teste): usar só `Path(remote).name` achata
    `reports/performance/x.json` em `reports/x.json`. Em escala isso espalha arquivos
    em caminhos errados silenciosamente.
    """
    prefix = ds["remote"].rstrip("/")
    rel = remote_path[len(prefix):].lstrip("/") if remote_path.startswith(prefix) else Path(remote_path).name
    raw = ds["path"]
    if raw.endswith("/") or "*" in raw:
        base = REPO_ROOT / (Path(raw).parent if "*" in raw else Path(raw.rstrip("/")))
        return base / rel
    return REPO_ROOT / raw          # arquivo único


def cmd_pull(manifest: dict, args) -> None:
    store = get_datastore()
    got = skipped = missing = 0
    seen: set[str] = set()
    for ds in manifest["datasets"]:
        if args.id and ds["id"] != args.id:
            continue
        if ds["layer"] not in REMOTE_LAYERS:
            continue
        remote_files = store.list(ds["remote"].rstrip("/"))
        for rf in remote_files:
            if rf.path in seen:          # entradas do manifesto podem se sobrepor
                continue
            seen.add(rf.path)
            dest = _local_dest(ds, rf.path)
            if dest.exists() and not args.force:
                skipped += 1
                continue
            print(f"  <- {rf.path}  ({human(rf.size)})")
            if not args.dry_run:
                store.download(rf.path, dest)
                got += 1
        if not remote_files:
            missing += 1
    print(f"\nBaixados: {got} | já presentes: {skipped} | datasets sem cópia remota: {missing}"
          + ("  [DRY-RUN]" if args.dry_run else ""))


def cmd_verify(manifest: dict, args) -> None:
    """Regra de ouro: nenhum dado pode existir SÓ numa máquina local.

    Consulta o REMOTO de verdade (não o `.datastore_state.json`), porque o arquivo de
    estado é só cache de otimização do push: se o remoto perder um arquivo, ou o estado
    ficar velho, confiar nele daria um "tudo certo" falso — justamente o modo de falha
    que esta camada existe para evitar.
    """
    store = get_datastore()
    violations = []
    print(f"Conferindo contra o remoto ({store.name})...")
    for ds in manifest["datasets"]:
        if ds["layer"] not in REMOTE_LAYERS:
            continue
        remote_index = {rf.path for rf in store.list(ds["remote"].rstrip("/"))}
        for local, remote in expand(ds):
            if remote not in remote_index:
                violations.append((ds["id"], remote, local.stat().st_size))
    if not violations:
        print("OK — todo dado do manifesto tem cópia na fonte da verdade.")
        return
    print(f"!! {len(violations)} arquivo(s) existem APENAS localmente "
          f"({human(sum(v[2] for v in violations))} em risco):\n")
    by_ds: dict[str, int] = {}
    for ds_id, _, size in violations:
        by_ds[ds_id] = by_ds.get(ds_id, 0) + size
    for ds_id, size in sorted(by_ds.items(), key=lambda kv: -kv[1]):
        print(f"  {ds_id:26s} {human(size):>8s}")
    print("\nRode: python -m scripts.datastore_sync push")
    sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Sincroniza dados com a fonte da verdade (WorkDrive).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("status", "push", "pull", "verify"):
        p = sub.add_parser(name)
        p.add_argument("--id", help="sincroniza só o dataset com este id do MANIFEST")
        p.add_argument("--force", action="store_true", help="ignora checksum/cache e refaz")
        p.add_argument("--dry-run", action="store_true", help="mostra o que faria, sem executar")

    args = ap.parse_args()
    manifest = load_manifest()
    {"status": cmd_status, "push": cmd_push, "pull": cmd_pull, "verify": cmd_verify}[args.cmd](
        manifest, args)


if __name__ == "__main__":
    main()
