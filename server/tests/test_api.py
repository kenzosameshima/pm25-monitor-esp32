import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings

TOKEN_1 = "token-do-no-01-aB3xQ9zK7pLm2Wv8Rt"
TOKEN_2 = "token-do-no-02-aB3xQ9zK7pLm2Wv8Rt"
URL = "/v1/measurements"


@pytest.fixture
def client(request, tmp_path, monkeypatch):
    """Cliente da API. Variáveis de ambiente extras via parametrização indireta:
    @pytest.mark.parametrize("client", [{"PM25_AUTH_MAX_FAILS": "3"}], indirect=True)"""
    db_path = tmp_path / "pm25.db"
    monkeypatch.setenv("PM25_DB_PATH", str(db_path))
    monkeypatch.setenv("PM25_DEVICE_TOKENS", f"no-01:{TOKEN_1},no-02:{TOKEN_2}")
    for name, value in getattr(request, "param", {}).items():
        monkeypatch.setenv(name, value)
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


def test_payload_invalido_e_atribuido_ao_dono_do_token_e_nao_ao_device_id_do_corpo(client):
    sem_pm25 = reading(0)
    del sem_pm25["pm25"]
    r = post(client, [sem_pm25], token=TOKEN_1, device="no-02")
    assert r.status_code == 422
    assert count(client, "SELECT device_id FROM invalid_messages") == "no-01"


def test_json_malformado_sem_token_nao_grava_o_corpo(client):
    r = client.post(URL, content=b"{" + b"x" * 1000, headers={"Content-Type": "application/json"})
    assert r.status_code == 401
    assert count(client, "SELECT COUNT(*) FROM invalid_messages WHERE raw_payload != ''") == 0


def test_json_malformado_com_token_fica_auditado(client):
    r = client.post(URL, content=b"{xx", headers={"Content-Type": "application/json", **auth_header(TOKEN_1)})
    assert r.status_code == 422
    assert count(client, "SELECT raw_payload FROM invalid_messages") == "{xx"


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


def test_pressao_e_gravada_e_e_opcional(client):
    r = post(client, [reading(0, pressure=931.3), reading(1)])
    assert r.status_code == 201
    with sqlite3.connect(client.db_path) as conn:
        rows = conn.execute("SELECT pressure, quality FROM measurements ORDER BY seq").fetchall()
    assert rows == [(931.3, "ok"), (None, "ok")]


def test_pressao_implausivel_e_marcada(client):
    post(client, [reading(0, pressure=50.0)])
    with sqlite3.connect(client.db_path) as conn:
        assert conn.execute("SELECT quality FROM measurements").fetchone() == ("pressao_fora_faixa",)


def test_banco_anterior_ganha_a_coluna_de_pressao(tmp_path):
    from app import db

    path = tmp_path / "antigo.db"
    with sqlite3.connect(path) as conn:
        schema = db.SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript("\n".join(line for line in schema.splitlines() if "pressure" not in line))
        conn.execute("INSERT INTO devices (device_id, first_seen) VALUES ('no-01', '2026-10-09T00:00:00Z')")
        conn.execute("INSERT INTO measurements (device_id, boot_id, seq, ts_sensor, ts_received, pm25, schema_version)"
                     " VALUES ('no-01', 1, 0, '2026-10-09T00:00:00Z', '2026-10-09T00:00:00Z', 12.0, '1')")
        assert "pressure" not in {r[1] for r in conn.execute("PRAGMA table_info(measurements)")}
    conn = db.connect(str(path))
    try:
        db.init_db(conn)
        db.init_db(conn)  # rodar de novo não muda nada
        assert conn.execute("SELECT pm25, pressure FROM measurements").fetchone()[:] == (12.0, None)
    finally:
        conn.close()


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
        row = conn.execute("SELECT temperature, pressure, rssi, quality FROM measurements WHERE seq = 1").fetchone()
    assert row == (None, None, None, "ok")
    assert stored_firmware(client) == ["build Oct 26 2026 12:00:00"]


# ---------------- versão do firmware: campo opcional que nunca pode custar leituras ----------------

def post_with_firmware(client, firmware):
    body = {"schema_version": "1", "device_id": "no-01", "readings": [reading(0)], "firmware": firmware}
    return client.post(URL, json=body, headers={"Authorization": f"Bearer {TOKEN_1}"})


