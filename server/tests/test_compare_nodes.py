"""Testes da concordância entre dois nós no mesmo ar: banco sintético, resultados conferíveis a mão."""

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

pd = pytest.importorskip("pandas")

from app import db  # noqa: E402
from scripts import compare_nodes as cn  # noqa: E402

T0 = datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc)  # 15:00 de 11/11 em Brasília, primeira hora cheia após a mudança
OK = 50                                                   # leituras numa hora válida (mínimo de 45)


def insert(conn, device, hours, first=T0):
    """Grava, a partir de `first`, uma hora por item de `hours`: (pm25, umidade, leituras); 0 leituras = hora vazia."""
    rows = []
    for h, (pm25, humidity, count) in enumerate(hours):
        for m in range(count):
            ts = first + timedelta(hours=h, minutes=m)
            rows.append({"device_id": device, "boot_id": 1, "seq": h * 60 + m, "ts_sensor": db.iso(ts),
                         "ts_received": db.iso(ts), "pm1": None, "pm25": pm25, "pm10": None, "pm25_cf1": None,
                         "temperature": 25.0, "humidity": humidity, "rssi": -60,
                         "uptime_s": 0, "samples": 58, "schema_version": "1", "quality": "ok"})
    if rows:
        db.insert_batch(conn, device, rows, first)


def make_db(tmp_path, **devices):
    path = str(tmp_path / "pm25.db")
    conn = db.connect(path)
    db.init_db(conn)
    for device, hours in devices.items():
        insert(conn, device.replace("_", "-"), hours)
    conn.close()
    return path


def run_main(tmp_path, *args):
    out = tmp_path / "out"
    rc = cn.main(["--out-dir", str(out), *args])
    report = json.loads((out / cn.REPORT_FILE).read_text(encoding="utf-8")) if rc == 0 else None
    return rc, report, out


# Seis horas (15:00 a 21:00 de Brasília). O no-01 tem todas válidas com 12; o no-02, 10 nas válidas, uma hora com
# poucas leituras, uma suspeita (sensor sem partículas) e a última sem leitura nenhuma.
NO_01 = [(12.0, 60.0, OK)] * 6
NO_02 = [(10.0, 60.0, OK), (10.0, 60.0, 30), (10.0, 60.0, OK), (0.0, 60.0, OK), (10.0, 60.0, OK), (10.0, 60.0, 0)]
WINDOW = ["--start", "2026-11-11T15:00", "--end", "2026-11-11T21:00"]


def test_so_pareia_horas_validas_nos_dois_nos(tmp_path, capsys):
    path = make_db(tmp_path, no_01=NO_01, no_02=NO_02)
    rc, report, out = run_main(tmp_path, "--db", path, *WINDOW)
    assert rc == 0
    assert report["nos"] == {"a": "no-01", "b": "no-02"}
    assert report["periodo"]["horas"] == 6
    total = report["concordancia"]["total"]
    assert total["n"] == 3 and total["vies"] == 2.0 and total["rmse"] == 2.0       # horas 0, 2 e 4
    assert total["media_a"] == 12.0 and total["media_b"] == 10.0

    a, b = report["horas"]["no-01"], report["horas"]["no-02"]
    assert a["estados"] == {"válida": 6, "sem leituras": 0, "poucas leituras": 0, "suspeita": 0}
    assert b["estados"] == {"válida": 3, "sem leituras": 1, "poucas leituras": 1, "suspeita": 1}
    assert a["usadas"] == 6 and a["usadas_sem_par"] == 3                            # perdidas pelo outro lado
    assert b["usadas"] == 3 and b["usadas_sem_par"] == 0
    assert report["horas"]["pareadas"] == 3

    pairs = pd.read_csv(out / cn.PAIRS_FILE)
    assert list(pairs.columns) == cn.PAIR_COLUMNS and len(pairs) == 3
    assert list(pd.to_datetime(pairs["hora_utc"])) == [pd.Timestamp(T0 + timedelta(hours=h)) for h in (0, 2, 4)]
    assert (pairs["pm25_a"] - pairs["pm25_b"] == 2).all()
    printed = capsys.readouterr().out
    assert "3 h pareadas" in printed and "+2.0" in printed


