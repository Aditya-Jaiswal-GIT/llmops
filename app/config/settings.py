import os
from dotenv import load_dotenv

load_dotenv()


class Settings:

    APP_NAME = "Groq LLMOps Platform"

    APP_ENV = os.getenv("APP_ENV", "development")

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    GROQ_API_KEY = os.getenv("GROQ_API_KEY")

    GROQ_MODEL = os.getenv(
        "GROQ_MODEL",
        "openai/gpt-oss-120b"
    )

    TEMPERATURE = float(
        os.getenv("TEMPERATURE", "0.3")
    )

    MAX_TOKENS = int(
        os.getenv("MAX_TOKENS", "1000")
    )

    MAX_RETRIES = int(
        os.getenv("MAX_RETRIES", "3")
    )

    RETRY_WAIT_SECONDS = int(
        os.getenv("RETRY_WAIT_SECONDS", "2")
    )


settings = Settings()


def validate_settings():

    if not settings.GROQ_API_KEY:
        raise ValueError(
            "GROQ_API_KEY is missing in .env"
        )

    if settings.MAX_RETRIES < 1:
        raise ValueError("MAX_RETRIES must be at least 1")
