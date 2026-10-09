"""Testes da comparação com a CETESB: CSV e banco sintéticos, com resultados conferíveis a mão."""

import json
from datetime import datetime, timedelta, timezone

import pytest

pd = pytest.importorskip("pandas")

from app import db  # noqa: E402
from scripts import compare_cetesb as cc  # noqa: E402

BRT0 = datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc)  # 00:00 de 01/09 em Brasília

HEADER = ("Tipo de Monitoramento:;CETESB\nTipo de Rede:;Automática\nTipo de Dado:;Primários\n"
          "Código da estação:;120\nNome da estação:;Osasco\n\nData;Hora;Média Horária\n"
          ";;MP2.5(Partículas Inaláveis Finas) - µg/m3\n")


def csv_file(tmp_path, lines: list[str], encoding: str = "latin-1", newline: str = "\n"):
    p = tmp_path / "cetesb.csv"
    p.write_bytes((HEADER + "\n".join(lines) + "\n").replace("\n", newline).encode(encoding))
    return str(p)


def qualar_line(hour: int, value, hour_label: str = "end") -> str:
    """Linha do QUALAR para a hora `hour` contada a partir de BRT0 (00:00 de 01/09 em Brasília).

    Com o rótulo no fim da hora, a hora 23:00-24:00 é escrita como 24:00 do mesmo dia, nunca 00:00.
    """
    start = BRT0.astimezone(cc.BRT) + timedelta(hours=hour)
    label = start + timedelta(hours=1) if hour_label == "end" else start
    if hour_label == "end" and label.hour == 0:
        day, hh = label - timedelta(days=1), 24
    else:
        day, hh = label, label.hour
    return f"{day:%d/%m/%Y};{hh:02d}:00;{value}"


# ---------------------------------------------------------------- leitura do CSV

def test_rotulo_fim_da_hora_e_meia_noite(tmp_path):
    path = csv_file(tmp_path, ["01/09/2026;01:00;30", "01/09/2026;24:00;7", "02/09/2026;01:00;8"])
    ref, info = cc.read_cetesb(path)
    assert ref[BRT0] == 30                                      # 01:00 = hora 00:00-01:00 de Brasília = 03:00Z
    assert ref[BRT0 + timedelta(hours=23)] == 7                  # 24:00 = hora 23:00-24:00
    assert ref[BRT0 + timedelta(hours=24)] == 8
    assert info["estacao"] == "Osasco" and info["codigo_estacao"] == "120"


def test_rotulo_de_inicio_da_hora(tmp_path):
    ref, info = cc.read_cetesb(csv_file(tmp_path, ["01/09/2026;01:00;30"]), hour_label="start")
    assert ref.index[0] == BRT0 + timedelta(hours=1)
    assert info["rotulo_hora"] == "início da hora"


def test_valor_vazio_vira_nan_e_utf8_tambem_le(tmp_path):
    ref, info = cc.read_cetesb(csv_file(tmp_path, ["01/09/2026;02:00;", "01/09/2026;03:00;5"], "utf-8"))
    assert ref.isna().sum() == 1 and info["horas_vazias"] == 1 and info["estacao"] == "Osasco"


def test_utf8_com_bom_crlf_e_virgula_decimal(tmp_path):
    path = csv_file(tmp_path, ["01/09/2026;01:00;12,5;"], "utf-8-sig", "\r\n")
    ref, info = cc.read_cetesb(path)
    assert ref[BRT0] == 12.5 and info["codigo_estacao"] == "120" and info["estacao"] == "Osasco"


def test_cabecalho_sem_estacao_fica_none(tmp_path):
    p = tmp_path / "sem_cabecalho.csv"
    p.write_text("01/09/2026;01:00;30\n", encoding="utf-8")
    _, info = cc.read_cetesb(str(p))
    assert info["estacao"] is None and info["codigo_estacao"] is None


@pytest.mark.parametrize("line, message", [
    ("01/09/2026;01:00;ND", "valor não numérico"),
    ("01/09/2026;01:30;5", "hora inválida"),
    ("01/09/2026;25:00;5", "hora inválida"),
    ("31/09/2026;01:00;5", "data inválida"),
    ("01/09/2026;01:00;5;7", "uma só coluna de valores"),
])
def test_linha_de_dados_malformada_da_erro_com_a_linha(tmp_path, line, message):
    with pytest.raises(ValueError, match=message) as err:
        cc.read_cetesb(csv_file(tmp_path, [line]))
    assert "linha 9" in str(err.value)                           # o cabeçalho ocupa as linhas 1 a 8


