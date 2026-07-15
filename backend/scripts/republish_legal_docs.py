"""One-off: republica os 5 documentos legais com o conteúdo atualizado de
`app/domains/legal/service.py::_DEFAULTS` (nova versão vigente, exige novo aceite).
Uso: cd backend && .venv/Scripts/python -m scripts.republish_legal_docs
"""
from __future__ import annotations

from app.db.models import Base  # noqa: F401  (importa todos os modelos p/ resolver FKs)
from app.db.connection import SessionLocal
from app.domains.legal import service
from app.domains.legal.models import LegalDocument
from sqlalchemy import select


def main() -> None:
    db = SessionLocal()
    try:
        service.seed_default_documents(db)  # garante que existam linhas antes de republicar
        for dtype, (title, body) in service._DEFAULTS.items():
            current = db.execute(
                select(LegalDocument).where(LegalDocument.type == dtype, LegalDocument.is_current.is_(True))
            ).scalar_one_or_none()
            if current is not None and current.title == title and current.body_md == body:
                print(f"[skip] {dtype.value}: já está com o conteúdo atual (v{current.version}).")
                continue
            doc = service.publish(db, dtype.value, title, body, admin_id=None)
            print(f"[ok] {dtype.value}: publicado v{doc.version}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
