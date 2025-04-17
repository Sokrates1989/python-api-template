# Configuration using pydantic-settings
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PORT: int = 8000
    NEO4J_URL: str = ""
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    COGNITO_USER_POOL_ID: str = ""
    AWS_REGION: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""

    class Config:
        env_file = ".env"

settings = Settings()