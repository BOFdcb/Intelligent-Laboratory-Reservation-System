from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "智能实验室预约系统"
    DEBUG: bool = True

    SECRET_KEY: str = "dev-secret"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080

    DATABASE_URL: str = "sqlite:///./data/lab.db"

    LLM_BASE_URL: str = "https://api.minimax.cn/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "MiniMax-M3"

    SILICONFLOW_BASE_URL: str = "https://api.siliconflow.cn/v1"
    SILICONFLOW_API_KEY: str = ""
    EMBED_MODEL_NAME: str = "Pro/BAAI/bge-m3"
    EMBED_DIM: int = 1024

    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8000


settings = Settings()