def stored_firmware(client):
    with sqlite3.connect(client.db_path) as conn:
        return [r[0] for r in conn.execute("SELECT firmware FROM ingest_batches ORDER BY id")]


def test_lote_guarda_a_versao_do_firmware(client):
    assert post_with_firmware(client, "build Oct 26 2026 12:00:00").status_code == 201
    assert stored_firmware(client) == ["build Oct 26 2026 12:00:00"]


def test_lote_sem_versao_do_firmware_continua_valido(client):
    assert post(client, [reading(0)]).status_code == 201
    assert stored_firmware(client) == [None]


@pytest.mark.parametrize("sent, kept", [
    (123, None), ("", None), ("   ", None), (["x"], None),       # não é um texto útil: ignorado
    ("x" * 500, "x" * 64),                                         # comprido demais: cortado
    ("a\x00b\nc", "abc"),                                          # caracteres de controle: removidos
])
def test_versao_do_firmware_invalida_nao_derruba_o_lote(client, sent, kept):
    """O nó descarta lote recusado com 4xx; um campo só de diagnóstico não pode causar isso."""
    assert post_with_firmware(client, sent).status_code == 201
    assert count(client, "SELECT COUNT(*) FROM measurements") == 1
    assert stored_firmware(client) == [kept]


# ---------------- API exposta na internet: corpo, autenticação uniforme e bloqueio por IP ----------------

LIMITE_PEQUENO = {"PM25_MAX_BODY_BYTES": "2000"}
TRES_FALHAS = {"PM25_AUTH_MAX_FAILS": "3", "PM25_AUTH_BLOCK_MIN": "5"}


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("client", [LIMITE_PEQUENO], indirect=True)
def test_corpo_acima_do_limite_retorna_413_sem_gravar(client):
    r = post(client, [reading(i, minutes_ago=100 - i) for i in range(30)])  # ~7 KB > 2000 bytes
    assert r.status_code == 413
    assert count(client, "SELECT COUNT(*) FROM measurements") == 0
    assert count(client, "SELECT COUNT(*) FROM ingest_batches") == 0
    # abaixo do limite continua aceito
    assert post(client, [reading(0)]).status_code == 201


@pytest.mark.parametrize("client", [LIMITE_PEQUENO], indirect=True)
def test_corpo_em_partes_acima_do_limite_retorna_413(client):
    """Sem Content-Length (envio em partes) o limite também vale, contando os bytes recebidos."""
    def partes():
        for _ in range(10):
            yield b" " * 500

    r = client.post(URL, content=partes(), headers=auth_header(TOKEN_1))
    assert r.status_code == 413
    assert count(client, "SELECT COUNT(*) FROM measurements") == 0


def test_token_ausente_e_invalido_recebem_a_mesma_resposta(client):
    body = {"schema_version": "1", "device_id": "no-01", "readings": [reading(0)]}
    ausente = client.post(URL, json=body)
    invalido = post(client, [reading(0)], token="token-inexistente-000000")
    outro_esquema = client.post(URL, json=body, headers={"Authorization": f"Basic {TOKEN_1}"})
    assert ausente.status_code == invalido.status_code == outro_esquema.status_code == 401
    assert ausente.json() == invalido.json() == outro_esquema.json()
    assert ausente.headers["www-authenticate"] == "Bearer"


def test_tentativa_invalida_fica_auditada_sem_gravar_o_token(client):
    token_errado = "token-inexistente-000000"
    post(client, [reading(0)], token=token_errado)
    client.post(URL, json={"schema_version": "1", "device_id": "no-01", "readings": [reading(0)]})
    assert count(client, "SELECT COUNT(*) FROM invalid_messages") == 2
    with sqlite3.connect(client.db_path) as conn:
        linhas = conn.execute("SELECT remote_addr, reason, raw_payload FROM invalid_messages").fetchall()
    assert all(addr == "testclient" for addr, _, _ in linhas)
    assert not any(token_errado in str(campo) for linha in linhas for campo in linha)
    assert not any(TOKEN_1 in str(campo) for linha in linhas for campo in linha)


