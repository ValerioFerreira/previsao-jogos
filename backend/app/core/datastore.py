"""Camada de armazenamento de dados — fonte da verdade dos arquivos grandes do projeto.

Mesma filosofia dos adapters de pagamento/nota fiscal (`PaymentGateway`/`InvoiceProvider`):
um `Protocol` + adapters trocáveis por env var, nunca o provedor hardcoded num domínio.

Provedores:
- `local`     — disco local (default seguro; usado em dev/offline e como fallback).
- `workdrive` — Zoho WorkDrive (fonte da verdade oficial a partir de 2026-07-28).

## Por que existe

Antes desta camada, dados críticos viviam APENAS em máquinas locais: o espelho bruto de
clubes (583 MB), o dataset de treino, os snapshots de odds. Isso quebrou de forma concreta:
o backfill de 83 competições foi feito numa máquina e ficou inacessível de outra, e o
histórico de odds coletado no Render (`data/odds/*.jsonl`) é efêmero — some a cada deploy,
tornando impossível medir CLV (a métrica mais confiável de habilidade em apostas).

## Regra de ouro

Nenhum dado pode ter sua ÚNICA cópia numa máquina local. O diretório local é **cache
derivado e descartável** — apagar e rodar `datastore_sync.py pull` deve restaurar tudo.

WorkDrive é armazenamento de ARQUIVOS, não banco: não dá `SELECT` nele. Dado que precisa
de query em runtime continua no Neon (ver `data/MANIFEST.yaml`, camada `neon`).
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

logger = logging.getLogger(__name__)

# Raiz do backend (…/backend) — todos os caminhos do manifesto são relativos a ela.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
# Cache local dos arquivos vindos do provedor remoto.
CACHE_ROOT = BACKEND_ROOT / "data"

CHUNK = 1024 * 1024  # 1 MiB — leitura em blocos p/ não carregar 583 MB em memória


@dataclass
class RemoteFile:
    """Metadado de um arquivo no provedor remoto."""
    path: str                 # caminho lógico (ex.: "raw/club_raw_cache.sqlite")
    size: int
    checksum: Optional[str] = None   # sha256 quando o provedor souber informar
    remote_id: str = ""              # id nativo do provedor (WorkDrive usa id, não caminho)


def sha256_file(path: Path) -> str:
    """Checksum em blocos — sync incremental depende disso p/ não subir 583 MB à toa."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


class DataStore(Protocol):
    """Interface mínima de armazenamento. Adapters: LocalStore, WorkDriveStore."""

    name: str

    def list(self, prefix: str = "") -> list[RemoteFile]: ...

    def exists(self, logical_path: str) -> bool: ...

    def stat(self, logical_path: str) -> Optional[RemoteFile]: ...

    def download(self, logical_path: str, dest: Path) -> Path: ...

    def upload(self, src: Path, logical_path: str) -> RemoteFile: ...


