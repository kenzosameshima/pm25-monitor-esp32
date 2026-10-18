"""Configuração do servidor, lida de variáveis de ambiente (ou do arquivo .env)."""

import hmac
import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

# Carrega o .env do diretório atual sem sobrescrever variáveis já definidas.
load_dotenv(os.environ.get("PM25_ENV_FILE", ".env"))

# Os tokens de exemplo dos arquivos .example começam com "TROQUE-"; usados de verdade, seriam credenciais públicas.
PLACEHOLDER = "troque"


@dataclass(frozen=True)
class Settings:
    db_path: str
    device_tokens: dict[str, str]  # token -> device_id
    read_token: str                # token do app de consulta; vazio desliga as rotas de leitura
    backup_dir: str
    backup_keep: int
    models_dir: str                # modelos de previsão usados pelo job horário
    max_body_bytes: int
    auth_max_fails: int
    auth_block_s: int

    @property
    def device_ids(self) -> list[str]:
        return sorted(set(self.device_tokens.values()))

    def is_read_token(self, token: str) -> bool:
        return bool(self.read_token) and hmac.compare_digest(self.read_token.encode(), token.encode())

    def device_for_token(self, token: str) -> str | None:
        """Compara o token com todos os cadastrados em tempo constante."""
        found = None
        for known, device in self.device_tokens.items():
            if hmac.compare_digest(known.encode(), token.encode()):
                found = device
        return found


def _check_token(token: str, name: str) -> None:
    """Recusa token curto ou o exemplo dos arquivos .example ("TROQUE-..."), que é público no repositório."""
    if len(token) < 16:
        raise ValueError(f"{name} muito curto (mínimo 16 caracteres)")
    if PLACEHOLDER in token.lower():
        raise ValueError(f"{name} ainda é o exemplo do repositório: gere um com secrets.token_urlsafe(24)")


def _parse_tokens(raw: str) -> dict[str, str]:
    """Converte 'no-01:tokenA,no-02:tokenB' em {tokenA: 'no-01', tokenB: 'no-02'}."""
    tokens: dict[str, str] = {}
    for item in filter(None, (p.strip() for p in raw.split(","))):
        device, sep, token = item.partition(":")
        if not sep or not device or not token:
            raise ValueError(f"Entrada inválida em PM25_DEVICE_TOKENS: {item!r}")
        _check_token(token, f"Token de {device}")
        tokens[token] = device
    return tokens


def _parse_read_token(raw: str, device_tokens: dict[str, str]) -> str:
    token = raw.strip()
    if token:
        _check_token(token, "PM25_READ_TOKEN")
    if token in device_tokens:
        raise ValueError("PM25_READ_TOKEN não pode repetir o token de um nó")
    return token


@lru_cache
def get_settings() -> Settings:
    env = os.environ.get
    device_tokens = _parse_tokens(env("PM25_DEVICE_TOKENS", ""))
    return Settings(
        db_path=env("PM25_DB_PATH", "data/pm25.db"),
        device_tokens=device_tokens,
        read_token=_parse_read_token(env("PM25_READ_TOKEN", ""), device_tokens),
        backup_dir=env("PM25_BACKUP_DIR", "backups"),
        backup_keep=int(env("PM25_BACKUP_KEEP", "14")),
        models_dir=env("PM25_MODELS_DIR", "data/models"),
        # 256 KiB: um lote de 500 leituras (o máximo do contrato) ocupa cerca de 125 KiB.
        max_body_bytes=int(env("PM25_MAX_BODY_BYTES", str(256 * 1024))),
        auth_max_fails=int(env("PM25_AUTH_MAX_FAILS", "10")),
        auth_block_s=int(env("PM25_AUTH_BLOCK_MIN", "5")) * 60,
    )
