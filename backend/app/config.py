import subprocess
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / ".cache" / "llm"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(ROOT / ".env", ".env"), extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    gemini_light_model: str = "gemini-3.5-flash-lite"
    gemini_validator_model: str = "gemini-3.6-flash"
    gemini_fallback_models: str = (
        "gemini-4-hydrogen,gemini-3.5-flash,gemma-4-31b-it,gemma-4-26b-a4b-it,gemini-3.1-flash-lite")
    agent_version: str = "0.1.0"
    max_file_size_mb: int = 10
    llm_timeout: int = 120
    analysis_timeout: int = 900
    max_retries: int = 1
    llm_min_interval: float = 4.0
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
