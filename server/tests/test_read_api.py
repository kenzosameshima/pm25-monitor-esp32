"""Testes das rotas de leitura do app de consulta e do cadastro de local dos nós."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import get_settings
from scripts import set_location

TOKEN_1 = "token-do-no-01-0000000000"
READ_TOKEN = "token-de-leitura-0000000000"
READ = {"Authorization": f"Bearer {READ_TOKEN}"}
HOUR = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


@pytest.fixture
def client(request, tmp_path, monkeypatch):
    """Cliente da API com token de leitura. Variáveis extras via parametrização indireta, como em test_api."""
    db_path = tmp_path / "pm25.db"
    monkeypatch.setenv("PM25_DB_PATH", str(db_path))
    monkeypatch.setenv("PM25_DEVICE_TOKENS", f"no-01:{TOKEN_1}")
    monkeypatch.setenv("PM25_READ_TOKEN", READ_TOKEN)
    for name, value in getattr(request, "param", {}).items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as c:
        c.db_path = db_path
        yield c
    get_settings.cache_clear()


def insert_hours(client, per_hour: list[int], pm25: list[float] | None = None, device: str = "no-01") -> None:
    """per_hour[i] leituras na hora que termina i+1 horas antes da hora cheia atual (a última é a mais recente)."""
    rows, seq = [], 0
    for i, n in enumerate(per_hour):
        hour = HOUR - timedelta(hours=len(per_hour) - i)
        for m in range(n):
            ts = hour + timedelta(minutes=m)
            rows.append({"device_id": device, "boot_id": 1, "seq": seq, "ts_sensor": db.iso(ts),
                         "ts_received": db.iso(ts), "pm1": None, "pm25": (pm25 or [10.0] * len(per_hour))[i],
                         "pm10": None, "pm25_cf1": None, "temperature": 20.0, "humidity": 60.0, "rssi": -60,
                         "uptime_s": 0, "samples": 58, "schema_version": "1", "quality": "ok"})
            seq += 1
    conn = db.connect(str(client.db_path))
    try:
        db.insert_batch(conn, device, rows, HOUR)
    finally:
        conn.close()


# ---------------------------------------------------------------- acesso

def test_leitura_exige_o_token_de_leitura(client):
    insert_hours(client, [60])
    assert client.get("/v1/devices").status_code == 401
    assert client.get("/v1/devices", headers={"Authorization": f"Bearer {TOKEN_1}"}).status_code == 401
    assert client.get("/v1/devices", headers=READ).status_code == 200


def test_token_de_leitura_nao_grava(client):
    r = client.post("/v1/measurements", headers=READ, json={"schema_version": "1", "device_id": "no-01",
                    "readings": [{"boot_id": 1, "seq": 0, "ts": db.iso(HOUR), "pm25": 1.0}]})
    assert r.status_code == 401


@pytest.mark.parametrize("client", [{"PM25_READ_TOKEN": ""}], indirect=True)
def test_sem_token_configurado_a_leitura_fica_desligada(client):
    assert client.get("/v1/devices", headers=READ).status_code == 503


@pytest.mark.parametrize("client", [{"PM25_AUTH_MAX_FAILS": "2"}], indirect=True)
def test_falhas_na_leitura_bloqueiam_o_ip(client):
    errado = {"Authorization": "Bearer errado-000000000000"}
    for _ in range(2):
        assert client.get("/v1/devices", headers=errado).status_code == 401
    r = client.get("/v1/devices", headers=errado)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    assert client.get("/v1/devices", headers=READ).status_code == 200  # o token certo passa mesmo assim


@pytest.mark.parametrize("devices, read", [
    ("no-01:TROQUE-este-token-do-no-01", ""),                 # exemplo do .env.example
    (f"no-01:{TOKEN_1}", "TROQUE-pelo-token-de-leitura"),    # exemplo do local.properties.example
])
def test_tokens_de_exemplo_do_repositorio_sao_recusados(monkeypatch, devices, read):
    monkeypatch.setenv("PM25_DEVICE_TOKENS", devices)
    monkeypatch.setenv("PM25_READ_TOKEN", read)
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="exemplo do repositório"):
        get_settings()
    get_settings.cache_clear()


@pytest.mark.parametrize("raw, message", [("curto", "muito curto"), (TOKEN_1, "repetir o token")])
def test_token_de_leitura_invalido_na_configuracao(monkeypatch, raw, message):
    monkeypatch.setenv("PM25_DEVICE_TOKENS", f"no-01:{TOKEN_1}")
    monkeypatch.setenv("PM25_READ_TOKEN", raw)
    get_settings.cache_clear()
    with pytest.raises(ValueError, match=message):
        get_settings()
    get_settings.cache_clear()


# ---------------------------------------------------------------- estado dos nós

def test_lista_de_nos_com_estado_leitura_e_local(client):
    insert_hours(client, [60, 0], pm25=[12.0, 0.0])          # última leitura há mais de uma hora
    assert set_location.main(["no-01", "Escola Exemplo, Vila Mariana", "--db", str(client.db_path)]) == 0
    body = client.get("/v1/devices", headers=READ).json()
    assert body["generated_at"].endswith("Z")
    assert body["silent_after_min"] == 15
    dev = body["devices"][0]
    assert dev["device_id"] == "no-01" and dev["location"] == "Escola Exemplo, Vila Mariana"
    assert dev["status"] == "silent"
    assert dev["minutes_since_last"] > 60
    assert dev["latest"]["pm25"] == 12.0 and dev["latest"]["pm10"] is None
    assert dev["latest"]["ts"] == db.iso(HOUR - timedelta(minutes=61))


def test_lista_vazia_sem_leituras(client):
    assert client.get("/v1/devices", headers=READ).json()["devices"] == []


def test_dispositivo_de_teste_fica_fora_do_app(client):
    insert_hours(client, [60])
    insert_hours(client, [60], device="teste-https")
    assert [d["device_id"] for d in client.get("/v1/devices", headers=READ).json()["devices"]] == ["no-01"]
    for path in ("hourly", "health", "forecast"):
        assert client.get(f"/v1/devices/teste-https/{path}", headers=READ).status_code == 404


def test_local_de_no_desconhecido_nao_e_cadastrado(client):
    assert set_location.main(["no-09", "Lugar", "--db", str(client.db_path)]) == 2


# ---------------------------------------------------------------- médias horárias

def test_horas_sem_saltos_com_validade(client):
    insert_hours(client, [60, 44, 0, 50], pm25=[10.0, 20.0, 0.0, 30.0])
    start = db.iso(HOUR - timedelta(hours=5))
    body = client.get("/v1/devices/no-01/hourly", headers=READ, params={"start": start, "end": db.iso(HOUR)}).json()
    assert body["min_readings"] == 45
    hours = body["hours"]
    assert [h["readings"] for h in hours] == [0, 60, 44, 0, 50]
    assert [h["valid"] for h in hours] == [False, True, False, False, True]
    assert [h["pm25"] for h in hours] == [None, 10.0, None, None, 30.0]
    assert hours[0]["hour"] == start


def test_inicio_e_arredondado_para_a_hora_cheia(client):
    insert_hours(client, [60])
    params = {"start": db.iso(HOUR - timedelta(minutes=50)), "end": db.iso(HOUR)}
    body = client.get("/v1/devices/no-01/hourly", headers=READ, params=params).json()
    assert body["start"] == db.iso(HOUR - timedelta(hours=1))
    assert body["hours"][0]["readings"] == 60


def test_ultimas_horas_completas_pelo_relogio_do_servidor(client):
    insert_hours(client, [60, 50])
    body = client.get("/v1/devices/no-01/hourly", headers=READ, params={"hours": 2}).json()
    assert body["end"] == db.iso(HOUR)                       # a hora em andamento fica de fora
    assert body["start"] == db.iso(HOUR - timedelta(hours=2))
    assert [h["readings"] for h in body["hours"]] == [60, 50]


def test_hours_e_start_juntos_sao_recusados(client):
    insert_hours(client, [60])
    params = {"hours": 2, "start": db.iso(HOUR - timedelta(hours=2))}
    assert client.get("/v1/devices/no-01/hourly", headers=READ, params=params).status_code == 422


@pytest.mark.parametrize("params", [
    {"start": db.iso(HOUR - timedelta(days=32)), "end": db.iso(HOUR)},        # acima de 31 dias
    {"start": db.iso(HOUR), "end": db.iso(HOUR - timedelta(hours=1))},        # fim antes do início
    {"start": "2026-10-01T12:00:00", "end": db.iso(HOUR)},                    # sem fuso
])
def test_intervalo_invalido_e_recusado(client, params):
    insert_hours(client, [60])
    assert client.get("/v1/devices/no-01/hourly", headers=READ, params=params).status_code == 422


def test_no_desconhecido_responde_404(client):
    for path in ("hourly", "health", "forecast"):
        assert client.get(f"/v1/devices/no-09/{path}", headers=READ).status_code == 404


# ---------------------------------------------------------------- saúde e previsão

def test_saude_da_coleta(client):
    insert_hours(client, [60, 60])
    body = client.get("/v1/devices/no-01/health", headers=READ, params={"hours": 3}).json()
    assert body["lost_messages"] == 0 and body["restarts"] == 0 and body["duplicates_discarded"] == 0
    since_first = (db.parse_iso(body["end"]) - (HOUR - timedelta(hours=2))).total_seconds() // 60
    assert body["completeness"] == pytest.approx(120 / since_first)  # os minutos desde a hora cheia também contam
    assert abs(body["largest_gap_min"] - (since_first - 120)) <= 1


def test_previsao_com_persistencia_e_modelo(client):
    insert_hours(client, [60, 60, 60], pm25=[10.0, 15.0, 20.0])
    conn = db.connect(str(client.db_path))
    with conn:
        for h, value in ((2, 14.0), (1, 21.0)):
            target = HOUR - timedelta(hours=h)
            conn.execute("INSERT INTO forecasts (device_id, generated_at, target_hour, predicted_pm25, model_name,"
                         " model_version) VALUES ('no-01', ?, ?, ?, 'ridge', 'v1')",
                         (db.iso(target - timedelta(minutes=5)), db.iso(target), value))
    conn.close()
    body = client.get("/v1/devices/no-01/forecast", headers=READ, params={"hours": 6}).json()
    assert body["predictors"] == ["persistence", "ridge v1"]
    last = {h["hour"]: h for h in body["hours"]}[db.iso(HOUR - timedelta(hours=1))]
    assert last["observed"] == 20.0 and last["predictions"] == {"persistence": 15.0, "ridge v1": 21.0}
    scores = {s["predictor"]: s for s in body["scores"]}
    assert scores["ridge v1"]["skill"] == pytest.approx(0.8)
    assert scores["persistence"]["mae"] == pytest.approx(5.0)


def test_parametro_fora_da_faixa_nao_vai_para_a_auditoria_da_ingestao(client):
    insert_hours(client, [60])
    assert client.get("/v1/devices/no-01/hourly", headers=READ, params={"hours": 0}).status_code == 422
    with sqlite3.connect(client.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM invalid_messages").fetchone()[0] == 0