class LocalStore:
    """Disco local. Default seguro — permite desenvolver e testar a camada inteira
    sem credencial do WorkDrive (`DATA_STORE=local`).

    O 'remoto' aqui é um diretório separado do cache, para que o fluxo push/pull seja
    exercitado de verdade (e não vire um no-op que esconde bug)."""

    name = "local"

    def __init__(self, root: Optional[Path] = None):
        env_root = os.environ.get("DATA_STORE_LOCAL_ROOT")
        self.root = Path(root or env_root or (BACKEND_ROOT / "data" / "_localstore"))
        self.root.mkdir(parents=True, exist_ok=True)

    def _abs(self, logical_path: str) -> Path:
        return self.root / logical_path

    def list(self, prefix: str = "") -> list[RemoteFile]:
        base = self._abs(prefix) if prefix else self.root
        if not base.exists():
            return []
        out: list[RemoteFile] = []
        for p in base.rglob("*"):
            if p.is_file():
                out.append(RemoteFile(path=str(p.relative_to(self.root)).replace("\\", "/"),
                                      size=p.stat().st_size))
        return out

    def exists(self, logical_path: str) -> bool:
        return self._abs(logical_path).exists()

    def stat(self, logical_path: str) -> Optional[RemoteFile]:
        p = self._abs(logical_path)
        if not p.exists():
            return None
        return RemoteFile(path=logical_path, size=p.stat().st_size, checksum=sha256_file(p))

    def download(self, logical_path: str, dest: Path) -> Path:
        src = self._abs(logical_path)
        if not src.exists():
            raise FileNotFoundError(f"[datastore:local] não existe no remoto: {logical_path}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return dest

    def upload(self, src: Path, logical_path: str) -> RemoteFile:
        if not src.exists():
            raise FileNotFoundError(f"[datastore:local] origem não existe: {src}")
        dst = self._abs(logical_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return RemoteFile(path=logical_path, size=dst.stat().st_size, checksum=sha256_file(dst))


class WorkDriveStore:
    """Zoho WorkDrive via API REST + OAuth2 (refresh token).

    Credenciais (env / backend/.env):
      ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REFRESH_TOKEN
      ZOHO_WORKDRIVE_FOLDER_ID   — pasta raiz do repositório de dados
      ZOHO_ACCOUNTS_BASE         — default https://accounts.zoho.com
      ZOHO_WORKDRIVE_BASE        — default https://www.zohoapis.com/workdrive/api/v1

    ATENÇÃO ao data center: contas na UE/Índia/Austrália usam domínios distintos
    (`.eu`, `.in`, `.com.au`) tanto em accounts quanto em zohoapis — é a mesma pegadinha
    já documentada no ZeptoMail (`zeptomail_base_url`). Se os domínios não baterem com a
    região da conta, a autenticação falha com erro pouco descritivo.

    Nota de implementação: o WorkDrive endereça arquivos por **id**, não por caminho.
    Este adapter mantém um índice caminho-lógico → id, resolvido navegando as pastas a
    partir de `ZOHO_WORKDRIVE_FOLDER_ID` e cacheado em memória por processo.
    """

    name = "workdrive"

    def __init__(self) -> None:
        self.client_id = os.environ.get("ZOHO_CLIENT_ID", "")
        self.client_secret = os.environ.get("ZOHO_CLIENT_SECRET", "")
        self.refresh_token = os.environ.get("ZOHO_REFRESH_TOKEN", "")
        self.root_folder_id = os.environ.get("ZOHO_WORKDRIVE_FOLDER_ID", "")
        self.accounts_base = os.environ.get("ZOHO_ACCOUNTS_BASE", "https://accounts.zoho.com")
        self.api_base = os.environ.get("ZOHO_WORKDRIVE_BASE",
                                       "https://www.zohoapis.com/workdrive/api/v1")
        missing = [k for k, v in {
            "ZOHO_CLIENT_ID": self.client_id,
            "ZOHO_CLIENT_SECRET": self.client_secret,
            "ZOHO_REFRESH_TOKEN": self.refresh_token,
            "ZOHO_WORKDRIVE_FOLDER_ID": self.root_folder_id,
        }.items() if not v]
        if missing:
            raise RuntimeError(
                "DATA_STORE=workdrive mas faltam credenciais: " + ", ".join(missing) +
                ". Crie em https://api-console.zoho.com e coloque em backend/.env."
            )
        self._token: Optional[str] = None
        self._folder_cache: dict[str, str] = {}

    # --- OAuth ---------------------------------------------------------------
    def _access_token(self) -> str:
        if self._token:
            return self._token
        import httpx
        resp = httpx.post(
            f"{self.accounts_base}/oauth/v2/token",
            data={"refresh_token": self.refresh_token, "client_id": self.client_id,
                  "client_secret": self.client_secret, "grant_type": "refresh_token"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError(f"WorkDrive: refresh de token não retornou access_token: {data}")
        self._token = token
        return token

    def _headers(self) -> dict:
        return {"Authorization": f"Zoho-oauthtoken {self._access_token()}",
                "Accept": "application/vnd.api+json"}

    # --- Navegação de pastas -------------------------------------------------
    def _children(self, folder_id: str) -> list[dict]:
        import httpx
        resp = httpx.get(f"{self.api_base}/files/{folder_id}/files",
                         headers=self._headers(), timeout=60)
        resp.raise_for_status()
        return resp.json().get("data", [])

    def _resolve(self, logical_path: str, create_missing: bool = False) -> tuple[str, Optional[str]]:
        """Resolve 'a/b/arquivo.parquet' -> (id_da_pasta_pai, id_do_arquivo|None)."""
        parts = [p for p in logical_path.replace("\\", "/").split("/") if p]
        if not parts:
            return self.root_folder_id, None
        *dirs, filename = parts
        parent = self.root_folder_id
        for d in dirs:
            key = f"{parent}/{d}"
            if key in self._folder_cache:
                parent = self._folder_cache[key]
                continue
            found = next((c for c in self._children(parent)
                          if c.get("attributes", {}).get("name") == d
                          and c.get("attributes", {}).get("is_folder")), None)
            if found is None:
                if not create_missing:
                    raise FileNotFoundError(f"[workdrive] pasta inexistente: {d} (em {logical_path})")
                found = self._create_folder(parent, d)
            parent = found["id"] if "id" in found else found.get("id", "")
            self._folder_cache[key] = parent
        file_entry = next((c for c in self._children(parent)
                           if c.get("attributes", {}).get("name") == filename), None)
        return parent, (file_entry.get("id") if file_entry else None)

    def _create_folder(self, parent_id: str, name: str) -> dict:
        import httpx
        resp = httpx.post(f"{self.api_base}/files", headers={**self._headers(),
                                                            "Content-Type": "application/json"},
                          json={"data": {"attributes": {"name": name, "parent_id": parent_id},
                                          "type": "files"}}, timeout=60)
        resp.raise_for_status()
        return resp.json().get("data", {})

    # --- Interface DataStore -------------------------------------------------
    def list(self, prefix: str = "") -> list[RemoteFile]:
        folder_id = self.root_folder_id
        if prefix:
            folder_id, _ = self._resolve(prefix.rstrip("/") + "/_", create_missing=False)
        out: list[RemoteFile] = []
        for c in self._children(folder_id):
            attrs = c.get("attributes", {})
            if attrs.get("is_folder"):
                continue
            out.append(RemoteFile(path=f"{prefix.rstrip('/')}/{attrs.get('name')}".lstrip("/"),
                                  size=int(attrs.get("storage_info", {}).get("size_in_bytes", 0) or 0),
                                  remote_id=c.get("id", "")))
        return out

    def exists(self, logical_path: str) -> bool:
        try:
            _, file_id = self._resolve(logical_path)
            return file_id is not None
        except FileNotFoundError:
            return False

    def stat(self, logical_path: str) -> Optional[RemoteFile]:
        try:
            _, file_id = self._resolve(logical_path)
        except FileNotFoundError:
            return None
        if not file_id:
            return None
        import httpx
        resp = httpx.get(f"{self.api_base}/files/{file_id}", headers=self._headers(), timeout=60)
        resp.raise_for_status()
        attrs = resp.json().get("data", {}).get("attributes", {})
        return RemoteFile(path=logical_path,
                          size=int(attrs.get("storage_info", {}).get("size_in_bytes", 0) or 0),
                          remote_id=file_id)

    def download(self, logical_path: str, dest: Path) -> Path:
        import httpx
        _, file_id = self._resolve(logical_path)
        if not file_id:
            raise FileNotFoundError(f"[workdrive] não existe no remoto: {logical_path}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with httpx.stream("GET", f"{self.api_base}/download/{file_id}",
                          headers=self._headers(), timeout=None, follow_redirects=True) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(CHUNK):
                    f.write(chunk)
        tmp.replace(dest)   # atômico: nunca deixa arquivo pela metade no lugar do bom
        return dest

    def upload(self, src: Path, logical_path: str) -> RemoteFile:
        import httpx
        if not src.exists():
            raise FileNotFoundError(f"[workdrive] origem não existe: {src}")
        parent_id, _ = self._resolve(logical_path, create_missing=True)
        with open(src, "rb") as fh:
            resp = httpx.post(
                f"{self.api_base}/upload",
                headers={"Authorization": f"Zoho-oauthtoken {self._access_token()}"},
                params={"parent_id": parent_id, "override-name-exist": "true"},
                files={"content": (Path(logical_path).name, fh)},
                timeout=None,
            )
        resp.raise_for_status()
        return RemoteFile(path=logical_path, size=src.stat().st_size, checksum=sha256_file(src))


def get_datastore(provider: Optional[str] = None) -> DataStore:
    """Fábrica — trocável por `DATA_STORE` (local | workdrive). Default: local."""
    name = (provider or os.environ.get("DATA_STORE") or "local").lower()
    if name == "workdrive":
        return WorkDriveStore()
    return LocalStore()


def fetch(logical_path: str, *, local_rel: Optional[str] = None,
          force: bool = False) -> Path:
    """Resolve um dado do manifesto para um caminho local utilizável.

    É a função que scripts e serviços devem chamar em vez de abrir caminho hardcoded:
    se já estiver no cache local, usa; se não, baixa do provedor. Assim o cache pode ser
    apagado a qualquer momento sem perder dado (regra de ouro deste módulo).
    """
    dest = CACHE_ROOT / (local_rel or logical_path)
    if dest.exists() and not force:
        return dest
    store = get_datastore()
    logger.info("[datastore:%s] baixando %s -> %s", store.name, logical_path, dest)
    return store.download(logical_path, dest)
