"""Backup diário do banco pela API de backup do SQLite.

Copiar o arquivo .db diretamente enquanto a API grava pode gerar uma cópia inconsistente no
modo WAL; a API de backup produz uma cópia íntegra mesmo com o banco em uso.

Uso: python -m scripts.backup
Aponte PM25_BACKUP_DIR para um pendrive ou pasta sincronizada: um backup no mesmo cartão SD
do Raspberry Pi não protege contra falha do cartão.
"""

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from app import db
from app.config import get_settings


def main() -> int:
    settings = get_settings()
    if not Path(settings.db_path).exists():
        print(f"Banco não encontrado: {settings.db_path}", file=sys.stderr)
        return 1

    out_dir = Path(settings.backup_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%MZ")
    final = out_dir / f"pm25-{stamp}.db"
    partial = final.with_name(final.name + ".part")

    src = db.connect(settings.db_path, readonly=True)
    dst = sqlite3.connect(partial)
    try:
        src.backup(dst)
        check = dst.execute("PRAGMA integrity_check").fetchone()[0]
        rows = dst.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
    finally:
        dst.close()
        src.close()

    if check != "ok":
        partial.unlink(missing_ok=True)
        print(f"Backup descartado: integrity_check retornou {check!r}", file=sys.stderr)
        return 2

    partial.rename(final)
    backups = sorted(out_dir.glob("pm25-*.db"))
    for old in backups[: max(0, len(backups) - settings.backup_keep)]:
        old.unlink()
    print(f"{final} ({rows} medições); {min(len(backups), settings.backup_keep)} backups mantidos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
