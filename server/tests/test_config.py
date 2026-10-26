"""Testes da configuração do servidor: tokens aceitos, recusados e como são resolvidos."""

import secrets

import pytest

from app.config import get_settings

TOKEN_1 = "token-do-no-01-aB3xQ9zK7pLm2Wv8Rt"
TOKEN_2 = "token-do-no-02-aB3xQ9zK7pLm2Wv8Rt"
READ_TOKEN = "token-de-leitura-aB3xQ9zK7pLm2Wv8Rt"


@pytest.fixture
def env(monkeypatch):
    """Define as variáveis de ambiente e relê a configuração; limpa o cache antes e depois."""
    def configure(devices: str, read: str = "") -> None:
        monkeypatch.setenv("PM25_DEVICE_TOKENS", devices)
        monkeypatch.setenv("PM25_READ_TOKEN", read)
        get_settings.cache_clear()

    yield configure
    get_settings.cache_clear()


@pytest.mark.parametrize("devices, read", [
    ("no-01:TROQUE-este-token-do-no-01", ""),                 # exemplo do .env.example
    (f"no-01:{TOKEN_1}", "TROQUE-pelo-token-de-leitura"),    # exemplo do local.properties.example
])
def test_tokens_de_exemplo_do_repositorio_sao_recusados(env, devices, read):
    env(devices, read)
    with pytest.raises(ValueError, match="exemplo do repositório"):
        get_settings()


@pytest.mark.parametrize("raw, message", [
    ("curto", "muito curto"),
    ("a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5", "muito curto"),             # 30 caracteres: abaixo do mínimo de 32
    ("a" * 40, "poucos caracteres distintos"),                      # comprido, mas sem variedade
    ("abcdefghi" * 4, "poucos caracteres distintos"),               # 9 caracteres distintos
    (TOKEN_1, "repetir o token"),
])
def test_token_de_leitura_invalido_na_configuracao(env, raw, message):
    env(f"no-01:{TOKEN_1}", raw)
    with pytest.raises(ValueError, match=message):
        get_settings()


@pytest.mark.parametrize("devices, message", [
    ("no-01:abcdefghijklmnopqrstuvwxyz12345", "muito curto"),        # 31 caracteres
    ("no-01:" + "z" * 40, "poucos caracteres distintos"),
])
def test_token_fraco_de_no_e_recusado_na_configuracao(env, devices, message):
    env(devices)
    with pytest.raises(ValueError, match=message):
        get_settings()


def test_token_gerado_por_secrets_e_aceito(env):
    env(f"no-01:{secrets.token_urlsafe(24)}", secrets.token_urlsafe(24))
    assert get_settings().device_ids == ["no-01"]


def test_entrada_de_no_sem_token_e_recusada(env):
    env("no-01")
    with pytest.raises(ValueError, match="Entrada inválida"):
        get_settings()


def test_cada_token_identifica_o_seu_no(env):
    env(f"no-01:{TOKEN_1}, no-02:{TOKEN_2}", READ_TOKEN)
    settings = get_settings()
    assert settings.device_for_token(TOKEN_1) == "no-01" and settings.device_for_token(TOKEN_2) == "no-02"
    assert settings.device_for_token(READ_TOKEN) is None and settings.device_for_token("") is None


def test_token_de_leitura_so_vale_quando_configurado(env):
    env(f"no-01:{TOKEN_1}", READ_TOKEN)
    assert get_settings().is_read_token(READ_TOKEN) and not get_settings().is_read_token(TOKEN_1)
    env(f"no-01:{TOKEN_1}", "")
    assert not get_settings().is_read_token("")                      # leitura desligada: nem o token vazio entra
