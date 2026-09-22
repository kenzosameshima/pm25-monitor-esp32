import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings

TOKEN_1 = "token-do-no-01-0000000000"
TOKEN_2 = "token-do-no-02-0000000000"
URL = "/v1/measurements"


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "pm25.db"
    monkeypatch.setenv("PM25_DB_PATH", str(db_path))
    monkeypatch.setenv("PM25_DEVICE_TOKENS", f"no-01:{TOKEN_1},no-02:{TOKEN_2}")
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as c:
        c.db_path = db_path
        yield c
    get_settings.cache_clear()


def reading(seq, boot_id=1, minutes_ago=10, **extra):
    ts = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=minutes_ago)
    base = {"boot_id": boot_id, "seq": seq, "ts": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "pm25": 12.5, "pm1": 8.0, "pm10": 15.0, "pm25_cf1": 13.1,
            "temperature": 24.0, "humidity": 60.0, "rssi": -60, "uptime_s": 600, "samples": 58}
    base.update(extra)
    return base


def post(client, readings, token=TOKEN_1, device="no-01"):
    return client.post(URL, json={"schema_version": "1", "device_id": device, "readings": readings},
                       headers={"Authorization": f"Bearer {token}"})


def count(client, sql):
    with sqlite3.connect(client.db_path) as conn:
        return conn.execute(sql).fetchone()[0]


def test_lote_e_gravado_e_confirmado_com_201(client):
    r = post(client, [reading(0, minutes_ago=2), reading(1, minutes_ago=1)])
    assert r.status_code == 201
    assert r.json() == {"inserted": 2, "duplicates": 0}
    assert count(client, "SELECT COUNT(*) FROM measurements") == 2


def test_reenvio_do_mesmo_lote_e_idempotente(client):
    lote = [reading(0, minutes_ago=2), reading(1, minutes_ago=1)]
    post(client, lote)
    r = post(client, lote)
    assert r.status_code == 201
    assert r.json() == {"inserted": 0, "duplicates": 2}
    assert count(client, "SELECT COUNT(*) FROM measurements") == 2
    assert count(client, "SELECT SUM(n_duplicates) FROM ingest_batches") == 2


def test_reinicio_do_no_nao_colide_com_leituras_antigas(client):
    """seq recomeça do zero após um reinício; o boot_id novo evita descartar leituras legítimas."""
    post(client, [reading(0, boot_id=1, minutes_ago=5), reading(1, boot_id=1, minutes_ago=4)])
    r = post(client, [reading(0, boot_id=2, minutes_ago=2), reading(1, boot_id=2, minutes_ago=1)])
    assert r.json() == {"inserted": 2, "duplicates": 0}
    assert count(client, "SELECT COUNT(*) FROM measurements") == 4


def test_mesma_seq_em_dispositivos_diferentes(client):
    post(client, [reading(0)])
    r = post(client, [reading(0)], token=TOKEN_2, device="no-02")
    assert r.json()["inserted"] == 1


def test_sem_token_ou_token_errado_retorna_401(client):
    body = {"schema_version": "1", "device_id": "no-01", "readings": [reading(0)]}
    assert client.post(URL, json=body).status_code == 401
    assert post(client, [reading(0)], token="token-inexistente-000000").status_code == 401
    assert count(client, "SELECT COUNT(*) FROM measurements") == 0


def test_device_id_de_outro_no_retorna_403_e_fica_auditado(client):
    r = post(client, [reading(0)], token=TOKEN_1, device="no-02")
    assert r.status_code == 403
    assert count(client, "SELECT COUNT(*) FROM invalid_messages") == 1
    assert count(client, "SELECT COUNT(*) FROM measurements") == 0


def test_payload_fora_do_contrato_retorna_422_e_fica_auditado(client):
    sem_pm25 = reading(0)
    del sem_pm25["pm25"]
    r = post(client, [sem_pm25])
    assert r.status_code == 422
    assert count(client, "SELECT COUNT(*) FROM invalid_messages") == 1
    assert count(client, "SELECT device_id FROM invalid_messages") == "no-01"


def test_horario_sem_fuso_e_rejeitado(client):
    r = post(client, [reading(0, ts="2026-09-22T12:00:00")])
    assert r.status_code == 422


def test_valores_implausiveis_sao_gravados_com_marcacao(client):
    r = post(client, [reading(0, humidity=120.0), reading(1, pm25=5000.0)])
    assert r.status_code == 201
    with sqlite3.connect(client.db_path) as conn:
        flags = [q for (q,) in conn.execute("SELECT quality FROM measurements ORDER BY seq")]
    assert flags == ["umid_fora_faixa", "pm25_fora_faixa"]


def test_campos_opcionais_podem_ser_nulos(client):
    r = post(client, [reading(0, temperature=None, humidity=None, rssi=None, pm1=None)])
    assert r.status_code == 201


def test_tabela_bruta_e_imutavel(client):
    post(client, [reading(0)])
    with sqlite3.connect(client.db_path) as conn:
        with pytest.raises(sqlite3.DatabaseError, match="imutável"):
            conn.execute("UPDATE measurements SET pm25 = 0")
        with pytest.raises(sqlite3.DatabaseError, match="imutável"):
            conn.execute("DELETE FROM measurements")


def test_lote_acima_do_limite_e_rejeitado(client):
    r = post(client, [reading(i, minutes_ago=600 - i) for i in range(501)])
    assert r.status_code == 422


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_banco_em_modo_wal(client):
    with sqlite3.connect(client.db_path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_contrato_payload_gerado_pelo_firmware_e_aceito(client):
    """O JSON vem de firmware/host_tests (buildPayload); garante que firmware e API falam o mesmo contrato."""
    import json
    from pathlib import Path

    payload = json.loads((Path(__file__).parent / "fixtures" / "payload_firmware.json").read_text())
    r = client.post(URL, json=payload, headers={"Authorization": f"Bearer {TOKEN_1}"})
    assert r.status_code == 201, r.text
    assert r.json() == {"inserted": 2, "duplicates": 0}
    with sqlite3.connect(client.db_path) as conn:
        row = conn.execute("SELECT temperature, rssi, quality FROM measurements WHERE seq = 1").fetchone()
    assert row == (None, None, "ok")
