import subprocess
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / ".cache" / "llm"
DATA_DIR = ROOT / ".data" / "analyses"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(ROOT / ".env", ".env"), extra="ignore")

    openrouter_api_key: str = ""
    llm_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    llm_light_model: str = "nvidia/nemotron-3.5-super-vl:free"
    llm_validator_model: str = "nvidia/nemotron-3.5-super-vl:free"
    llm_fallback_models: str = "inclusionai/ling-3.2-flash:free,particle-ai/particle-1:free,google/gemma-4-31b-it:free"
    agent_version: str = "0.1.0"
    max_file_size_mb: int = 10
    llm_timeout: int = 90
    analysis_timeout: int = 900
    max_retries: int = 1
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    frontend_port: int = 5173

    @property
    def max_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def agent_version() -> str:
    """Версия для паспорта: тег или коммит git; вне git — значение из настроек."""
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "describe", "--tags", "--always", "--dirty"],
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return f"{get_settings().agent_version} ({out.stdout.strip()})"
    except (OSError, subprocess.SubprocessError):
        pass
    return get_settings().agent_version