def test_hora_repetida_da_erro(tmp_path):
    with pytest.raises(ValueError, match="hora repetida"):
        cc.read_cetesb(csv_file(tmp_path, ["01/09/2026;24:00;5", "02/09/2026;00:00;6"]))


def test_arquivo_sem_dados_da_erro(tmp_path):
    with pytest.raises(ValueError):
        cc.read_cetesb(csv_file(tmp_path, []))


# ---------------------------------------------------------------- estatística

def test_concordancia_vies_e_regressao():
    ref = pd.Series(range(10, 40), dtype=float)
    out = cc.agreement(ref * 1.5 + 2, ref)                      # nó lê 50% acima mais 2
    assert out["n"] == 30 and out["inclinacao"] == 1.5 and out["intercepto"] == 2.0 and out["pearson_r"] == 1.0
    assert out["vies"] == pytest.approx((0.5 * ref + 2).mean(), abs=0.01)
    assert out["rmse"] == pytest.approx(((0.5 * ref + 2) ** 2).mean() ** 0.5, abs=0.01)
    assert out["mae"] == out["vies"]                            # todas as diferenças são positivas


def test_menos_de_24_pares_nao_calcula_correlacao():
    ref = pd.Series(range(10, 33), dtype=float)                 # 23 pares
    out = cc.agreement(ref + 3, ref)
    assert out["n"] == 23 and out["vies"] == 3.0 and "pearson_r" not in out and "24 pares" in out["aviso"]
    ref24 = pd.Series(range(10, 34), dtype=float)               # com 24 pares já calcula
    assert "pearson_r" in cc.agreement(ref24 + 3, ref24) and "aviso" not in cc.agreement(ref24 + 3, ref24)


@pytest.mark.parametrize("node, ref", [
    ([10.1] * 30, list(range(30))),                             # nó constante (soma em float não é exata)
    (list(range(30)), [8.0] * 30),                              # CETESB constante
])
def test_serie_constante_sem_nan(node, ref):
    out = cc.agreement(pd.Series(node, dtype=float), pd.Series(ref, dtype=float))
    assert "pearson_r" not in out and "inclinacao" not in out and "constante" in out["aviso"]
    json.dumps(out, allow_nan=False)                            # nada de NaN/Infinity


def test_menos_de_dois_pontos():
    assert cc.agreement(pd.Series(dtype=float), pd.Series(dtype=float)) == {"n": 0}
    one = cc.agreement(pd.Series([5.0]), pd.Series([3.0]))
    assert one["n"] == 1 and one["vies"] == 2.0 and one["rmse"] == 2.0
    json.dumps(one, allow_nan=False)


def test_umidade_separa_sem_perder_nem_repetir_horas():
    pairs = pd.DataFrame({"pm25_no": [10.0, 12.0, 14.0, 16.0], "pm25_cetesb": [9.0, 9.0, 9.0, 9.0],
                          "umidade": [60.0, 75.0, 75.1, None]})
    out = cc.by_humidity(pairs, 75.0)
    assert out["umidade_baixa"]["n"] == 2                       # 75 exato fica em "baixa" (<=)
    assert out["umidade_alta"]["n"] == 1 and out["sem_umidade"] == 1
    assert out["umidade_alta"]["n"] + out["umidade_baixa"]["n"] + out["sem_umidade"] == out["total"]["n"] == 4


# ---------------------------------------------------------------- ponta a ponta

def insert_node(conn, device, values, humidity, per_hour=50):
    """Grava `per_hour` leituras por hora a partir de BRT0; humidity[h] é a umidade da hora h (None = sem)."""
    rows = []
    for h, v in enumerate(values):
        for m in range(per_hour):
            ts = BRT0 + timedelta(hours=h, minutes=m)
            rows.append({"device_id": device, "boot_id": 1, "seq": h * 60 + m, "ts_sensor": db.iso(ts),
                         "ts_received": db.iso(ts), "pm1": None, "pm25": v, "pm10": None, "pm25_cf1": None,
                         "temperature": 20.0, "humidity": humidity[h], "rssi": -60,
                         "uptime_s": 0, "samples": 58, "schema_version": "1", "quality": "ok"})
    db.insert_batch(conn, device, rows, BRT0)


VALUES = [10.0 + h % 7 for h in range(60)]                     # 60 horas do nó: 01/09, 02/09 e metade de 03/09
HUMIDITY = [60.0] * 30 + [90.0] * 30
HUMIDITY[40] = None                                            # uma hora sem umidade


