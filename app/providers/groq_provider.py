from time import perf_counter

from groq import (
    RateLimitError,
    APIConnectionError,
    InternalServerError
)

from langchain_groq import ChatGroq
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

import logging

from app.config.settings import settings
from app.core.logger import get_logger


logger = get_logger(__name__)


class GroqProvider:

    def __init__(self):

        self.llm = ChatGroq(
            model=settings.GROQ_MODEL,
            api_key=settings.GROQ_API_KEY,
            temperature=settings.TEMPERATURE,
            max_tokens=settings.MAX_TOKENS
        )

        logger.info(
            "Groq provider initialized | model=%s",
            settings.GROQ_MODEL
        )

    @retry(
        retry=retry_if_exception_type((
            RateLimitError,
            APIConnectionError,
            InternalServerError
        )),
        stop=stop_after_attempt(settings.MAX_RETRIES),
        wait=wait_exponential(
            multiplier=settings.RETRY_WAIT_SECONDS,
            min=settings.RETRY_WAIT_SECONDS,
            max=15
        ),
        before_sleep=before_sleep_log(
            logger,
            logging.WARNING
        ),
        reraise=True
    )
    def invoke(self, messages):

        start = perf_counter()

        try:

            response = self.llm.invoke(messages)

            latency = round(
                perf_counter() - start,
                4
            )

            usage = response.usage_metadata or {}

            result = {
                "content": response.content,
                "model": settings.GROQ_MODEL,
                "latency_seconds": latency,
                "usage": {
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0)
                }
            }

            logger.info(
                "LLM request successful | model=%s | "
                "latency=%s | tokens=%s",
                settings.GROQ_MODEL,
                latency,
                result["usage"]["total_tokens"]
            )

            return result

        except Exception:

            logger.exception("Groq invocation failed")
            raise
