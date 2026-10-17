"""Testes do alerta operacional, sem Telegram configurado: as mensagens só são impressas."""

import json

import pytest

from app import db
from app.config import get_settings
from scripts import alert_telegram


@pytest.fixture
def state_path(tmp_path, monkeypatch):
    """Banco vazio (todos os nós mudos) e Telegram desligado. Devolve o arquivo de estado dos alertas."""
    path = tmp_path / "alert_state.json"
    monkeypatch.setenv("PM25_DB_PATH", str(tmp_path / "pm25.db"))
    monkeypatch.setenv("PM25_DEVICE_TOKENS", "no-01:token-do-no-01-0000000000,no-02:token-do-no-02-0000000000,"
                                             "teste-https:token-do-teste-000000000")
    monkeypatch.setenv("PM25_ALERT_STATE", str(path))
    monkeypatch.setenv("PM25_TELEGRAM_TOKEN", "")
    monkeypatch.setenv("PM25_TELEGRAM_CHAT_ID", "")
    get_settings.cache_clear()
    conn = db.connect(str(tmp_path / "pm25.db"))
    db.init_db(conn)
    conn.close()
    yield path
    get_settings.cache_clear()


def test_alerta_ignora_dispositivo_de_teste(state_path, capsys):
    assert alert_telegram.main() == 0
    out = capsys.readouterr().out
    assert "no-01 sem enviar dados" in out
    assert "teste-https" not in out


def test_falha_no_envio_grava_o_estado_dos_avisos_anteriores(state_path, monkeypatch):
    def send(token, chat_id, text):
        if "no-02" in text:
            raise OSError("Telegram fora do ar")

    monkeypatch.setattr(alert_telegram, "send", send)
    with pytest.raises(OSError):
        alert_telegram.main()
    state = json.loads(state_path.read_text())
    assert state["no-01"]["alerting"] is True    # já avisado: não repete na próxima execução
    assert "no-02" not in state                  # não avisado: tenta de novo na próxima execução
