"""Alerta operacional: avisa no Telegram quando um sensor para de enviar dados e quando volta.

Rode a cada 5 minutos (cron). Sem PM25_TELEGRAM_TOKEN configurado, só imprime as mensagens.
O estado dos alertas fica num arquivo JSON, para o banco continuar com um único processo escritor.

Uso: python -m scripts.alert_telegram
"""

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import db
from app.config import get_settings

BRT = timezone(timedelta(hours=-3), "BRT")


def fmt(dt: datetime | None) -> str:
    return dt.astimezone(BRT).strftime("%d/%m %H:%M") if dt else "nunca"


def send(token: str, chat_id: str, text: str) -> None:
    if not token or not chat_id:
        print(f"[simulação] {text}")
        return
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    with urllib.request.urlopen(url, data=data, timeout=15) as resp:
        resp.read()


def main() -> int:
    s = get_settings()
    state_path = Path(s.alert_state_path)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    now = datetime.now(timezone.utc)
    limit = timedelta(minutes=s.alert_silence_min)

    if Path(s.db_path).exists():
        conn = db.connect(s.db_path, readonly=True)
        try:
            last = db.last_seen(conn, s.device_ids)
        finally:
            conn.close()
    else:
        last = {}

    for device in s.device_ids:
        seen = last.get(device)
        silent = seen is None or now - seen > limit
        alerting = state.get(device, {}).get("alerting", False)
        if silent and not alerting:
            send(s.telegram_token, s.telegram_chat_id,
                 f"⚠️ {device} sem enviar dados há mais de {s.alert_silence_min} min "
                 f"(último recebimento: {fmt(seen)}).")
            state[device] = {"alerting": True, "since": db.iso(now)}
        elif not silent and alerting:
            since = datetime.fromisoformat(state[device]["since"].replace("Z", "+00:00"))
            send(s.telegram_token, s.telegram_chat_id,
                 f"✅ {device} voltou a enviar dados (alerta aberto às {fmt(since)}).")
            state[device] = {"alerting": False}

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
