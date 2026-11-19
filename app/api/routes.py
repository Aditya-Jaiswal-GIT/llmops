
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.services.notification_queue import get_notification_history
from app.services.llm_service import LLMService
from app.core.observability import (
    get_request_metrics,
    get_recent_requests,
    get_cost_metrics
)
from app.core.observability import get_request_trends
router = APIRouter(prefix="/api/v1", tags=["LLM"])


class ChatRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        description="Question to send to the LLM"
    )


class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int


class ChatResponse(BaseModel):
    success: bool
    provider: str
    response: str
    model: str
    token_usage: TokenUsage
    latency_seconds: float


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):

    try:
        llm_service = LLMService()

        result = llm_service.generate_response(
            request.question
        )

        return {
            "success": True,
            "provider": "Groq",
            "response": result["answer"],
            "model": result["model"],
            "token_usage": {
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "total_tokens": result["total_tokens"]
            },
            "latency_seconds": result["latency_seconds"]
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM provider error: {str(e)}"
        )

@router.get("/monitoring/metrics")
def monitoring_metrics():
    return get_request_metrics()


@router.get("/monitoring/recent")
def monitoring_recent_requests(limit: int = 20):
    limit = max(1, min(limit, 100))
    return get_recent_requests(limit)



@router.get("/monitoring/costs")
def monitoring_costs():
    return get_cost_metrics()

@router.get("/monitoring/trends")
def monitoring_trends(days: int = 7):
    days = max(1, min(days, 90))
    return get_request_trends(days)


@router.get("/monitoring/notifications")
def monitoring_notifications(limit: int = 50):

    limit = max(1, min(limit, 500))

    return get_notification_history(limit=limit)