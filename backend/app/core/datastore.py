"""Camada de armazenamento de dados — fonte da verdade dos arquivos grandes do projeto.

Mesma filosofia dos adapters de pagamento/nota fiscal (`PaymentGateway`/`InvoiceProvider`):
um `Protocol` + adapters trocáveis por env var, nunca o provedor hardcoded num domínio.

Provedores:
- `local`  — disco local (default seguro; usado em dev/offline e como fallback).
- `gdrive` — Google Drive via Service Account (fonte da verdade oficial a partir de 2026-07-30).

## Por que existe

Antes desta camada, dados críticos viviam APENAS em máquinas locais: o espelho bruto de
clubes (583 MB), o dataset de treino, os snapshots de odds. Isso quebrou de forma concreta:
o backfill de 83 competições foi feito numa máquina e ficou inacessível de outra, e o
histórico de odds coletado no Render (`data/odds/*.jsonl`) é efêmero — some a cada deploy,
tornando impossível medir CLV (a métrica mais confiável de habilidade em apostas).

## Regra de ouro

Nenhum dado pode ter sua ÚNICA cópia numa máquina local. O diretório local é **cache
derivado e descartável** — apagar e rodar `datastore_sync.py pull` deve restaurar tudo.

Google Drive é armazenamento de ARQUIVOS, não banco: não dá `SELECT` nele. Dado que precisa
de query em runtime continua no Neon (ver `data/MANIFEST.yaml`, camada `neon`).

## Nota histórica (2026-07-30)

Este módulo usava Zoho WorkDrive (`WorkDriveStore`, `ZOHO_*`). Trocado por Google Drive antes
de qualquer credencial ter sido criada — nenhuma migração de dado foi necessária, só o adapter.
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
    """Interface mínima de armazenamento. Adapters: LocalStore, GoogleDriveStore."""

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
    exercitado de verdade (e não vire um no-op que esconde bug) — mesmo sem credencial
    do Google Drive."""

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


