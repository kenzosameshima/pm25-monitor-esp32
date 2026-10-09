"""Testes da comparação com a CETESB: CSV e banco sintéticos, com resultados conferíveis a mão."""

import json
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("pandas")

from app import db  # noqa: E402
from scripts import compare_cetesb as cc  # noqa: E402

BRT0 = datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc)  # 00:00 de 01/09 em Brasília

HEADER = ("Tipo de Monitoramento:;CETESB\nTipo de Rede:;Automática\nCódigo da estação:;120\n"
          "Nome da estação:;Osasco\n\nData;Hora;Média Horária\n;;MP2.5(Partículas Inaláveis Finas) - µg/m3\n")


def csv_file(tmp_path, lines: list[str], encoding: str = "latin-1"):
    p = tmp_path / "cetesb.csv"
    p.write_bytes((HEADER + "\n".join(lines) + "\n").encode(encoding))
    return str(p)


def test_rotulo_fim_da_hora_e_meia_noite(tmp_path):
    path = csv_file(tmp_path, ["01/09/2026;01:00;30", "01/09/2026;24:00;7", "02/09/2026;01:00;8"])
    ref, info = cc.read_cetesb(path)
    assert ref[BRT0] == 30                                      # 01:00 = hora 00:00-01:00 de Brasília = 03:00Z
    assert ref[BRT0 + timedelta(hours=23)] == 7                  # 24:00 = hora 23:00-24:00
    assert ref[BRT0 + timedelta(hours=24)] == 8
    assert info["estacao"] == "Osasco" and info["codigo_estacao"] == "120"


def test_rotulo_de_inicio_da_hora(tmp_path):
    ref, _ = cc.read_cetesb(csv_file(tmp_path, ["01/09/2026;01:00;30"]), hour_label="start")
    assert ref.index[0] == BRT0 + timedelta(hours=1)


def test_valor_vazio_vira_nan_e_utf8_tambem_le(tmp_path):
    ref, info = cc.read_cetesb(csv_file(tmp_path, ["01/09/2026;02:00;", "01/09/2026;03:00;5"], "utf-8"))
    assert ref.isna().sum() == 1 and info["horas_vazias"] == 1 and info["estacao"] == "Osasco"


def test_arquivo_sem_dados_da_erro(tmp_path):
    with pytest.raises(ValueError):
        cc.read_cetesb(csv_file(tmp_path, []))


def test_concordancia_vies_e_regressao():
    import pandas as pd
    ref = pd.Series(range(10, 40), dtype=float)
    out = cc.agreement(ref * 1.5 + 2, ref)                      # nó lê 50% acima mais 2
    assert out["n"] == 30 and out["inclinacao"] == 1.5 and out["intercepto"] == 2.0 and out["pearson_r"] == 1.0
    assert out["vies"] == pytest.approx((0.5 * ref + 2).mean(), abs=0.01)
    few = cc.agreement(ref[:5] + 3, ref[:5])
    assert few["vies"] == 3.0 and "pearson_r" not in few and "aviso" in few


def insert_node(conn, device, values, humidity=60.0, per_hour=50):
    rows = []
    for h, v in enumerate(values):
        for m in range(per_hour):
            ts = BRT0 + timedelta(hours=h, minutes=m)
            rows.append({"device_id": device, "boot_id": 1, "seq": h * 60 + m, "ts_sensor": db.iso(ts),
                         "ts_received": db.iso(ts), "pm1": None, "pm25": v, "pm10": None, "pm25_cf1": None,
                         "temperature": 20.0, "humidity": humidity if h < 30 else 90.0, "rssi": -60,
                         "uptime_s": 0, "samples": 58, "schema_version": "1", "quality": "ok"})
    db.insert_batch(conn, device, rows, BRT0)


def test_pareamento_ponta_a_ponta(tmp_path, capsys):
    values = [10.0 + h % 7 for h in range(60)]                  # 60 horas do nó
    dbfile = str(tmp_path / "pm25.db")
    conn = db.connect(dbfile)
    db.init_db(conn)
    insert_node(conn, "no-01", values)
    insert_node(conn, "teste-https", values)                     # nó de teste fica de fora
    conn.close()
    # CETESB: o rótulo é o fim da hora, então a hora h do nó é a linha h+1 (a meia-noite vira 24:00 do dia anterior);
    # viés fixo de +2 no nó e uma hora vazia
    fixed = []
    for h, v in enumerate(values):
        end = BRT0.astimezone(cc.BRT) + timedelta(hours=h + 1)
        day, hh = (end - timedelta(days=1), 24) if end.hour == 0 else (end, end.hour)
        fixed.append(f"{day:%d/%m/%Y};{hh:02d}:00;{'' if h == 5 else int(v - 2)}")
    path = csv_file(tmp_path, fixed)

    rc = cc.main(["--cetesb", path, "--db", dbfile, "--out-dir", str(tmp_path / "out"), "--devices", "no-01"])
    assert rc == 0
    report = json.loads((tmp_path / "out" / "comparacao_cetesb.json").read_text(encoding="utf-8"))
    total = report["nos"]["no-01"]["total"]
    assert total["n"] == 59 and total["vies"] == 2.0 and total["rmse"] == 2.0   # 60 horas menos a vazia
    assert report["nos"]["no-01"]["umidade_alta"]["n"] > 0 and report["nos"]["no-01"]["umidade_baixa"]["n"] > 0
    assert (tmp_path / "out" / "comparacao_cetesb_pares.csv").exists()
    assert "no-01: 59 h pareadas" in capsys.readouterr().out
    rc2 = cc.main(["--cetesb", path, "--db", dbfile, "--out-dir", str(tmp_path / "out2")])
    assert rc2 == 0
    assert set(json.loads((tmp_path / "out2" / "comparacao_cetesb.json").read_text(encoding="utf-8"))["nos"]) == {"no-01"}


def test_arquivos_ausentes_retornam_1(tmp_path):
    assert cc.main(["--cetesb", str(tmp_path / "x.csv"), "--db", str(tmp_path / "x.db")]) == 1
