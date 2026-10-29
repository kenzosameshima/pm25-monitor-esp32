"""Testes do dashboard com o AppTest do Streamlit: o script roda sem navegador sobre um banco sintético."""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pytest

pytest.importorskip("streamlit")
import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402
from scripts.simulate_sensor import synthetic  # noqa: E402

DASHBOARD = str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")


def populate(path: Path, hours: int = 30, devices=(("no-01", 1), ("no-02", 2))) -> None:
    conn = db.connect(str(path))
    db.init_db(conn)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    for device, boots in devices:
        state: dict = {}
        rows = []
        for i in range(hours * 60):
            if device == "no-02" and 1000 <= i < 1060:
                continue  # uma hora sem dados no nó 2
            ts = now - timedelta(minutes=hours * 60 - i)
            boot = 1 if (boots == 1 or i < hours * 30) else 2
            seq = i if boot == 1 else i - hours * 30
            r = synthetic(ts, state)
            rows.append({"device_id": device, "boot_id": boot, "seq": seq, "ts_sensor": db.iso(ts),
                         "ts_received": db.iso(ts), "uptime_s": 60 * i, "schema_version": "1",
                         "quality": "ok", **r})
        db.insert_batch(conn, device, rows, now)
    with conn:
        for h in range(1, 12):
            target = now.replace(minute=0) - timedelta(hours=h)
            conn.execute(
                "INSERT INTO forecasts (device_id, generated_at, target_hour, predicted_pm25, model_name, model_version)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                ("no-01", db.iso(target - timedelta(minutes=1)), db.iso(target), 15.0 + h % 3, "ridge", "v1"))
    conn.close()


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PM25_DB_PATH", str(tmp_path / "pm25.db"))
    monkeypatch.setenv("PM25_DEVICE_TOKENS", "no-01:token-do-no-01-aB3xQ9zK7pLm2Wv8Rt")
    get_settings.cache_clear()
    st.cache_data.clear()
    yield tmp_path / "pm25.db"
    get_settings.cache_clear()
    st.cache_data.clear()


def test_sem_banco_mostra_aviso(app_env):
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception
    assert "Nenhum dado" in at.warning[0].value


def test_dashboard_renderiza_as_tres_abas(app_env):
    populate(app_env)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert [t.label for t in at.tabs] == ["Status", "Séries", "Previsto × observado"]
    assert len(at.metric) == 8  # 4 indicadores por sensor; o sinal Wi-Fi vai numa linha à parte
    assert at.metric[0].label == "PM2,5"
    assert at.metric[0].delta in {"Boa", "Moderada", "Ruim", "Muito ruim", "Péssima"}  # faixa da CETESB
    assert at.metric[1].label == "PM10 (µg/m³)"
    assert not any("implausível" in c.value for c in at.caption)

    # tabela de saúde da coleta: o nó 2 teve uma hora sem dados e um reinício
    health = at.dataframe[0].value.set_index("Sensor")
    assert health.loc["no-02", "Reinícios"] == 1
    assert health.loc["no-02", "Maior lacuna (min)"] >= 59
    assert health.loc["no-01", "Mensagens perdidas"] == 0

    # previsto × observado: persistência e o modelo gravado, com skill score
    metrics = at.dataframe[1].value.set_index("Previsor")
    assert {"Persistência", "ridge v1"} <= set(metrics.index)
    assert "Skill score" in metrics.columns


def test_esconde_no_de_teste_e_reserva_card_do_no_cadastrado_sem_dados(app_env, monkeypatch):
    monkeypatch.setenv("PM25_DEVICE_TOKENS", "no-01:token-do-no-01-aB3xQ9zK7pLm2Wv8Rt,no-02:token-do-no-02-aB3xQ9zK7pLm2Wv8Rt,"
                                             "teste-https:token-do-teste-aB3xQ9zK7pLm2Wv8Rt")
    populate(app_env, hours=3, devices=(("no-01", 1), ("teste-https", 1)))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert [h.value for h in at.subheader] == ["no-01", "no-02"]
    assert any("aguardando instalação" in c.value for c in at.caption)
    assert len(at.metric) == 4  # só o no-01 tem leitura
    assert list(at.dataframe[0].value["Sensor"]) == ["no-01"]
    assert at.multiselect[0].options == ["no-01"]


def add_model_forecasts(path: Path, name: str, version: str, hours_ago: list[int]) -> None:
    """Previsões de `name version` do no-01 para as horas-alvo `hours_ago` horas antes da hora atual."""
    top = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    conn = db.connect(str(path))
    with conn:
        for k in hours_ago:
            target = top - timedelta(hours=k)
            conn.execute("INSERT INTO forecasts (device_id, generated_at, target_hour, predicted_pm25, model_name,"
                         " model_version) VALUES (?, ?, ?, ?, ?, ?)",
                         ("no-01", db.iso(target - timedelta(minutes=1)), db.iso(target), 15.0, name, version))
    conn.close()


def test_tabela_de_previsao_diz_que_todos_os_previsores_usam_as_mesmas_horas(app_env):
    populate(app_env)                                    # ridge v1 prevê as horas -1 a -11
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    metrics = at.dataframe[1].value.set_index("Previsor")
    assert set(metrics["Horas"]) == {11}                 # a persistência também só conta as 11 horas do modelo
    note = [c.value for c in at.caption if "mesmas 11 horas" in c.value]
    assert len(note) == 1 and "hora seguinte" in note[0] and " a " in note[0]  # horizonte e período avaliado


def test_tabela_de_previsao_avisa_quando_os_modelos_nao_tem_horas_em_comum(app_env):
    populate(app_env)
    add_model_forecasts(app_env, "ridge", "v2", [20, 21, 22])  # a versão nova não tem hora em comum com a v1
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert not any("mesmas 11 horas" in c.value for c in at.caption)
    assert any("nas horas em que tem previsão" in c.value for c in at.caption)


def add_last_reading(path: Path, device: str, hours_ago: float, **values) -> None:
    """Uma única leitura de `device`, de `hours_ago` horas atrás, com os valores dados."""
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).replace(second=0, microsecond=0)
    conn = db.connect(str(path))
    db.insert_batch(conn, device, [{"device_id": device, "boot_id": 1, "seq": 0, "uptime_s": 0, "schema_version": "1",
                                    "quality": "ok", "ts_sensor": db.iso(ts), "ts_received": db.iso(ts),
                                    **{**synthetic(ts, {}), **values}}], ts)
    conn.close()


