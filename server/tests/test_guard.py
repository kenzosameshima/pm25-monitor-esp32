"""Testes do bloqueio de IP após falhas de autenticação."""

import pytest

from app import guard
from app.guard import AuthThrottle


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return Clock()


def fail(throttle: AuthThrottle, ip: str | None, times: int) -> None:
    for _ in range(times):
        throttle.register_failure(ip)


def test_abaixo_do_limite_o_ip_nao_e_bloqueado(clock):
    throttle = AuthThrottle(max_fails=3, block_s=300, clock=clock)
    fail(throttle, "10.0.0.1", 2)
    assert throttle.retry_after("10.0.0.1") == 0


def test_no_limite_o_ip_fica_bloqueado_pelo_tempo_configurado(clock):
    throttle = AuthThrottle(max_fails=3, block_s=300, clock=clock)
    fail(throttle, "10.0.0.1", 3)
    assert throttle.retry_after("10.0.0.1") == 300
    clock.now += 100.5
    assert throttle.retry_after("10.0.0.1") == 200                  # arredonda para cima


def test_depois_do_bloqueio_a_contagem_recomeca(clock):
    throttle = AuthThrottle(max_fails=3, block_s=300, clock=clock)
    fail(throttle, "10.0.0.1", 3)
    clock.now += 301
    assert throttle.retry_after("10.0.0.1") == 0
    fail(throttle, "10.0.0.1", 2)
    assert throttle.retry_after("10.0.0.1") == 0                    # 2 falhas novas, não 5
    fail(throttle, "10.0.0.1", 1)
    assert throttle.retry_after("10.0.0.1") == 300


def test_falhas_antigas_expiram_com_a_janela(clock):
    throttle = AuthThrottle(max_fails=3, block_s=300, clock=clock)
    fail(throttle, "10.0.0.1", 2)
    clock.now += 301
    fail(throttle, "10.0.0.1", 2)                                   # 2 + 2 seriam 4, mas as duas primeiras expiraram
    assert throttle.retry_after("10.0.0.1") == 0


def test_cada_ip_tem_a_sua_contagem(clock):
    throttle = AuthThrottle(max_fails=2, block_s=300, clock=clock)
    fail(throttle, "10.0.0.1", 2)
    assert throttle.retry_after("10.0.0.1") > 0 and throttle.retry_after("10.0.0.2") == 0


def test_ip_desconhecido_tambem_e_controlado(clock):
    throttle = AuthThrottle(max_fails=2, block_s=300, clock=clock)
    fail(throttle, None, 2)
    assert throttle.retry_after(None) > 0


def test_o_controle_descarta_os_ips_mais_antigos_acima_do_teto(clock, monkeypatch):
    monkeypatch.setattr(guard, "MAX_TRACKED_IPS", 2)
    throttle = AuthThrottle(max_fails=1, block_s=300, clock=clock)
    for ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):
        fail(throttle, ip, 1)
    assert throttle.retry_after("10.0.0.1") == 0                    # o mais antigo foi esquecido
    assert throttle.retry_after("10.0.0.2") > 0 and throttle.retry_after("10.0.0.3") > 0
