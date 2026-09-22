"""Configuração do servidor, lida de variáveis de ambiente (ou do arquivo .env)."""

import hmac
import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

# Carrega o .env do diretório atual sem sobrescrever variáveis já definidas.
load_dotenv(os.environ.get("PM25_ENV_FILE", ".env"))


@dataclass(frozen=True)
class Settings:
    db_path: str
    device_tokens: dict[str, str]  # token -> device_id
    backup_dir: str
    backup_keep: int
    telegram_token: str
    telegram_chat_id: str
    alert_silence_min: int
    alert_state_path: str

    @property
    def device_ids(self) -> list[str]:
        return sorted(set(self.device_tokens.values()))

    def device_for_token(self, token: str) -> str | None:
        """Compara o token com todos os cadastrados em tempo constante."""
        found = None
        for known, device in self.device_tokens.items():
            if hmac.compare_digest(known.encode(), token.encode()):
                found = device
        return found


def _parse_tokens(raw: str) -> dict[str, str]:
    """Converte 'no-01:tokenA,no-02:tokenB' em {tokenA: 'no-01', tokenB: 'no-02'}."""
    tokens: dict[str, str] = {}
    for item in filter(None, (p.strip() for p in raw.split(","))):
        device, sep, token = item.partition(":")
        if not sep or not device or not token:
            raise ValueError(f"Entrada inválida em PM25_DEVICE_TOKENS: {item!r}")
        if len(token) < 16:
            raise ValueError(f"Token de {device} muito curto (mínimo 16 caracteres)")
        tokens[token] = device
    return tokens


@lru_cache
def get_settings() -> Settings:
    env = os.environ.get
    return Settings(
        db_path=env("PM25_DB_PATH", "data/pm25.db"),
        device_tokens=_parse_tokens(env("PM25_DEVICE_TOKENS", "")),
        backup_dir=env("PM25_BACKUP_DIR", "backups"),
        backup_keep=int(env("PM25_BACKUP_KEEP", "14")),
        telegram_token=env("PM25_TELEGRAM_TOKEN", ""),
        telegram_chat_id=env("PM25_TELEGRAM_CHAT_ID", ""),
        alert_silence_min=int(env("PM25_ALERT_SILENCE_MIN", "15")),
        alert_state_path=env("PM25_ALERT_STATE", "data/alert_state.json"),
    )
