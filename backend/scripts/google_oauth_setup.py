#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
scripts/google_oauth_setup.py — obtém o refresh token do Google Drive (passo único).
======================================================================================

`app/core/datastore.py::GoogleDriveStore` autentica como um USUÁRIO REAL via OAuth2, não
como Service Account — Service Account não tem cota de armazenamento própria e o upload
falha com `storageQuotaExceeded` numa pasta comum do Meu Drive (só funciona com Shared
Drive, que exige Google Workspace pago). Ver docstring de `GoogleDriveStore` para o
histórico completo dessa descoberta (2026-07-30).

## Pré-requisito (uma vez, no Google Cloud Console)

1. https://console.cloud.google.com/apis/credentials (mesmo projeto onde a Drive API já
   está ativada) → **Create Credentials → OAuth client ID**
2. Tipo de aplicativo: **Desktop app** (não "Web application" — o tipo Desktop aceita
   qualquer porta localhost automaticamente, sem precisar registrar a URL de redirect)
3. Anote o **Client ID** e o **Client Secret**.
4. Se pedir "OAuth consent screen": tipo **External**, adicione seu próprio e-mail como
   "test user" (não precisa publicar o app).

## Uso

  python -m scripts.google_oauth_setup --client-id SEU_ID --client-secret SEU_SECRET

Abre uma URL pra você colar no navegador (não consigo abrir por você). Depois de você
aceitar, um servidor local nesta máquina recebe o retorno automaticamente e imprime o
refresh token — cole em `backend/.env`:

  GOOGLE_OAUTH_CLIENT_ID=...
  GOOGLE_OAUTH_CLIENT_SECRET=...
  GOOGLE_OAUTH_REFRESH_TOKEN=...   (impresso por este script)
"""
from __future__ import annotations

import argparse
import http.server
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCOPE = "https://www.googleapis.com/auth/drive"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

_captured: dict = {}


def _make_handler():
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):  # silencia o log padrão do http.server
            pass

        def do_GET(self):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            _captured["code"] = qs.get("code", [None])[0]
            _captured["error"] = qs.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Autorizado! Pode fechar esta aba." if _captured.get("code") else \
                  f"Erro: {_captured.get('error')}. Pode fechar esta aba."
            self.wfile.write(f"<html><body><h2>{msg}</h2></body></html>".encode("utf-8"))
    return Handler


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--client-id", required=True)
    ap.add_argument("--client-secret", required=True)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="não tenta abrir o navegador sozinho")
    a = ap.parse_args()

    redirect_uri = f"http://localhost:{a.port}/"
    params = {
        "client_id": a.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",   # pede refresh_token, não só access_token
        "prompt": "consent",        # força emitir refresh_token mesmo se já autorizou antes
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)

    print("=" * 78)
    print(" AUTORIZACAO GOOGLE DRIVE -- passo unico")
    print("=" * 78)
    print(f"\nAbra esta URL no seu navegador (logado na conta do Drive certa):\n\n{url}\n")

    server = http.server.HTTPServer(("localhost", a.port), _make_handler())
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()

    if not a.no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    print(f"Aguardando retorno em {redirect_uri} (até você autorizar no navegador)...")
    t.join(timeout=300)
    server.server_close()

    if not _captured.get("code"):
        print(f"\nNão recebi o código (erro: {_captured.get('error')}). Tente de novo.")
        raise SystemExit(1)

    import httpx
    resp = httpx.post(TOKEN_URL, data={
        "code": _captured["code"], "client_id": a.client_id, "client_secret": a.client_secret,
        "redirect_uri": redirect_uri, "grant_type": "authorization_code",
    }, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    refresh_token = data.get("refresh_token")

    if not refresh_token:
        print("\n[AVISO] resposta não trouxe refresh_token -- provavelmente você já tinha")
        print("autorizado este app antes. Revogue o acesso em")
        print("https://myaccount.google.com/permissions e rode este script de novo.")
        print(f"\nResposta completa: {data}")
        raise SystemExit(1)

    print("\n" + "=" * 78)
    print(" SUCESSO -- cole isto em backend/.env:")
    print("=" * 78)
    print(f"GOOGLE_OAUTH_CLIENT_ID={a.client_id}")
    print(f"GOOGLE_OAUTH_CLIENT_SECRET={a.client_secret}")
    print(f"GOOGLE_OAUTH_REFRESH_TOKEN={refresh_token}")


if __name__ == "__main__":
    main()
