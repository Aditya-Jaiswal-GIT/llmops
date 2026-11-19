
from app.services.cost_service import calculate_cost


def test_cost_calculation():

    result = calculate_cost(
        model="openai/gpt-oss-120b",
        input_tokens=10000,
        output_tokens=5000
    )

    assert result["input_tokens"] == 10000
    assert result["output_tokens"] == 5000
    assert result["total_cost"] >= 0

    print(result)


if __name__ == "__main__":
    test_cost_calculation()