class GoogleDriveStore:
    """Google Drive via API REST v3 + OAuth2 (refresh token de um usuário real).

    Credenciais (env / backend/.env):
      GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REFRESH_TOKEN
      GOOGLE_DRIVE_FOLDER_ID   — pasta raiz do repositório de dados

    ATENÇÃO — por que não é Service Account: essa era a implementação original (JWT, sem
    interação humana), mas Service Account do Google **não tem cota de armazenamento
    própria** — mesmo compartilhada como Editor numa pasta normal do Meu Drive, o upload
    falha com `storageQuotaExceeded` ("Service Accounts do not have storage quota").
    Só funciona com Shared Drive (exige Google Workspace pago) ou delegando pra um usuário
    real via OAuth2 — que é o caso aqui (conta pessoal do dono). Descoberto rodando contra
    a API real em 2026-07-30 (a suíte de testes só cobria `LocalStore`).

    Passo humano único: gerar o refresh token uma vez com
    `python -m scripts.google_oauth_setup` (abre o navegador, pede consentimento, imprime
    o token) — depois disso a renovação do access token é automática.

    Nota de implementação: como o WorkDrive (adapter anterior), o Google Drive endereça
    arquivos por **id**, não por caminho, e permite nomes duplicados na mesma pasta. Este
    adapter mantém um índice caminho-lógico → id, resolvido navegando as pastas a partir de
    `GOOGLE_DRIVE_FOLDER_ID` (query `'{parent}' in parents`) e cacheado em memória por
    processo.
    """

    name = "gdrive"
    _SCOPES = "https://www.googleapis.com/auth/drive"
    _TOKEN_URL = "https://oauth2.googleapis.com/token"
    _API_BASE = "https://www.googleapis.com/drive/v3"
    _UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"

    def __init__(self) -> None:
        self.root_folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "")
        self.client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
        self.client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")
        self.refresh_token = os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN", "")
        missing = [k for k, v in {
            "GOOGLE_DRIVE_FOLDER_ID": self.root_folder_id,
            "GOOGLE_OAUTH_CLIENT_ID": self.client_id,
            "GOOGLE_OAUTH_CLIENT_SECRET": self.client_secret,
            "GOOGLE_OAUTH_REFRESH_TOKEN": self.refresh_token,
        }.items() if not v]
        if missing:
            raise RuntimeError(
                "DATA_STORE=gdrive mas faltam credenciais: " + ", ".join(missing) +
                ". Veja `python -m scripts.google_oauth_setup --help`."
            )
        self._token: Optional[str] = None
        self._folder_cache: dict[str, str] = {}

    # --- OAuth (token de acesso renovado a partir do refresh token) ----------
    def _access_token(self) -> str:
        if self._token:
            return self._token
        import httpx
        resp = httpx.post(self._TOKEN_URL, data={
            "client_id": self.client_id, "client_secret": self.client_secret,
            "refresh_token": self.refresh_token, "grant_type": "refresh_token",
        }, timeout=30)
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            raise RuntimeError(f"Google OAuth: refresh não retornou access_token: {resp.json()}")
        self._token = token
        return token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token()}"}

    # --- Navegação de pastas -------------------------------------------------
    def _children(self, folder_id: str) -> list[dict]:
        import httpx
        out: list[dict] = []
        page_token = None
        while True:
            params = {
                "q": f"'{folder_id}' in parents and trashed=false",
                "fields": "nextPageToken, files(id,name,mimeType,size)",
                "pageSize": 1000,
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if page_token:
                params["pageToken"] = page_token
            resp = httpx.get(f"{self._API_BASE}/files", headers=self._headers(),
                             params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            out.extend(data.get("files", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return out

    @staticmethod
    def _is_folder(entry: dict) -> bool:
        return entry.get("mimeType") == "application/vnd.google-apps.folder"

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
                          if c.get("name") == d and self._is_folder(c)), None)
            if found is None:
                if not create_missing:
                    raise FileNotFoundError(f"[gdrive] pasta inexistente: {d} (em {logical_path})")
                found = self._create_folder(parent, d)
            parent = found["id"]
            self._folder_cache[key] = parent
        file_entry = next((c for c in self._children(parent) if c.get("name") == filename), None)
        return parent, (file_entry.get("id") if file_entry else None)

    def _create_folder(self, parent_id: str, name: str) -> dict:
        import httpx
        resp = httpx.post(
            f"{self._API_BASE}/files",
            headers={**self._headers(), "Content-Type": "application/json"},
            params={"supportsAllDrives": "true"},
            json={"name": name, "mimeType": "application/vnd.google-apps.folder",
                  "parents": [parent_id]},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    # --- Interface DataStore -------------------------------------------------
    def list(self, prefix: str = "") -> list[RemoteFile]:
        folder_id = self.root_folder_id
        if prefix:
            folder_id, _ = self._resolve(prefix.rstrip("/") + "/_", create_missing=False)
        out: list[RemoteFile] = []
        for c in self._children(folder_id):
            if self._is_folder(c):
                continue
            out.append(RemoteFile(path=f"{prefix.rstrip('/')}/{c.get('name')}".lstrip("/"),
                                  size=int(c.get("size", 0) or 0), remote_id=c.get("id", "")))
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
        resp = httpx.get(f"{self._API_BASE}/files/{file_id}", headers=self._headers(),
                         params={"fields": "id,size", "supportsAllDrives": "true"}, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        return RemoteFile(path=logical_path, size=int(data.get("size", 0) or 0), remote_id=file_id)

    def download(self, logical_path: str, dest: Path) -> Path:
        import httpx
        _, file_id = self._resolve(logical_path)
        if not file_id:
            raise FileNotFoundError(f"[gdrive] não existe no remoto: {logical_path}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with httpx.stream("GET", f"{self._API_BASE}/files/{file_id}", headers=self._headers(),
                          params={"alt": "media", "supportsAllDrives": "true"},
                          timeout=None, follow_redirects=True) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(CHUNK):
                    f.write(chunk)
        tmp.replace(dest)   # atômico: nunca deixa arquivo pela metade no lugar do bom
        return dest

    def upload(self, src: Path, logical_path: str) -> RemoteFile:
        """Upload resumível (protocolo de 2 passos do Drive) — o arquivo é STREAMED em
        blocos de `CHUNK`, nunca lido inteiro em memória. Importante aqui: o maior dataset
        do projeto (`club_raw_cache.sqlite`) passa de 580 MB, e um multipart ingênuo que lê
        o arquivo inteiro pra montar o corpo da requisição arriscaria estourar memória."""
        import httpx
        if not src.exists():
            raise FileNotFoundError(f"[gdrive] origem não existe: {src}")
        parent_id, existing_id = self._resolve(logical_path, create_missing=True)
        name = Path(logical_path).name
        metadata = {"name": name} if existing_id else {"name": name, "parents": [parent_id]}

        url = f"{self._UPLOAD_BASE}/files" if not existing_id else f"{self._UPLOAD_BASE}/files/{existing_id}"
        method = "POST" if not existing_id else "PATCH"
        size = src.stat().st_size
        init = httpx.request(
            method, url,
            headers={**self._headers(), "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Type": "application/octet-stream",
                    "X-Upload-Content-Length": str(size)},
            params={"uploadType": "resumable", "supportsAllDrives": "true"},
            json=metadata, timeout=60,
        )
        init.raise_for_status()
        session_uri = init.headers.get("Location")
        if not session_uri:
            raise RuntimeError(f"[gdrive] upload resumível não retornou Location: {init.headers}")

        def _stream():
            with open(src, "rb") as fh:
                while chunk := fh.read(CHUNK):
                    yield chunk

        put = httpx.put(session_uri, content=_stream(),
                        headers={"Content-Length": str(size)}, timeout=None)
        put.raise_for_status()
        remote_id = put.json().get("id", existing_id or "") if put.content else (existing_id or "")
        return RemoteFile(path=logical_path, size=size, checksum=sha256_file(src), remote_id=remote_id)


def get_datastore(provider: Optional[str] = None) -> DataStore:
    """Fábrica — trocável por `DATA_STORE` (local | gdrive). Default: local."""
    name = (provider or os.environ.get("DATA_STORE") or "local").lower()
    if name == "gdrive":
        return GoogleDriveStore()
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
