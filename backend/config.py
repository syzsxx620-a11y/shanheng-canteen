from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    database_url: str = 'sqlite:///./data/platform.db'
    jwt_secret: str = ''
    cors_origins: list[str] = ['http://localhost:5173', 'http://127.0.0.1:5173']
    llm_base_url: str = ''
    llm_model: str = ''
    llm_api_key: str = ''
    llm_timeout: float = 15
    yolo_weights: str = ''
    image_retention_days: int = 7
    cookie_secure: bool = False
    data_dir: str = str(ROOT / 'data')

@lru_cache
def settings():
    return Settings()
