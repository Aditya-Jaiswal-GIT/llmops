
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]

PRICING_FILE = BASE_DIR / "app" / "config" / "model_pricing.json"


def load_pricing():

    with open(PRICING_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int
):

    pricing = load_pricing()

    if model not in pricing:
        raise ValueError(
            f"Pricing not configured for model: {model}"
        )

    model_pricing = pricing[model]

    input_rate = model_pricing["input_price_per_million"]
    output_rate = model_pricing["output_price_per_million"]

    input_cost = (
        input_tokens / 1_000_000
    ) * input_rate

    output_cost = (
        output_tokens / 1_000_000
    ) * output_rate

    total_cost = input_cost + output_cost

    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_cost": round(input_cost, 10),
        "output_cost": round(output_cost, 10),
        "total_cost": round(total_cost, 10),
        "currency": model_pricing.get("currency", "USD")
    }