def test_no_sem_dados_nao_mostra_a_ultima_leitura_como_se_fosse_atual(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_last_reading(app_env, "no-02", hours_ago=27, pm25=0.0, pm10=0.0)  # o nó parou com a leitura em zero
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception

    pm25 = [m for m in at.metric if m.label == "PM2,5"]
    assert pm25[1].value == "—"                  # no-02: nem 0,0 µg/m³ nem a faixa "Boa"
    assert not pm25[1].delta
    assert len(at.metric) == 5                   # os 4 do no-01 e só o PM2,5 do no-02
    assert any("sem dados" in c.value for c in at.caption)

    last = at.expander[0]                        # a última leitura segue acessível, dita como histórico
    assert last.label == "Ver a última leitura recebida"
    text = " ".join(c.value for c in last.caption)
    assert "histórico" in text and "0,0 µg/m³" in text


def test_no_em_operacao_continua_com_todos_os_indicadores_e_sem_expansor(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert len(at.metric) == 4
    assert len(at.expander) == 0


def aq_scales(at) -> list[str]:
    """Os HTMLs das escalas de faixas que a página desenhou, um por nó com leitura atual."""
    return [h.proto.body for h in at.get("html") if 'class="aq-scale"' in h.proto.body]


def test_cartao_do_no_em_operacao_mostra_a_escala_das_faixas_com_a_leitura_por_extenso(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    scales = aq_scales(at)
    assert len(scales) == 1
    assert re.search(r'aria-label="PM2,5 de \d+,\d µg/m³, na faixa (Boa|Moderada|Ruim|Muito ruim|Péssima)"', scales[0])


def test_no_sem_dados_nao_mostra_a_escala_das_faixas(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_last_reading(app_env, "no-02", hours_ago=27, pm25=0.0, pm10=0.0)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert len(aq_scales(at)) == 1                 # só o no-01: o zero do no-02 não vira uma leitura na escala


def test_todo_grafico_tem_descricao_para_o_leitor_de_tela(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_dead_hours(app_env, "no-01", [10])        # com horas fora, a série horária também desenha a faixa
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    descriptions = [json.loads(c.proto.spec).get("description") for c in at.get("vega_lite_chart")]
    assert len(descriptions) == 5 and all(descriptions), descriptions     # 6 h, PM2,5, umidade, faixa e previsão
    assert any(d.startswith("Gráfico de linhas") and "PM2,5" in d and "no-01" in d for d in descriptions)
    assert any(d.startswith("Faixa das horas sem média") for d in descriptions)
    assert any("observado" in d.lower() and "persistência" in d.lower() for d in descriptions)


def test_cartao_do_no_poe_o_sinal_wifi_numa_linha_a_parte(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert [m.label for m in at.metric] == ["PM2,5", "PM10 (µg/m³)", "Temperatura", "Umidade"]
    wifi = [c.value for c in at.caption if c.value.startswith("Sinal Wi-Fi")]
    assert len(wifi) == 1 and re.fullmatch(r"Sinal Wi-Fi: -?\d+ dBm", wifi[0])


def test_numeros_do_painel_usam_virgula_decimal(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_last_reading(app_env, "no-02", hours_ago=27)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    values = [m.value for m in at.metric if m.value != "—"]
    assert values and all("." not in v and "," in v for v in values), values
    stale = [c.value for c in at.caption if "sem dados" in c.value]
    assert len(stale) == 1 and re.search(r"último envio há \d+,\d h", stale[0]), stale


def test_periodo_tem_atalhos_e_so_o_personalizado_pede_datas(app_env):
    populate(app_env, hours=3)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    period = at.segmented_control[0]
    assert period.label == "Período" and list(period.options) == ["7 dias", "30 dias", "Personalizado"]
    assert period.value == "7 dias" and len(at.date_input) == 0
    period.set_value("Personalizado").run()
    assert not at.exception, at.exception
    assert len(at.date_input) == 1


def test_30_dias_em_um_minuto_avisa_do_limite(app_env):
    populate(app_env, hours=3)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    at.segmented_control[0].set_value("30 dias").run()
    at.radio[0].set_value("1 minuto").run()
    assert not at.exception, at.exception
    assert any("até 7 dias" in i.value for i in at.info)


def test_serie_horaria_conta_as_horas_sem_media_por_causa(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_dead_hours(app_env, "no-01", [10])
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    note = [c.value for c in at.caption if c.value.startswith("Horas sem média")]
    assert len(note) == 1
    assert "1 suspeita" in note[0] and re.search(r"\d+ sem leituras", note[0])   # as causas com zero hora não entram
    assert len(at.get("vega_lite_chart")) == 5       # 6 h, PM2,5, umidade, faixa das horas sem média e previsão


def test_serie_horaria_mostra_o_no_que_parou_como_sem_leituras_ate_agora(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_last_reading(app_env, "no-02", hours_ago=27)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    note = next(c.value for c in at.caption if c.value.startswith("Horas sem média"))
    assert int(re.search(r"(\d+) sem leituras", note).group(1)) >= 20     # as horas desde que o no-02 parou


def test_resolucao_de_um_minuto_nao_mostra_a_faixa_das_horas_sem_media(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_dead_hours(app_env, "no-01", [10])
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    at.radio[0].set_value("1 minuto").run()
    assert not at.exception, at.exception
    assert not any(c.value.startswith("Horas sem média") for c in at.caption)


def add_dead_hours(path: Path, device: str, hours_ago: list[int]) -> None:
    """Uma hora cheia de leituras com PM1, PM2,5 e PM10 em zero, para cada `hours_ago` (horas antes da hora atual)."""
    top = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    conn = db.connect(str(path))
    for k in hours_ago:
        start = top - timedelta(hours=k)
        dead = {**synthetic(start, {}), "pm25": 0.0, "pm1": 0.0, "pm10": 0.0}
        db.insert_batch(conn, device, [{"device_id": device, "boot_id": 9, "seq": k * 60 + m, "uptime_s": 0,
                                        "schema_version": "1", "quality": "ok",
                                        "ts_sensor": db.iso(start + timedelta(minutes=m)),
                                        "ts_received": db.iso(start + timedelta(minutes=m)), **dead}
                                       for m in range(60)], start)
    conn.close()


def test_serie_horaria_conta_as_horas_suspeitas_que_ficaram_de_fora(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_dead_hours(app_env, "no-01", [10])
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert any("1 hora suspeita ficou de fora (no-01: 1)" in c.value for c in at.caption)


def test_aviso_das_horas_suspeitas_nao_afirma_o_que_o_ar_faz_e_leva_os_criterios_num_expansor(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_dead_hours(app_env, "no-01", [10])
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception

    notes = [c.value for c in at.caption if "hora suspeita ficou de fora" in c.value]
    assert len(notes) == 1 and "abaixo de" not in notes[0]       # o aviso é curto: os limites ficam no expansor
    assert not any("o que o ar não faz" in c.value for c in at.caption)

    criteria = [e for e in at.expander if e.label == "Critério das horas suspeitas"]
    assert len(criteria) == 1
    text = " ".join(c.value for c in criteria[0].caption)
    assert "25%" in text and "0,5 µg/m³" in text and "1,0 µg/m³" in text        # a regra aplicada
    assert "falha do sensor" in text and "ar muito limpo" in text and "CETESB" in text  # a causa não está decidida


def trend_head(at) -> str:
    """O HTML da linha acima do gráfico de 6 horas, com o período, a legenda e os avisos dos nós calados."""
    return next(h.proto.body for h in at.get("html") if 'class="aq-trend-head"' in h.proto.body)


def test_grafico_de_seis_horas_tem_titulo_curto_e_uma_linha_so_com_periodo_e_legenda(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert "#### PM2,5 · últimas 6 horas" in [m.value for m in at.markdown]
    head = trend_head(at)
    assert re.search(r"\d{2}(/\d{2}|–\d{2}/\d{2}| a \d{2}/\d{2}) · µg/m³", head)    # o período e a unidade
    assert "no-01" in head and "background:#22b8cf" in head                            # a legenda, com a cor do nó
    assert "sem leituras" not in head


def test_grafico_de_seis_horas_nao_repete_titulo_e_legenda_dentro_do_grafico(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    spec = json.loads(at.get("vega_lite_chart")[0].proto.spec)
    assert "title" not in spec                       # o título e o período já vêm acima do gráfico
    colors = [layer["encoding"]["color"] for layer in spec.get("layer", [spec]) if "color" in layer.get("encoding", {})]
    assert colors and all(c.get("legend") is None for c in colors)     # e a legenda também


def test_cabecalho_do_grafico_explica_o_no_que_nao_enviou_nada(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_last_reading(app_env, "no-02", hours_ago=27)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    head = trend_head(at)
    assert "no-02 · sem leituras neste período" in head and "no-01 · sem" not in head
    assert not any("sem leituras nas últimas" in c.value for c in at.caption)   # o aviso saiu de baixo do gráfico


def test_cabecalho_do_grafico_nao_avisa_quando_todos_os_nos_enviaram(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1), ("no-02", 1)))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    head = trend_head(at)
    assert "sem leituras" not in head and "no-01" in head and "no-02" in head


def test_cabecalho_do_grafico_avisa_quando_nenhum_no_enviou(app_env):
    conn = db.connect(str(app_env))
    db.init_db(conn)
    conn.close()
    add_last_reading(app_env, "no-01", hours_ago=30)
    add_last_reading(app_env, "no-02", hours_ago=27)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert "no-01, no-02 · sem leituras neste período" in trend_head(at)


def test_aviso_das_horas_suspeitas_separa_a_contagem_por_no(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1), ("no-02", 1)))
    add_dead_hours(app_env, "no-01", [10])
    add_dead_hours(app_env, "no-02", [12, 11])
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert any("3 horas suspeitas ficaram de fora (no-01: 1, no-02: 2)" in c.value for c in at.caption)


def test_aviso_das_horas_suspeitas_so_cita_os_nos_com_horas_suspeitas(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1), ("no-02", 1)))
    add_dead_hours(app_env, "no-02", [10])
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert any("1 hora suspeita ficou de fora (no-02: 1)" in c.value for c in at.caption)


def test_sem_horas_suspeitas_a_serie_horaria_nao_menciona_o_assunto(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert not any("suspeita" in c.value for c in at.caption)


def test_mostra_a_versao_do_firmware_quando_o_no_informa(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1), ("no-02", 1)))
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    conn = db.connect(str(app_env))
    db.insert_batch(conn, "no-01", [{"device_id": "no-01", "boot_id": 1, "seq": 3 * 60, "ts_sensor": db.iso(now),
                                     "ts_received": db.iso(now), "uptime_s": 3 * 3600, "schema_version": "1",
                                     "quality": "ok", **synthetic(now, {})}], now, firmware="build Oct 26 2026")
    conn.close()
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    firmware = [c.value for c in at.caption if "Firmware" in c.value]
    assert firmware == ["Firmware: build Oct 26 2026"]               # o no-02 não informa: nada é mostrado


def test_avisa_quando_a_ultima_leitura_foi_marcada(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    conn = db.connect(str(app_env))  # a tabela é imutável: a leitura marcada entra como a mais recente
    db.insert_batch(conn, "no-01", [{"device_id": "no-01", "boot_id": 1, "seq": 3 * 60, "ts_sensor": db.iso(now),
                                     "ts_received": db.iso(now), "uptime_s": 3 * 3600, "schema_version": "1",
                                     "quality": "umid_fora_faixa", **synthetic(now, {}), "humidity": 120.0}], now)
    conn.close()
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert any("implausível (umid_fora_faixa)" in c.value for c in at.caption)


def test_troca_para_resolucao_de_um_minuto(app_env):
    populate(app_env, hours=3)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    at.radio[0].set_value("1 minuto").run()
    assert not at.exception, at.exception


def test_no_em_operacao_com_leitura_zerada_fica_sem_faixa_e_diz_por_que(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_last_reading(app_env, "no-02", hours_ago=0.02, pm1=0.0, pm25=0.0, pm10=0.0)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception

    pm25 = [m for m in at.metric if m.label == "PM2,5"]
    assert pm25[1].value == "0,0"                # o valor segue visível: é o que o nó enviou
    assert not pm25[1].delta                     # mas sem o selo "Boa", que um sensor parado em zero não merece
    assert len(aq_scales(at)) == 1               # a escala é só do no-01
    notes = [c.value for c in at.caption if "Leitura zerada" in c.value]
    assert len(notes) == 1
    assert "PM1, PM2,5 e PM10" in notes[0] and "pode não estar vendo partículas" in notes[0]
    assert "sem faixa" in notes[0]


def test_leitura_com_particulas_nao_traz_o_aviso_de_leitura_zerada(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert not [c for c in at.caption if "zerada" in c.value]
    assert [m for m in at.metric if m.label == "PM2,5"][0].delta


def test_pm10_leva_a_unidade_no_rotulo_para_o_valor_caber_na_coluna_estreita(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    pm10 = next(m for m in at.metric if m.label.startswith("PM10"))
    assert re.fullmatch(r"\d+,\d", pm10.value), pm10.value   # "50,9 µg/m³" ficava cortado num cartão de meia tela


@pytest.mark.parametrize("values, named", [
    ({"pm1": None, "pm25": 0.0, "pm10": 0.0}, "(PM2,5 e PM10 em 0,0)"),
    ({"pm1": 0.0, "pm25": 0.0, "pm10": None}, "(PM1 e PM2,5 em 0,0)"),
])
def test_nota_da_leitura_zerada_cita_so_as_particulas_que_o_no_enviou(app_env, values, named):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_last_reading(app_env, "no-02", hours_ago=0.02, **values)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    notes = [c.value for c in at.caption if "Leitura zerada" in c.value]
    assert len(notes) == 1 and notes[0].startswith(f"Leitura zerada {named}:"), notes


def shown(table):
    """O que a tabela escreve nas células: os valores formatados pelo Styler, ou os próprios valores sem ele."""
    display = table.proto.arrow_data.styler.display_values
    if not display:
        return table.value.astype(str)
    return pa.ipc.open_stream(display).read_all().to_pandas()


def has_decimal_point(text) -> bool:
    return bool(text.apply(lambda col: col.str.contains(".", regex=False)).any().any())


def test_tabela_de_saude_escreve_os_numeros_com_virgula_e_mantem_a_barra(app_env):
    populate(app_env)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    table = at.dataframe[0]
    assert list(table.value.columns[:3]) == ["Sensor", "Completude", "%"]  # a barra e o número ao lado dela
    text = shown(table)
    assert text["%"].str.fullmatch(r"\d+,\d\d%").all(), list(text["%"])
    assert not has_decimal_point(text), text


def test_tabela_de_previsao_escreve_os_numeros_com_virgula(app_env):
    populate(app_env)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    text = shown(at.dataframe[1])
    for column in ("MAE (µg/m³)", "RMSE (µg/m³)", "Skill score"):
        assert text[column].str.fullmatch(r"-?\d+,\d\d").all(), (column, list(text[column]))
    assert not has_decimal_point(text), text


def page_style(at) -> str:
    return next(h.proto.body for h in at.get("html") if "stMainBlockContainer" in h.proto.body)


def wide_screen_rules(at) -> str:
    """As regras que valem a partir de 640 px, a largura em que o Streamlit deixa de empilhar as colunas."""
    block = re.search(r"@media \(min-width: 640px\) \{(.*?)\n\}", page_style(at), re.S)
    assert block, "faltam as regras do cabeçalho para telas largas"
    return block.group(1)


def rem_of(rules: str, selector: str, prop: str) -> float:
    match = re.search(rf"{re.escape(selector)}\s*\{{[^}}]*?{prop}:\s*([\d.]+)rem", rules)
    assert match, f"{selector} sem {prop} em rem"
    return float(match.group(1))


def test_cabecalho_em_tela_larga_gasta_menos_altura(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    rules = wide_screen_rules(at)
    assert 1.5 <= rem_of(rules, "[data-testid='stMainBlockContainer']", "padding-top") <= 2.0   # 24 a 32 px (era 56)
    assert 1.625 <= rem_of(rules, "h1", "font-size") <= 1.75                                   # 26 a 28 px (era 44)
    assert rem_of(rules, "h1", "padding-bottom") <= 0.5                                         # o título junto das abas
    assert rem_of(rules, "[role='tabpanel']", "padding-top") <= 0.5                             # e as abas, do conteúdo
    # A barra do Streamlit fica por cima do conteúdo e tem fundo sólido: com a margem menor ela esconderia o título.
    assert re.search(r"\[data-testid='stHeader'\]\s*\{[^}]*background:\s*transparent", rules)


def test_cabecalho_no_celular_segue_como_esta(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    # Fora da regra de tela larga a margem de cima fica em 3,5rem: no celular a barra do Streamlit cobriria uma menor.
    assert "padding-top: 3.5rem" in page_style(at).split("@media")[0]


def set_location(path: Path, device: str, location: str) -> None:
    conn = db.connect(str(path))
    db.set_location(conn, device, location)
    conn.close()


def test_cartao_junta_nome_e_local_no_titulo(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1), ("no-02", 2)))
    set_location(app_env, "no-01", "Osasco")
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert [s.value for s in at.subheader][:2] == ["no-01 · Osasco", "no-02"]   # sem local, só o nome
    assert "Osasco" not in [c.value for c in at.caption]                          # o local não ganha uma linha só dele


def test_unidade_do_pm25_vai_menor_ao_lado_do_valor(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    pm25 = [m for m in at.metric if m.label == "PM2,5"][0]
    assert re.fullmatch(r"\d+,\d", pm25.value), pm25.value        # o valor é só o número...
    # ...e a unidade é escrita pelo estilo, menor e com peso normal, só onde há uma leitura (não no "—" do nó sem dados).
    unit = re.search(r"st-key-hero-'\]:not\(\[class\*='st-key-hero-empty-'\]\)[^{]*::after\s*\{([^}]*)\}", page_style(at))
    assert unit, "falta a regra que escreve a unidade ao lado do valor"
    assert 'content: " µg/m³"' in unit.group(1) and "font-weight: 400" in unit.group(1)


def test_cartao_do_no_em_tela_larga_tem_blocos_mais_juntos(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    rules = wide_screen_rules(at)
    node = "[data-testid='stVerticalBlock'][class*='st-key-node-']"
    assert rem_of(rules, node, "gap") <= 0.75                                   # 12 px entre os grupos (eram 16)
    assert rem_of(rules, node, "padding") <= 0.75                               # e 12 px de margem interna
    assert rem_of(rules, "[data-testid='stHeading'] h3", "font-size") <= 1.5   # o nome do nó não domina o cartão
    # O selo da faixa fica ao lado do valor, não numa linha só dele: a grade põe o rótulo em cima e os dois embaixo.
    grid = re.search(r"\[data-testid='stMetric'\] > div \{([^}]*)\}", rules)
    assert grid and "display: grid" in grid.group(1), "falta a grade do PM2,5 com o selo da faixa ao lado do valor"
    # A escala junto das métricas. O seletor leva o cartão: a regra-base da escala vem depois no CSS e venceria um empate.
    assert rem_of(rules, "[class*='st-key-hero-'] .aq-scale", "margin-bottom") <= 0.5
    # O Streamlit tira 16 px da altura do título para compensar o espaço que ele mesmo põe embaixo; sem esse espaço, a
    # compensação encurtaria a caixa do título e o texto cairia sobre a linha do estado.
    assert re.search(r"\[data-testid='stMarkdownContainer'\]\s*\{[^}]*margin-bottom:\s*0[;} ]", rules)
