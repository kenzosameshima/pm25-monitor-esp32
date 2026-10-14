"""Grava o local de instalação de um nó, mostrado no dashboard e no app de consulta.

Uso: python -m scripts.set_location no-01 "EE Exemplo, Vila Mariana (fachada, 3 m do chão)"
     python -m scripts.set_location no-01 --clear
O nó precisa já ter enviado alguma leitura: é a primeira ingestão que o cadastra no banco.
"""

import argparse
import sys
from pathlib import Path

from app import db
from app.config import get_settings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("device_id")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("location", nargs="?", help="descrição do local (bairro, ponto, altura)")
    group.add_argument("--clear", action="store_true", help="apaga o local cadastrado")
    ap.add_argument("--db", default=None, help="caminho do banco (padrão: PM25_DB_PATH)")
    args = ap.parse_args(argv)

    path = args.db or get_settings().db_path
    if not Path(path).exists():
        print(f"Banco não encontrado: {path}", file=sys.stderr)
        return 1
    location = None if args.clear else args.location.strip() or None
    conn = db.connect(path)
    try:
        found = db.set_location(conn, args.device_id, location)
    finally:
        conn.close()
    if not found:
        print(f"{args.device_id} ainda não enviou leituras; ligue o nó e tente de novo", file=sys.stderr)
        return 2
    print(f"{args.device_id}: {location or '(sem local)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
