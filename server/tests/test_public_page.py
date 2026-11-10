"""Testes da página pública (/public): o que ela mostra a qualquer pessoa, sem token, e o que fica só no painel."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import get_settings

TOKEN_1 = "token-do-no-01-aB3xQ9zK7pLm2Wv8Rt"
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
NOW = HOUR = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def clock():
    """O relógio de cada teste: com o valor do carregamento do arquivo, uma leitura de "1 min atrás" ficaria atrasada
    numa suíte longa."""
    global NOW, HOUR
    NOW = datetime.now(timezone.utc).replace(microsecond=0)
    HOUR = NOW.replace(minute=0, second=0)


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "pm25.db"
    monkeypatch.setenv("PM25_DB_PATH", str(db_path))
    monkeypatch.setenv("PM25_DEVICE_TOKENS", f"no-01:{TOKEN_1}")
    monkeypatch.setenv("PM25_READ_TOKEN", "")
    get_settings.cache_clear()
    from app.main import app

    with TestClient(app) as c:
        c.db_path = db_path
        yield c
    get_settings.cache_clear()


def reading(ts: datetime, seq: int, pm25: float | None = 10.0, *, device: str = "no-01", received: datetime | None = None,
            **fields) -> dict:
    row = {"device_id": device, "boot_id": 1, "seq": seq, "ts_sensor": db.iso(ts),
           "ts_received": db.iso(received or ts), "pm1": None, "pm25": pm25, "pm10": None, "pm25_cf1": None,
           "temperature": 20.0, "humidity": 60.0, "pressure": None, "rssi": -60, "uptime_s": 0, "samples": 58,
           "schema_version": "1", "quality": "ok"}
    return row | fields


def insert(client, rows: list[dict], device: str = "no-01", firmware: str | None = None) -> None:
    conn = db.connect(str(client.db_path))
    try:
        db.insert_batch(conn, device, rows, NOW, None, firmware)
    finally:
        conn.close()


def test_abre_sem_token_e_mostra_o_pm25_da_ultima_leitura_com_a_faixa(client):
    insert(client, [reading(NOW - timedelta(minutes=2), 0, 12.0), reading(NOW - timedelta(minutes=1), 1, 32.4)])

    r = client.get("/public")

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert '<span class="num">32,4</span> µg/m³' in r.text
    assert "PM2,5 · média de 1 minuto" in r.text
    assert "Moderada" in node_card(r.text)


@pytest.mark.parametrize("minutes_ago, state, shows_value", [
    (1, "Em operação", True),
    (7, "Atrasado", True),
    (40, "Sem dados recentes", False),
])
def test_mostra_o_estado_do_no_e_esconde_o_valor_de_quem_parou_de_enviar(client, minutes_ago, state, shows_value):
    sent = NOW - timedelta(minutes=minutes_ago)
    insert(client, [reading(sent, 0, 41.7)])

    page = node_card(client.get("/public").text)

    assert state in page
    assert ("41,7" in page) is shows_value
    assert ("Moderada" in page) is shows_value


@pytest.mark.parametrize("minutes_ago, heading", [(1, "<h3>Agora</h3>"), (7, "<h3>Última leitura, há 7 min</h3>")])
def test_no_atrasado_nao_chama_a_ultima_leitura_de_agora(client, minutes_ago, heading):
    insert(client, [reading(NOW - timedelta(minutes=minutes_ago), 0, 12.0)])

    page = node_card(client.get("/public").text)

    assert heading in page
    assert ("<h3>Agora</h3>" in page) is (minutes_ago == 1)


def node_card(page: str) -> str:
    """O cartão do primeiro nó, enviando ou parado: a legenda das faixas, mais abaixo, sempre traz o nome de todas."""
    start = page.index('<section class="node')
    return page[start:page.index("</section>", start)]


def test_leitura_zerada_aparece_sem_faixa(client):
    insert(client, [reading(NOW - timedelta(minutes=1), 0, 0.0, pm1=0.0, pm10=0.0)])

    page = node_card(client.get("/public").text)

    assert "0,0" in page
    assert "Boa" not in page
    assert "zerada" in page
    assert '<p class="word">Sem faixa</p>' in page


def test_pm25_abaixo_de_meio_micrograma_fica_sem_faixa_mesmo_com_pm10(client):
    insert(client, [reading(NOW - timedelta(minutes=1), 0, 0.3, pm1=0.0, pm10=0.1)])

    page = node_card(client.get("/public").text)

    assert "0,3" in page
    assert "Boa" not in page
    assert "<p class=\"word\">Sem faixa</p>" in page
    assert "zerada" not in page          # leitura zerada é só a que tem tudo em zero (GLOSSARY.md)


@pytest.mark.parametrize("humidity, warns", [(81.0, True), (60.0, False)])
def test_mostra_pm10_temperatura_e_umidade_e_avisa_da_umidade_alta(client, humidity, warns):
    insert(client, [reading(NOW - timedelta(minutes=1), 0, 20.0, pm10=48.2, temperature=23.4, humidity=humidity)])

    page = client.get("/public").text

    assert "48,2" in page
    assert "23,4" in page
    assert f"{humidity:.0f}%" in page
    assert ("acima de 75%" in page) is warns


def hour_of_readings(hours_ago: int, pm25: float, minutes: int = 60, first_seq: int = 0) -> list[dict]:
    """`minutes` leituras na hora que começou `hours_ago` horas antes da hora cheia atual."""
    start = HOUR - timedelta(hours=hours_ago)
    return [reading(start + timedelta(minutes=m), first_seq + m, pm25) for m in range(minutes)]


def test_media_de_24_horas_usa_so_as_horas_validas(client):
    rows = (hour_of_readings(6, 40.0, first_seq=0) + hour_of_readings(5, 30.0, first_seq=100)
            + hour_of_readings(3, 20.0, first_seq=200) + hour_of_readings(2, 90.0, minutes=10, first_seq=300)
            + [reading(NOW, 400, 12.0)])
    insert(client, rows)

    page = node_card(client.get("/public").text)

    assert "Média das 3 horas válidas: <strong>30,0 µg/m³</strong>" in page  # a hora com 10 leituras fica de fora
    assert coverage(page)["Horas válidas"] == "3 de 24 h"
    assert "Moderada" in page        # a faixa da média
    assert "Boa" in page             # e a da última leitura, 12,0


def coverage(card: str) -> dict[str, str]:
    """A linha de cobertura das últimas 24 horas de um cartão: rótulo -> valor."""
    import re

    start = card.index('<dl class="coverage">')
    block = card[start:card.index("</dl>", start)]
    return dict(re.findall(r"<dt>(.*?)</dt><dd>(.*?)</dd>", block))


def test_cobertura_separa_horas_suspeitas_das_que_tiveram_poucas_leituras(client):
    rows = (hour_of_readings(4, 20.0) + hour_of_readings(3, 0.2, first_seq=100)
            + hour_of_readings(2, 0.3, first_seq=200) + [reading(NOW, 300, 15.0)])
    insert(client, rows)

    page = node_card(client.get("/public").text)

    assert coverage(page) == {"Horas válidas": "1 de 24 h", "Suspeitas": "2 h", "Faltaram leituras": "21 h"}
    assert "não dá para saber se o ar estava muito limpo ou se o sensor falhou" in page


def test_cobertura_completa_nao_lista_horas_de_fora(client):
    rows = [r for h in range(24, 0, -1) for r in hour_of_readings(h, 20.0, first_seq=h * 100)]
    insert(client, rows + [reading(NOW, 0, 15.0)])

    page = node_card(client.get("/public").text)

    assert "Média de <strong>20,0 µg/m³</strong>" in page
    assert coverage(page) == {"Horas válidas": "24 de 24 h"}
    assert "Suspeitas" not in page


def test_no_enviando_sem_nenhuma_hora_com_media_diz_o_motivo_em_vez_de_ficar_em_branco(client):
    rows = [r for h in range(24, 0, -1) for r in hour_of_readings(h, 0.0, first_seq=h * 100)]
    insert(client, rows + [reading(NOW, 0, 0.0, pm1=0.0, pm10=0.0)])

    page = node_card(client.get("/public").text)

    assert "Últimas 24 horas" in page
    assert '<div class="panel">' in page
    assert "Nenhuma hora válida nas últimas 24 horas" in page
    assert coverage(page) == {"Horas válidas": "0 de 24 h", "Suspeitas": "24 h"}


def test_veredito_avisa_que_a_faixa_vale_para_24_horas_e_a_leitura_zerada_nao(client):
    insert(client, [reading(NOW, 0, 12.0)])
    insert(client, [reading(NOW, 0, 0.0, device="no-02", pm1=0.0, pm10=0.0)], device="no-02")

    page = client.get("/public").text
    first, second = page.split('<section class="node')[1:3]

    assert "a faixa serve só de referência" in first
    assert "a faixa serve só de referência" not in second


def test_legenda_do_grafico_explica_a_marca_cinza(client):
    insert(client, hour_of_readings(3, 18.0) + [reading(NOW, 100, 15.0)])

    assert "marca cinza" in client.get("/public").text


def test_cartao_traz_o_grafico_das_ultimas_24_horas(client):
    insert(client, hour_of_readings(4, 18.0) + hour_of_readings(3, 22.0, first_seq=100) + [reading(NOW, 200, 15.0)])

    page = client.get("/public").text

    assert page.count("<svg") == 1
    assert "PM2,5 médio por hora nas últimas 24 horas" in page



def forecast(target: datetime, value: float, version: str = "v1", generated: datetime | None = None) -> dict:
    return {"device_id": "no-01", "generated_at": generated or target, "target_hour": target,
            "predicted_pm25": value, "model_name": "ridge", "model_version": version}


def insert_forecasts(client, rows: list[dict]) -> None:
    conn = db.connect(str(client.db_path))
    try:
        db.insert_forecasts(conn, rows)
    finally:
        conn.close()


def test_mostra_a_previsao_mais_recente_da_hora_em_andamento_sem_as_retroativas(client):
    insert(client, [reading(NOW, 0, 15.0)])
    insert_forecasts(client, [forecast(HOUR - timedelta(hours=1), 50.0), forecast(HOUR, 27.3),
                              forecast(HOUR, 99.9, version="v1-retro"),
                              forecast(HOUR, 61.0, version="v0", generated=HOUR - timedelta(minutes=55))])

    page = client.get("/public").text

    assert "27,3" in page
    assert "experimental" in page
    for hidden in ("50,0", "99,9", "61,0", "ridge"):
        assert hidden not in page


def test_sem_previsao_a_secao_some(client):
    insert(client, [reading(NOW, 0, 15.0)])

    assert "Previsão" not in client.get("/public").text



def set_location(client, location: str) -> None:
    conn = db.connect(str(client.db_path))
    try:
        db.set_location(conn, "no-01", location)
    finally:
        conn.close()


def test_local_aparece_sem_os_detalhes_de_instalacao(client):
    insert(client, [reading(NOW, 0, 15.0)])
    set_location(client, "Veloso, Osasco (apoio externo da janela, coberto, 1,1 m do chão)")

    page = client.get("/public").text

    assert "Veloso, Osasco" in page
    assert "apoio externo" not in page
    assert "1,1 m" not in page


def test_local_vem_escapado(client):
    insert(client, [reading(NOW, 0, 15.0)])
    set_location(client, "<script>alert(1)</script> Centro")

    page = client.get("/public").text

    assert "<script>" not in page
    assert "&lt;script&gt;" in page



def test_banco_sem_leituras_mostra_um_aviso(client):
    page = client.get("/public")

    assert page.status_code == 200
    assert "Nenhum nó enviou leituras ainda" in page.text


def test_no_de_teste_fica_de_fora(client):
    insert(client, [reading(NOW, 0, 15.0, device="teste-https")], device="teste-https")

    page = client.get("/public").text

    assert "teste-https" not in page
    assert "Nenhum nó enviou leituras ainda" in page


def test_nao_mostra_o_que_diz_como_o_no_e_a_coleta_estao(client):
    insert(client, [reading(NOW, 0, 15.0, rssi=-61)], firmware="fw-9.8.7")

    page = client.get("/public").text.lower()

    for internal in ("fw-9.8.7", "firmware", "-61", "dbm", "wi-fi", "completude", "lacuna", "reinício", "duplicata",
                     "marcada", "boot_id"):
        assert internal not in page



def test_cabecalhos_proibem_script_recurso_externo_e_moldura(client):
    headers = client.get("/public").headers

    csp = headers["content-security-policy"]
    assert "default-src 'none'" in csp
    assert "script-src" not in csp            # sem script-src, vale o default-src 'none'
    assert "frame-ancestors 'none'" in csp
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cache-control"] == "public, max-age=60"


def test_rodape_diz_a_hora_da_atualizacao_e_que_nao_substitui_a_cetesb(client):
    insert(client, [reading(NOW, 0, 15.0)])

    before = datetime.now(timezone.utc)
    page = client.get("/public").text
    after = datetime.now(timezone.utc)

    assert any(f"Página atualizada às {t.astimezone(LOCAL_TZ):%H:%M}" in page for t in (before, after))
    assert "horário de Brasília" in page
    assert "CETESB" in page



def test_pagina_se_recarrega_sozinha_a_cada_minuto_sem_script(client):
    page = client.get("/public").text

    assert '<meta http-equiv="refresh" content="60">' in page
    assert "<script" not in page
    assert "atualiza sozinha a cada minuto" in page


def test_pagina_fica_em_cache_por_um_minuto(client):
    insert(client, [reading(NOW - timedelta(minutes=1), 0, 15.0)])
    first = client.get("/public").text
    insert(client, [reading(NOW, 1, 88.8)])

    second = client.get("/public").text

    assert "88,8" not in second
    assert second == first



def test_nos_enviando_vem_antes_dos_parados(client):
    insert(client, [reading(NOW - timedelta(hours=2), 0, 15.0, device="aa-parado")], device="aa-parado")
    insert(client, [reading(NOW, 0, 15.0)])

    page = client.get("/public").text

    assert page.index("no-01") < page.index("aa-parado")


def test_no_parado_sem_horas_com_media_fica_numa_linha(client):
    insert(client, [reading(NOW - timedelta(minutes=40), 0, 41.7)])

    card = node_card(client.get("/public").text)

    assert "Sem dados recentes" in card
    assert "Agora" not in card
    assert "Últimas 24 horas" not in card


def test_titulo_do_no_e_o_lugar_e_o_sensor_fica_no_estado(client):
    insert(client, [reading(NOW, 0, 15.0)])
    set_location(client, "Veloso, Osasco (apoio externo da janela)")

    card = node_card(client.get("/public").text)

    assert "<h2>Veloso, Osasco</h2>" in card
    assert "(sensor no-01)</span>" in card


# ---------------------------------------------------------------- gráfico

def series(values: list[float | None]) -> "pd.Series":
    import pandas as pd

    end = pd.Timestamp(HOUR)
    index = pd.date_range(end - pd.Timedelta(hours=len(values)), end, freq="h", inclusive="left")
    return pd.Series([float("nan") if v is None else v for v in values], index=index)


def svg(values: list[float | None]):
    import xml.etree.ElementTree as ET

    from app.public_page import hourly_chart_svg

    return ET.fromstring(hourly_chart_svg(series(values)))


NS = "{http://www.w3.org/2000/svg}"


def test_grafico_interrompe_a_linha_nas_horas_sem_media():
    chart = svg([10.0, 12.0, None, None, 30.0, 31.0, None, 15.0])

    assert len(chart.findall(f".//{NS}polyline")) == 2      # 10-12 e 30-31
    assert len(chart.findall(f".//{NS}circle")) == 1        # o 15 sozinho vira um ponto


@pytest.mark.parametrize("values, top", [([10.0, 12.0], "25"), ([20.0, 61.0], "75"), ([130.0], "150")])
def test_eixo_vai_ate_o_limite_de_faixa_logo_acima_do_maior_valor(values, top):
    labels = [t.text for t in svg(values).iter(f"{NS}text") if t.get("class") == "tick"]

    assert labels[-1] == top


def test_grafico_sem_nenhuma_hora_com_media_fica_vazio():
    from app.public_page import hourly_chart_svg

    assert hourly_chart_svg(series([None, None, None])) == ""



def test_horas_sem_media_ganham_marca_no_eixo():
    chart = svg([10.0, None, 12.0, None, None])

    assert len([r for r in chart.iter(f"{NS}rect") if r.get("class") == "gap"]) == 3