def test_device_id_incompativel_com_o_token_nao_grava_o_token(client):
    r = post(client, [reading(0)], token=TOKEN_1, device="no-02")
    assert r.status_code == 403
    with sqlite3.connect(client.db_path) as conn:
        (reason, raw), = conn.execute("SELECT reason, raw_payload FROM invalid_messages").fetchall()
    assert "no-02" in reason and "no-01" in reason
    assert TOKEN_1 not in raw


@pytest.mark.parametrize("client", [TRES_FALHAS], indirect=True)
def test_bloqueio_por_ip_apos_n_falhas_nao_afeta_outro_ip(client):
    for _ in range(3):
        assert post(client, [reading(0)], token="token-inexistente-000000").status_code == 401
    bloqueado = post(client, [reading(0)], token="token-inexistente-000000")
    assert bloqueado.status_code == 429
    assert 0 < int(bloqueado.headers["retry-after"]) <= 300
    assert count(client, "SELECT COUNT(*) FROM measurements") == 0
    assert count(client, "SELECT COUNT(*) FROM invalid_messages") == 3  # o 429 não escreve no banco

    outro_ip = TestClient(client.app, client=("203.0.113.9", 40000))
    r = outro_ip.post(URL, json={"schema_version": "1", "device_id": "no-01", "readings": [reading(0)]},
                      headers=auth_header(TOKEN_1))
    assert r.status_code == 201


@pytest.mark.parametrize("client", [TRES_FALHAS], indirect=True)
def test_token_correto_passa_com_o_ip_bloqueado(client):
    """Quem divide o IP com um nó não consegue tirá-lo do ar errando o token de propósito."""
    for _ in range(3):
        post(client, [reading(0)], token="token-inexistente-000000")
    assert post(client, [reading(0)], token="token-inexistente-000000").status_code == 429
    assert post(client, [reading(0)]).status_code == 201
    assert count(client, "SELECT COUNT(*) FROM measurements") == 1


@pytest.mark.parametrize("client", [TRES_FALHAS], indirect=True)
def test_autenticacao_valida_nao_zera_a_contagem_de_falhas(client):
    for _ in range(2):
        post(client, [reading(0)], token="token-inexistente-000000")
    assert post(client, [reading(0)]).status_code == 201          # não zera as 2 falhas
    assert post(client, [reading(1)], token="token-inexistente-000000").status_code == 401  # 3ª falha: bloqueia
    assert post(client, [reading(1)], token="token-inexistente-000000").status_code == 429


@pytest.mark.parametrize("client", [TRES_FALHAS], indirect=True)
def test_device_id_incompativel_nao_conta_como_falha_de_autenticacao(client):
    for _ in range(5):
        assert post(client, [reading(0)], token=TOKEN_1, device="no-02").status_code == 403
    assert post(client, [reading(0)]).status_code == 201


def test_falhas_antigas_expiram_com_a_janela():
    from app.guard import AuthThrottle

    agora = [1000.0]
    t = AuthThrottle(max_fails=3, block_s=300, clock=lambda: agora[0])
    t.register_failure("1.1.1.1")
    t.register_failure("1.1.1.1")
    agora[0] += 301                    # as duas falhas saem da janela
    t.register_failure("1.1.1.1")
    t.register_failure("1.1.1.1")
    assert t.retry_after("1.1.1.1") == 0
    t.register_failure("1.1.1.1")      # 3 falhas dentro da mesma janela
    assert t.retry_after("1.1.1.1") == 300


def test_bloqueio_expira_e_o_contador_recomeca():
    from app.guard import AuthThrottle

    agora = [1000.0]
    t = AuthThrottle(max_fails=2, block_s=300, clock=lambda: agora[0])
    t.register_failure("1.1.1.1")
    assert t.retry_after("1.1.1.1") == 0
    t.register_failure("1.1.1.1")
    assert t.retry_after("1.1.1.1") == 300
    assert t.retry_after("2.2.2.2") == 0
    agora[0] += 299
    assert t.retry_after("1.1.1.1") > 0
    agora[0] += 2
    assert t.retry_after("1.1.1.1") == 0
    t.register_failure("1.1.1.1")                 # contagem recomeçou: uma falha não bloqueia
    assert t.retry_after("1.1.1.1") == 0
