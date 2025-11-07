# Configuration using pydantic-settings
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    # API Settings
    PORT: int = 8000
    IMAGE_TAG: str = "local non docker"
    REDIS_URL: str = "redis://localhost:6379"
    DEBUG: bool = False
    
    # Security Settings
    ADMIN_API_KEY: str = ""  # API key for admin endpoints like /packages
    
    # Database Type Configuration
    DB_TYPE: Literal["neo4j", "postgresql", "mysql", "sqlite"] = "neo4j"
    
    # Neo4j Configuration
    NEO4J_URL: str = ""
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    
    # SQL Database Configuration
    DATABASE_URL: str = ""
    DB_NAME: str = ""
    DB_PORT: int = 5432

    class Config:
        env_file = ".env"


settings = Settings()