from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    OPENAI_API_BASE: str
    OPENAI_API_KEY: str
    # PINECONE_API_KEY: str
    # PINECONE_ENVIRONMENT: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()