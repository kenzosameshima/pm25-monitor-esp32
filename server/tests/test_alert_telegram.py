"""Testes do alerta operacional, sem Telegram configurado: as mensagens só são impressas."""

from app import db
from app.config import get_settings
from scripts import alert_telegram


def test_alerta_ignora_dispositivo_de_teste(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PM25_DB_PATH", str(tmp_path / "pm25.db"))
    monkeypatch.setenv("PM25_DEVICE_TOKENS", "no-01:token-do-no-01-0000000000,teste-https:token-do-teste-000000000")
    monkeypatch.setenv("PM25_ALERT_STATE", str(tmp_path / "alert_state.json"))
    monkeypatch.setenv("PM25_TELEGRAM_TOKEN", "")
    monkeypatch.setenv("PM25_TELEGRAM_CHAT_ID", "")
    get_settings.cache_clear()
    conn = db.connect(str(tmp_path / "pm25.db"))
    db.init_db(conn)
    conn.close()
    try:
        assert alert_telegram.main() == 0
    finally:
        get_settings.cache_clear()
    out = capsys.readouterr().out
    assert "no-01 sem enviar dados" in out
    assert "teste-https" not in out
