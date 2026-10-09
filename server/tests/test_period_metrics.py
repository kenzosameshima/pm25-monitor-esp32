"""Testes das métricas do período com bancos sintéticos pequenos, montados a mão.

Cenário-base: um dia de Brasília (2026-09-01, terça-feira; 03:00Z a 03:00Z do dia seguinte) com uma leitura
por minuto, seq contínuo e boot_id 1. Cada teste remove ou altera minutos conhecidos, então os números
esperados saem de contas simples (1 440 minutos por dia, 1 410 = 1 440 - 30, etc.).
"""

import hashlib
import json
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from app import db
from scripts import period_metrics as pmx

DAY0 = datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc)  # 00:00 em Brasília
DAY = date(2026, 9, 1)


def plan(first=0, last=None, acq=(), lost=(), down=(), pm25=lambda m: 10.0, days=1):
    """Leituras (minuto, boot_id, seq, pm25). `acq`: minutos sem leitura e sem consumir seq (sensor mudo);
    `lost`: minutos cuja mensagem se perdeu (consomem seq); `down`: minutos desligado, com novo boot_id depois."""
    out, boot, seq, reboot = [], 1, 0, False
    for m in range(first, (days * 1440 - 1 if last is None else last) + 1):
        if m in down:
            reboot = True
            continue
        if reboot:
            boot, seq, reboot = boot + 1, 0, False
        if m in acq:
            continue
        if m in lost:
            seq += 1
            continue
        out.append((m, boot, seq, pm25(m)))
        seq += 1
    return out


def insert(conn, device, readings, rssi=lambda m: -60, received_at=None):
    rows = []
    for m, boot, seq, value in readings:
        ts = db.iso(DAY0 + timedelta(minutes=m))
        rows.append({"device_id": device, "boot_id": boot, "seq": seq, "ts_sensor": ts, "ts_received": ts,
                     "pm1": None, "pm25": value, "pm10": None, "pm25_cf1": None, "temperature": 20.0,
                     "humidity": 60.0, "rssi": rssi(m), "uptime_s": 0, "samples": 58, "schema_version": "1",
                     "quality": "ok"})
    return db.insert_batch(conn, device, rows, received_at or DAY0 + timedelta(hours=1))


@pytest.fixture
def conn(tmp_path):
    c = db.connect(str(tmp_path / "pm25.db"))
    db.init_db(c)
    yield c
    c.close()


def node(conn, tmp_path, device="no-01", start=DAY, end=DAY):
    """Roda o cálculo sobre o banco do teste e devolve o bloco do nó."""
    db_file = conn.execute("PRAGMA database_list").fetchone()["file"]
    report = pmx.run(db_file, start, end, tmp_path / "saida", None, freeze=False)
    return report["nos"][device]


def test_limites_do_periodo_em_brasilia():
    start, end, days = pmx.period_bounds(date(2026, 9, 1), date(2026, 9, 2))
    assert (start, end, days) == (DAY0, DAY0 + timedelta(days=2), 2)
    with pytest.raises(ValueError):
        pmx.period_bounds(date(2026, 9, 2), date(2026, 9, 1))


def test_dia_completo(conn, tmp_path):
    insert(conn, "no-01", plan())
    op = node(conn, tmp_path)["operacional"]
    assert (op["minutos_com_leitura"], op["completude"], op["maior_lacuna_min"]) == (1440, 1.0, 0)
    assert op["mensagens_perdidas"] == op["reinicios"] == 0
    assert op["lacunas_min"] == {"comunicacao": 0, "aquisicao": 0, "reinicio": 0, "bordas": 0, "total": 0}


