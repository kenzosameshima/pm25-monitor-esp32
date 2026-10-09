"""Testes do check_https.py contra um servidor HTTP local falso, sem rede e sem o túnel.

O erro de certificado exige TLS real e fica como verificação manual (ver README).
"""

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.models import Batch
from scripts import check_https

TOKEN_OK = "token-de-teste-0000000000"


class Falso(BaseHTTPRequestHandler):
    recebidos: list[dict] = []
    atraso_s = 0.0

    def do_POST(self):
        corpo = self.rfile.read(int(self.headers["Content-Length"]))
        if self.atraso_s:
            time.sleep(self.atraso_s)
        auth = self.headers.get("Authorization")
        if auth != f"Bearer {TOKEN_OK}":
            self._responder(401, {"detail": "Não autorizado"})
            return
        self.recebidos.append({"body": json.loads(corpo), "path": self.path})
        self._responder(201, {"inserted": 1, "duplicates": 0})

    def _responder(self, codigo, corpo):
        dados = json.dumps(corpo).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        try:
            self.wfile.write(dados)
        except OSError:  # o cliente desistiu (teste de tempo esgotado)
            pass

    def log_message(self, *args):
        pass


@pytest.fixture
def servidor():
    handler = type("H", (Falso,), {"recebidos": [], "atraso_s": 0.0})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    srv.handler = handler
    srv.url = f"http://127.0.0.1:{srv.server_port}/v1/measurements"
    yield srv
    srv.shutdown()
    srv.server_close()


def rodar(url, token, *extra):
    return check_https.main(["--url", url, "--token", token, "--permitir-http", *extra])


def test_201_retorna_zero_e_envia_uma_leitura_valida_no_contrato(servidor, capsys):
    assert rodar(servidor.url, TOKEN_OK) == 0
    assert "HTTP 201" in capsys.readouterr().out
    (recebido,) = servidor.handler.recebidos
    batch = Batch.model_validate(recebido["body"])           # o mesmo contrato da API
    assert batch.device_id == "teste-https"
    assert len(batch.readings) == 1


def test_device_personalizado_vai_no_corpo(servidor):
    assert rodar(servidor.url, TOKEN_OK, "--device", "no-09") == 0
    assert servidor.handler.recebidos[0]["body"]["device_id"] == "no-09"


def test_401_retorna_codigo_proprio_e_mensagem_clara(servidor, capsys):
    assert rodar(servidor.url, "token-errado-00000000") == check_https.NAO_AUTORIZADO
    err = capsys.readouterr().err
    assert "401" in err and "Token" in err


def test_tempo_esgotado_retorna_codigo_proprio(servidor, capsys):
    servidor.handler.atraso_s = 1.5
    assert rodar(servidor.url, TOKEN_OK, "--timeout", "0.3") == check_https.TEMPO_ESGOTADO
    assert "sem resposta" in capsys.readouterr().err


def test_conexao_recusada_retorna_codigo_proprio(capsys):
    with socket.socket() as s:                                # porta livre, sem ninguém escutando
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    assert rodar(f"http://127.0.0.1:{porta}/v1/measurements", TOKEN_OK) == check_https.CONEXAO
    assert "FALHA" in capsys.readouterr().err


def test_url_http_e_recusada_sem_a_opcao_explicita(servidor, capsys):
    assert check_https.main(["--url", servidor.url, "--token", TOKEN_OK]) == check_https.USO
    assert "https://" in capsys.readouterr().err
    assert servidor.handler.recebidos == []


def test_argumento_faltando_nao_colide_com_o_codigo_de_certificado():
    with pytest.raises(SystemExit) as saida:
        check_https.main(["--url", "https://exemplo.invalido/v1/measurements"])
    assert saida.value.code == check_https.USO != check_https.CERTIFICADO
