
import time
import logging

from langchain_core.prompts import ChatPromptTemplate

from app.providers.groq_provider import GroqProvider
from app.prompts.templates import SYSTEM_PROMPT
from app.core.observability import record_llm_request
from app.services.cost_service import calculate_cost


logger = logging.getLogger(__name__)


class LLMService:

    def __init__(self):
        self.provider = GroqProvider()

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", "{question}")
        ])

        self.chain = self.prompt | self.provider.llm

    def generate_response(self, question: str):

        start_time = time.perf_counter()
        model = self.provider.llm.model_name

        try:
            result = self.chain.invoke({
                "question": question
            })

            latency = round(
                time.perf_counter() - start_time, 3
            )

            answer = result.content
            usage = result.usage_metadata or {}

            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            total_tokens = usage.get(
                "total_tokens",
                input_tokens + output_tokens
            )

            # Calculate estimated request cost.
            try:
                cost = calculate_cost(
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens
                )

                input_cost = cost["input_cost"]
                output_cost = cost["output_cost"]
                total_cost = cost["total_cost"]

            except Exception:
                # Cost monitoring must not break LLM inference.
                logger.exception(
                    "Cost calculation failed for model %s",
                    model
                )

                input_cost = 0
                output_cost = 0
                total_cost = 0

            # Record successful request and cost.
            record_llm_request(
                provider="Groq",
                model=model,
                status="success",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                latency_seconds=latency,
                question_length=len(question),
                answer_length=len(answer),
                input_cost=input_cost,
                output_cost=output_cost,
                total_cost=total_cost
            )

            return {
                "answer": answer,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "latency_seconds": latency
            }

        except Exception as exc:

            latency = round(
                time.perf_counter() - start_time, 3
            )

            record_llm_request(
                provider="Groq",
                model=model,
                status="failed",
                latency_seconds=latency,
                error_type=type(exc).__name__,
                question_length=len(question)
            )

            raise