def test_lacuna_de_aquisicao_minutos_sem_leitura_e_sem_salto_de_seq(conn, tmp_path):
    insert(conn, "no-01", plan(acq=range(600, 630)))  # 30 minutos mudos
    op = node(conn, tmp_path)["operacional"]
    assert op["minutos_com_leitura"] == 1410
    assert op["completude"] == round(1410 / 1440, 4) == 0.9792
    assert op["maior_lacuna_min"] == 30
    assert op["lacunas_min"] == {"comunicacao": 0, "aquisicao": 30, "reinicio": 0, "bordas": 0, "total": 30}
    assert op["mensagens_perdidas"] == 0 and op["reinicios"] == 0


def test_lacuna_de_comunicacao_salto_de_seq_na_mesma_inicializacao(conn, tmp_path):
    insert(conn, "no-01", plan(lost=range(200, 210)))  # 10 mensagens perdidas
    op = node(conn, tmp_path)["operacional"]
    assert op["minutos_com_leitura"] == 1430
    assert op["mensagens_perdidas"] == 10
    assert op["maior_lacuna_min"] == 10
    assert op["lacunas_min"] == {"comunicacao": 10, "aquisicao": 0, "reinicio": 0, "bordas": 0, "total": 10}


def test_lacuna_de_reinicio_mudanca_de_boot_id(conn, tmp_path):
    insert(conn, "no-01", plan(down=range(300, 305)))  # 5 minutos desligado; boot 2 recomeça com seq 0
    op = node(conn, tmp_path)["operacional"]
    assert op["minutos_com_leitura"] == 1435
    assert op["reinicios"] == 1
    assert op["mensagens_perdidas"] == 0               # o seq recomeçar do zero não é perda
    assert op["lacunas_min"] == {"comunicacao": 0, "aquisicao": 0, "reinicio": 5, "bordas": 0, "total": 5}


def test_bordas_do_periodo_ficam_fora_da_classificacao_mas_dentro_da_completude(conn, tmp_path):
    insert(conn, "no-01", plan(first=60, last=1379))  # nó instalado às 01:00 e parado às 22:59
    op = node(conn, tmp_path)["operacional"]
    assert op["minutos_com_leitura"] == 1320
    assert op["maior_lacuna_min"] == 60
    assert op["lacunas_min"] == {"comunicacao": 0, "aquisicao": 0, "reinicio": 0, "bordas": 120, "total": 120}


def test_origens_somam_os_minutos_faltantes(conn, tmp_path):
    insert(conn, "no-01", plan(acq=range(100, 110), lost=range(400, 405), down=range(700, 703)))
    op = node(conn, tmp_path)["operacional"]
    assert op["lacunas_min"] == {"comunicacao": 5, "aquisicao": 10, "reinicio": 3, "bordas": 0, "total": 18}
    assert op["minutos_com_leitura"] == 1440 - 18
    assert op["maior_lacuna_min"] == 10
    assert op["mensagens_perdidas"] == 5 and op["reinicios"] == 1


def test_duplicatas_e_rssi_medio(conn, tmp_path):
    leituras = plan(last=59)
    insert(conn, "no-01", leituras, rssi=lambda m: -60 if m % 2 == 0 else -70)
    inserted, duplicates = insert(conn, "no-01", leituras)  # reenvio do mesmo lote
    assert (inserted, duplicates) == (0, 60)
    op = node(conn, tmp_path)["operacional"]
    assert op["duplicatas_descartadas"] == 60
    assert op["rssi_medio_dbm"] == -65.0


@pytest.mark.parametrize("presentes, hora_valida", [(44, False), (45, True)])
def test_hora_com_menos_de_45_leituras_e_tratada_como_ausente(conn, tmp_path, presentes, hora_valida):
    # Hora 5 de Brasília (minutos 300 a 359) vale 100 µg/m³; as outras 23 horas valem 10.
    value = lambda m: 100.0 if 300 <= m < 360 else 10.0
    insert(conn, "no-01", plan(acq=range(300 + presentes, 360), pm25=value))
    pm = node(conn, tmp_path)["pm25"]
    if hora_valida:
        assert pm["horas_validas"] == 24 and pm["maximo_horario"] == 100.0
    else:
        assert pm["horas_validas"] == 23 and pm["maximo_horario"] == 10.0 and pm["media"] == 10.0
    assert pm["horas_esperadas"] == 24


