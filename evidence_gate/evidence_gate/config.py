from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env from project root
_env_path = Path(__file__).resolve().parents[2] / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EVIDENCE_GATE_")

    jira_base_url: str = ""
    jira_username: str = ""
    jira_password: str = ""

    quickwit_enabled: bool = True
    quickwit_url: str = ""
    quickwit_username: str = ""
    quickwit_password: str = ""

    metabase_enabled: bool = True
    metabase_url: str = ""
    metabase_username: str = ""
    metabase_password: str = ""

    data_dir: str = ".data"

    @property
    def data_path(self) -> Path:
        return Path(__file__).resolve().parents[1] / self.data_dir


settings = Settings()