@pytest.fixture
def dbfile(tmp_path):
    path = str(tmp_path / "pm25.db")
    conn = db.connect(path)
    db.init_db(conn)
    insert_node(conn, "no-01", VALUES, HUMIDITY)
    insert_node(conn, "teste-https", VALUES, HUMIDITY)          # nó de teste fica de fora
    conn.close()
    return path


def cetesb_csv(tmp_path, hour_label="end", empty=(5,), all_empty=False):
    """CSV da CETESB com viés fixo de +2 no nó (CETESB = nó - 2) e as horas de `empty` vazias."""
    lines = [qualar_line(h, "" if all_empty or h in empty else int(v - 2), hour_label) for h, v in enumerate(VALUES)]
    return csv_file(tmp_path, lines)


def run_main(tmp_path, *args):
    out = tmp_path / "out"
    rc = cc.main(["--out-dir", str(out), *args])
    report = json.loads((out / "comparacao_cetesb.json").read_text(encoding="utf-8")) if rc == 0 else None
    return rc, report, out


def test_pareamento_ponta_a_ponta(tmp_path, dbfile, capsys):
    rc, report, out = run_main(tmp_path, "--cetesb", cetesb_csv(tmp_path), "--db", dbfile, "--devices", "no-01")
    assert rc == 0
    node = report["nos"]["no-01"]
    assert node["total"]["n"] == 59 and node["total"]["vies"] == 2.0 and node["total"]["rmse"] == 2.0  # 60 menos a vazia
    assert node["umidade_baixa"]["n"] == 29 and node["umidade_alta"]["n"] == 29 and node["sem_umidade"] == 1
    assert report["cetesb"]["codigo_estacao"] == "120"
    pairs = pd.read_csv(out / "comparacao_cetesb_pares.csv")
    assert list(pairs.columns) == cc.PAIR_COLUMNS and len(pairs) == 59
    assert (pairs["pm25_no"] - pairs["pm25_cetesb"] == 2).all()
    assert "no-01: 59 h pareadas" in capsys.readouterr().out

    rc2, report2, _ = run_main(tmp_path, "--cetesb", cetesb_csv(tmp_path), "--db", dbfile)
    assert rc2 == 0 and set(report2["nos"]) == {"no-01"}


def test_rotulo_de_inicio_ponta_a_ponta(tmp_path, dbfile):
    path = cetesb_csv(tmp_path, hour_label="start")
    _, report, _ = run_main(tmp_path, "--cetesb", path, "--db", dbfile, "--hour-label", "start")
    total = report["nos"]["no-01"]["total"]
    assert total["n"] == 59 and total["vies"] == 2.0 and total["rmse"] == 2.0
    # o mesmo arquivo lido com a convenção errada desloca tudo em 1 h e o erro aparece
    _, wrong, _ = run_main(tmp_path, "--cetesb", path, "--db", dbfile)
    assert wrong["nos"]["no-01"]["total"]["rmse"] > 2.0


def test_start_e_end_filtram_o_periodo(tmp_path, dbfile):
    _, report, _ = run_main(tmp_path, "--cetesb", cetesb_csv(tmp_path), "--db", dbfile,
                            "--start", "2026-09-02", "--end", "2026-09-02")
    assert report["periodo"] == {"inicio": "2026-09-02", "fim": "2026-09-02", "fuso": "America/Sao_Paulo (UTC-3)"}
    assert report["nos"]["no-01"]["total"]["n"] == 24             # só as 24 horas de 02/09 (a vazia é de 01/09)


def test_estacao_sem_dados_no_periodo(tmp_path, dbfile, capsys):
    rc, report, out = run_main(tmp_path, "--cetesb", cetesb_csv(tmp_path, all_empty=True), "--db", dbfile)
    assert rc == 0
    assert report["cetesb"]["horas_vazias"] == 60
    assert report["nos"]["no-01"]["total"] == {"n": 0} and report["nos"]["no-01"]["sem_umidade"] == 0
    pairs = pd.read_csv(out / "comparacao_cetesb_pares.csv")
    assert list(pairs.columns) == cc.PAIR_COLUMNS and pairs.empty
    assert "no-01: nenhuma hora pareada" in capsys.readouterr().out


def test_arquivos_ausentes_retornam_1(tmp_path):
    assert cc.main(["--cetesb", str(tmp_path / "x.csv"), "--db", str(tmp_path / "x.db")]) == 1


def test_csv_malformado_retorna_2(tmp_path, dbfile, capsys):
    assert cc.main(["--cetesb", csv_file(tmp_path, ["01/09/2026;01:00;ND"]), "--db", dbfile,
                    "--out-dir", str(tmp_path / "out")]) == 2
    assert "valor não numérico" in capsys.readouterr().err