def test_estatisticas_e_perfis_com_horas_de_1_a_24(conn, tmp_path):
    insert(conn, "no-01", plan(pm25=lambda m: float(m // 60 + 1)))  # a hora k de Brasília vale k + 1
    pm = node(conn, tmp_path)["pm25"]
    assert pm["horas_validas"] == 24
    assert pm["media"] == 12.5 and pm["mediana"] == 12.5 and pm["maximo_horario"] == 24.0
    # interpolação linear na posição 0,05 * 23 = 1,15 (entre 2 e 3) e 0,95 * 23 = 21,85 (entre 22 e 23)
    assert pm["p5"] == 2.15 and pm["p95"] == 22.85
    assert pm["desvio_padrao"] == round(math.sqrt(50), 4)    # variância amostral de 1..24 = 50

    por_hora = pd.read_csv(tmp_path / "saida" / "perfil_hora.csv")
    assert list(por_hora["hora"]) == list(range(24)) and list(por_hora["media"]) == [float(k + 1) for k in range(24)]
    por_dia = pd.read_csv(tmp_path / "saida" / "perfil_dia_semana.csv")
    assert por_dia.to_dict("records") == [{"device_id": "no-01", "dia_semana": "terça", "n": 24, "media": 12.5}]


def test_frequencia_acima_das_diretrizes(conn, tmp_path):
    insert(conn, "no-01", plan(pm25=lambda m: float(m // 60 + 1)))  # horas 1..24, média do dia 12,5
    ref = node(conn, tmp_path)["pm25"]["referencias"]
    oms = ref["OMS 2021 nível-guia (15)"]
    assert oms["limite_ug_m3"] == 15.0
    assert oms["horas"] == {"acima": 9, "total": 24, "fracao": 0.375}      # horas de 16 a 24
    assert oms["medias_24h"] == {"acima": 0, "total": 1, "fracao": 0.0}    # 12,5 não passa de 15
    assert ref["CONAMA 506/2024 PI-2 (50, em vigor desde 2025)"]["horas"]["acima"] == 0


def test_media_de_24h_acima_do_nivel_guia(conn, tmp_path):
    insert(conn, "no-01", plan(pm25=lambda m: 20.0))
    ref = node(conn, tmp_path)["pm25"]["referencias"]
    assert ref["OMS 2021 nível-guia (15)"]["medias_24h"] == {"acima": 1, "total": 1, "fracao": 1.0}
    assert ref["CONAMA 506/2024 PF (15)"]["horas"]["acima"] == 24
    assert ref["OMS 2021 meta intermediária 4 (25)"]["medias_24h"]["acima"] == 0


@pytest.mark.parametrize("horas_validas, dias", [(17, 0), (18, 1)])
def test_dia_precisa_de_18_horas_validas_para_ter_media_de_24h(conn, tmp_path, horas_validas, dias):
    insert(conn, "no-01", plan(acq=range(horas_validas * 60, 1440)))
    pm = node(conn, tmp_path)["pm25"]
    assert pm["horas_validas"] == horas_validas
    assert pm["dias_validos_24h"] == dias


def test_completude_diaria_em_csv(conn, tmp_path):
    # Dois dias; no segundo faltam 144 minutos (10%) em aquisição.
    insert(conn, "no-01", plan(days=2, acq=range(1440 + 100, 1440 + 244)), received_at=DAY0)
    node(conn, tmp_path, end=DAY + timedelta(days=1))
    diaria = pd.read_csv(tmp_path / "saida" / "completude_diaria.csv")
    assert diaria.to_dict("records") == [
        {"device_id": "no-01", "data": "2026-09-01", "leituras": 1440, "esperadas": 1440, "completude": 1.0},
        {"device_id": "no-01", "data": "2026-09-02", "leituras": 1296, "esperadas": 1440, "completude": 0.9},
    ]


def test_dispositivo_de_teste_fica_de_fora_a_menos_que_pedido(conn, tmp_path):
    insert(conn, "no-01", plan(last=59))
    insert(conn, "teste-https", plan(last=0))
    db_file = conn.execute("PRAGMA database_list").fetchone()["file"]
    assert list(pmx.run(db_file, DAY, DAY, tmp_path / "a", None, False)["nos"]) == ["no-01"]
    assert list(pmx.run(db_file, DAY, DAY, tmp_path / "b", ["teste-https"], False)["nos"]) == ["teste-https"]


def test_no_sem_leituras_no_periodo(conn, tmp_path):
    insert(conn, "no-01", plan(last=0))
    other = DAY + timedelta(days=5)
    op = node(conn, tmp_path, start=other, end=other)["operacional"]
    assert (op["minutos_com_leitura"], op["completude"], op["maior_lacuna_min"]) == (0, 0.0, 1440)
    assert op["rssi_medio_dbm"] is None


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_banco_de_origem_nao_e_alterado(conn, tmp_path):
    insert(conn, "no-01", plan())
    conn.close()
    db_file = tmp_path / "pm25.db"
    before = sha256(db_file)
    assert pmx.main(["--db", str(db_file), "--start", "2026-09-01", "--end", "2026-09-01",
                     "--out-dir", str(tmp_path / "saida")]) == 0
    assert sha256(db_file) == before
    assert {p.name for p in (tmp_path / "saida").iterdir()} == {
        "periodo.json", "completude_diaria.csv", "perfil_hora.csv", "perfil_dia_semana.csv"}


def test_freeze_produz_copia_integra_com_hash_e_intervalo(conn, tmp_path):
    insert(conn, "no-01", plan(acq=range(600, 630)))
    conn.close()
    source = tmp_path / "pm25.db"
    before = sha256(source)
    out = tmp_path / "saida"
    assert pmx.main(["--db", str(source), "--start", "2026-09-01", "--end", "2026-09-01",
                     "--out-dir", str(out), "--freeze"]) == 0
    assert sha256(source) == before                                       # a origem não muda

    report = json.loads((out / "periodo.json").read_text(encoding="utf-8"))
    frozen = out / report["congelamento"]["arquivo"]
    assert frozen.name == "pm25-congelado-2026-09-01_2026-09-01.db"
    assert report["congelamento"]["sha256"] == sha256(frozen)               # o hash identifica o arquivo
    assert report["congelamento"]["intervalo"] == {"inicio": "2026-09-01", "fim": "2026-09-01"}
    assert report["congelamento"]["medicoes"] == 1410
    assert datetime.strptime(report["congelamento"]["extraido_em"], "%Y-%m-%dT%H:%M:%SZ")
    assert report["banco"] == frozen.name                                   # métricas calculadas sobre a cópia
    assert report["nos"]["no-01"]["operacional"]["minutos_com_leitura"] == 1410

    copy = sqlite3.connect(frozen)
    try:
        assert copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert copy.execute("SELECT COUNT(*) FROM measurements").fetchone()[0] == 1410
        with pytest.raises(sqlite3.DatabaseError, match="imutável"):         # os gatilhos vão junto
            copy.execute("DELETE FROM measurements")
    finally:
        copy.close()
    assert sorted(p.name for p in out.glob("*.db*")) == [frozen.name]       # sem -wal, -shm nem .part


def test_banco_inexistente_retorna_erro(tmp_path, capsys):
    code = pmx.main(["--db", str(tmp_path / "nada.db"), "--start", "2026-09-01", "--end", "2026-09-01"])
    assert code == 1 and "não encontrado" in capsys.readouterr().err