def test_include_suspect_traz_as_horas_suspeitas_marcadas_e_separadas(tmp_path):
    path = make_db(tmp_path, no_01=NO_01, no_02=NO_02)
    _, report, _ = run_main(tmp_path, "--db", path, *WINDOW)
    assert report["regras"]["horas_suspeitas_incluidas"] is False and "suspeitas" not in report["concordancia"]

    rc, report, out = run_main(tmp_path, "--db", path, *WINDOW, "--include-suspect")
    assert rc == 0 and report["regras"]["horas_suspeitas_incluidas"] is True
    assert report["horas"]["pareadas"] == 4                                         # a hora suspeita volta
    b = report["horas"]["no-02"]
    assert b["estados"]["suspeita"] == 1 and b["usadas"] == 4                       # o estado continua dito
    assert report["horas"]["no-01"]["usadas_sem_par"] == 2
    c = report["concordancia"]
    assert c["total"]["n"] == 4
    assert c["suspeitas"]["n"] == 1 and c["suspeitas"]["vies"] == 12.0             # o no-02 lê 0 onde o no-01 lê 12
    assert c["demais"]["n"] == 3 and c["demais"]["vies"] == 2.0
    pairs = pd.read_csv(out / cn.PAIRS_FILE)
    assert int(pairs["suspeita_b"].sum()) == 1 and int(pairs["suspeita_a"].sum()) == 0


def test_umidade_do_par_e_a_media_dos_dois_nos_e_separa_sem_perder_horas(tmp_path):
    # (umidade do no-01, umidade do no-02) -> média: 80 alta; 75 baixa (o limite fica em baixa); só o no-02 com 60
    # baixa; nenhum dos dois: sem umidade. Pelo no-01 sozinho, a primeira hora (70) cairia em baixa.
    no_01 = [(14.0, 70.0, OK), (12.0, 75.0, OK), (12.0, None, OK), (12.0, None, OK)]
    no_02 = [(10.0, 90.0, OK), (10.0, 75.0, OK), (10.0, 60.0, OK), (10.0, None, OK)]
    path = make_db(tmp_path, no_01=no_01, no_02=no_02)
    _, report, out = run_main(tmp_path, "--db", path, "--start", "2026-11-11T15:00", "--end", "2026-11-11T19:00")
    c = report["concordancia"]
    assert c["umidade_alta"]["n"] == 1 and c["umidade_alta"]["vies"] == 4.0
    assert c["umidade_baixa"]["n"] == 2 and c["umidade_baixa"]["vies"] == 2.0
    assert c["sem_umidade"] == 1
    assert c["umidade_alta"]["n"] + c["umidade_baixa"]["n"] + c["sem_umidade"] == c["total"]["n"] == 4
    pairs = pd.read_csv(out / cn.PAIRS_FILE)
    assert list(pairs["umidade"].fillna(-1)) == [80.0, 75.0, 60.0, -1]


def test_sem_sobreposicao_nenhuma_hora_pareada(tmp_path, capsys):
    path = make_db(tmp_path, no_01=NO_01)                                          # o no-02 não mandou nada
    rc, report, out = run_main(tmp_path, "--db", path, *WINDOW)
    assert rc == 0
    assert report["concordancia"]["total"] == {"n": 0} and report["concordancia"]["sem_umidade"] == 0
    assert report["horas"]["pareadas"] == 0
    assert report["horas"]["no-02"]["estados"]["sem leituras"] == 6 and report["horas"]["no-01"]["usadas_sem_par"] == 6
    pairs = pd.read_csv(out / cn.PAIRS_FILE)
    assert list(pairs.columns) == cn.PAIR_COLUMNS and pairs.empty
    assert "Nenhuma hora pareada" in capsys.readouterr().out


