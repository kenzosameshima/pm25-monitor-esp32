"""Verifica o transporte HTTPS entre redes: envia uma leitura sintética e confere o 201.

Roda no computador de quem faz a instalação, em qualquer rede, contra o endereço público do túnel.
Cadastre antes um dispositivo de teste no servidor (PM25_DEVICE_TOKENS=...,teste-https:<token>) para
não misturar a leitura sintética com os dados dos nós; a tabela `measurements` é imutável.

Exemplo:
  python -m scripts.check_https --url https://MAQUINA.TAILNET.ts.net/v1/measurements --token TOKEN_DO_TESTE

Códigos de saída: 0 sucesso; 1 uso incorreto; 2 certificado inválido; 3 token recusado (401);
4 device_id diferente do token (403); 5 IP bloqueado por tentativas inválidas (429); 6 tempo esgotado;
7 outra resposta HTTP; 8 falha de conexão (DNS, recusada, sem rota).
"""

import argparse
import json
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from scripts.simulate_sensor import synthetic

OK, USO, CERTIFICADO, NAO_AUTORIZADO, DEVICE_DIFERENTE, BLOQUEADO, TEMPO_ESGOTADO, HTTP_INESPERADO, CONEXAO = range(9)


def montar_leitura() -> dict:
    """Uma leitura do minuto atual. O boot_id muda a cada execução, então reexecutar nunca colide."""
    agora = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    return {"boot_id": int(time.time()) % 2**31, "seq": 0, "ts": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "uptime_s": 60, **synthetic(agora, {})}


def enviar(url: str, token: str, device: str, timeout: float) -> tuple[int, str]:
    """Envia uma leitura. Retorna (código de saída, mensagem para o usuário)."""
    corpo = json.dumps({"schema_version": "1", "device_id": device, "readings": [montar_leitura()]}).encode()
    req = urllib.request.Request(
        url, data=corpo, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    inicio = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status, texto = resp.status, resp.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        status, texto = e.code, e.read().decode(errors="replace")
    except urllib.error.URLError as e:
        return _falha_de_conexao(e.reason, timeout)
    except TimeoutError:
        return TEMPO_ESGOTADO, _msg_tempo(timeout)
    except ssl.SSLError as e:
        return _falha_de_conexao(e, timeout)
    except OSError as e:
        return CONEXAO, f"FALHA: conexão interrompida ({e})."

    duracao = time.monotonic() - inicio
    if status == 201:
        return OK, f"OK: HTTP 201 em {duracao:.1f} s, resposta {texto.strip()}"
    if status == 401:
        return NAO_AUTORIZADO, "FALHA: HTTP 401. Token ausente ou inválido para este servidor."
    if status == 403:
        return DEVICE_DIFERENTE, (f"FALHA: HTTP 403. O token não pertence ao device_id '{device}'; "
                                  "use --device com o identificador cadastrado para este token.")
    if status == 429:
        return BLOQUEADO, "FALHA: HTTP 429. O servidor bloqueou este IP por tentativas inválidas; aguarde alguns minutos."
    return HTTP_INESPERADO, f"FALHA: HTTP {status} inesperado (esperado 201). Resposta: {texto.strip()[:300]}"


def _msg_tempo(timeout: float) -> str:
    return (f"FALHA: sem resposta em {timeout:g} s. Confira se o túnel está ativo no servidor "
            "(tailscale funnel status) e se a API está em execução.")


def _falha_de_conexao(motivo: object, timeout: float) -> tuple[int, str]:
    if isinstance(motivo, ssl.SSLCertVerificationError):
        return CERTIFICADO, (f"FALHA: certificado não validado ({motivo.verify_message}). "
                             "Confira o endereço (deve ser o nome público do túnel) e o relógio deste computador.")
    if isinstance(motivo, ssl.SSLError):
        return CONEXAO, f"FALHA: erro TLS ({motivo}). O endereço pode não estar com HTTPS ativo."
    if isinstance(motivo, TimeoutError):
        return TEMPO_ESGOTADO, _msg_tempo(timeout)
    if isinstance(motivo, socket.gaierror):
        return CONEXAO, f"FALHA: nome não encontrado ({motivo}). Confira o endereço e a conexão deste computador."
    return CONEXAO, f"FALHA: não foi possível conectar ({motivo})."


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):
        # O argparse sairia com 2, que aqui significa "certificado inválido".
        self.print_usage(sys.stderr)
        print(f"{self.prog}: erro: {message}", file=sys.stderr)
        sys.exit(USO)


def main(argv: list[str] | None = None) -> int:
    ap = _Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="endereço completo, terminando em /v1/measurements")
    ap.add_argument("--token", required=True, help="token do dispositivo de teste")
    ap.add_argument("--device", default="teste-https", help="device_id cadastrado para o token (padrão: teste-https)")
    ap.add_argument("--timeout", type=float, default=15.0, help="segundos de espera pela resposta (padrão: 15)")
    ap.add_argument("--permitir-http", action="store_true", help="aceita URL http:// (só para testes locais)")
    args = ap.parse_args(argv)

    esquema = urllib.parse.urlsplit(args.url).scheme
    if esquema not in ("http", "https"):
        print("FALHA: a URL precisa começar com https://", file=sys.stderr)
        return USO
    if esquema == "http" and not args.permitir_http:
        print("FALHA: a URL usa http://, sem criptografia. Use https:// (ou --permitir-http em testes locais).",
              file=sys.stderr)
        return USO

    codigo, mensagem = enviar(args.url, args.token, args.device, args.timeout)
    print(mensagem, file=sys.stdout if codigo == OK else sys.stderr)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