def test_periodo_vazio_tambem_sai_sem_pares(tmp_path):
    path = make_db(tmp_path, no_01=NO_01, no_02=NO_01)
    rc, report, _ = run_main(tmp_path, "--db", path, "--start", "2026-11-11T15:10", "--end", "2026-11-11T15:50")
    assert rc == 0 and report["periodo"]["horas"] == 0 and report["concordancia"]["total"] == {"n": 0}


def test_inicio_padrao_e_a_mudanca_e_a_hora_cortada_fica_de_fora(tmp_path):
    # A mudança foi às 17:18 UTC: a hora das 17:00 tem só 42 minutos no mesmo suporte e não conta.
    early = [(12.0, 60.0, 60)] * 3
    path = str(tmp_path / "pm25.db")
    conn = db.connect(path)
    db.init_db(conn)
    insert(conn, "no-01", early, first=T0 - timedelta(hours=2))                  # 16:00 a 19:00 UTC
    insert(conn, "no-02", early, first=T0 - timedelta(hours=2))
    conn.close()
    _, report, _ = run_main(tmp_path, "--db", path, "--end", "2026-11-11")       # dia sozinho: até o fim dele
    assert report["periodo"]["inicio_utc"] == "2026-11-11T17:18:00Z"
    assert report["periodo"]["primeira_hora_utc"] == "2026-11-11T18:00:00Z"
    assert report["periodo"]["fim_utc"] == "2026-11-12T03:00:00Z"                # 00:00 de 12/11 em Brasília
    assert report["periodo"]["horas"] == 9 and report["horas"]["pareadas"] == 1  # só a hora das 18:00 UTC


@pytest.mark.parametrize("args, message", [
    (["--devices", "no-01"], "exatamente dois"),
    (["--devices", "no-01,no-01"], "diferentes"),
    (["--start", "2026-11-12", "--end", "2026-11-11"], "anterior"),
])
def test_argumentos_invalidos_retornam_2(tmp_path, capsys, args, message):
    path = make_db(tmp_path, no_01=NO_01, no_02=NO_02)
    assert cn.main(["--db", path, "--out-dir", str(tmp_path / "out"), *args]) == 2
    assert message in capsys.readouterr().err


def test_banco_ausente_retorna_1(tmp_path, capsys):
    assert cn.main(["--db", str(tmp_path / "nada.db")]) == 1
    assert "não encontrado" in capsys.readouterr().err


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_freeze_compara_sobre_copia_integra_com_hash_e_nao_altera_a_origem(tmp_path):
    source = tmp_path / "pm25.db"
    make_db(tmp_path, no_01=NO_01, no_02=NO_02)
    before = sha256(source)
    rc, report, out = run_main(tmp_path, "--db", str(source), "--start", "2026-11-11T15:00", "--end", "2026-11-25",
                               "--freeze")
    assert rc == 0 and sha256(source) == before
    frozen = out / report["congelamento"]["arquivo"]
    assert frozen.name == "pm25-congelado-2026-11-11_2026-11-25.db"
    assert report["congelamento"]["sha256"] == sha256(frozen)
    assert report["congelamento"]["intervalo"] == {"inicio": "2026-11-11", "fim": "2026-11-25"}
    assert report["banco"] == frozen.name and report["horas"]["pareadas"] == 3      # calculado sobre a cópia

    # a rodada final pode apontar --db para a cópia congelada e chega ao mesmo resultado
    rc, again, _ = run_main(tmp_path, "--db", str(frozen), "--start", "2026-11-11T15:00", "--end", "2026-11-25")
    assert rc == 0 and again["concordancia"] == report["concordancia"] and sha256(frozen) == report["congelamento"]["sha256"]
