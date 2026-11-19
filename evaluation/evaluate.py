
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import os
from tracking.mlflow_tracker import track_evaluation
from langchain_core.prompts import ChatPromptTemplate
import mlflow
from app.services.llm_service import LLMService
from evaluation.experiment_config import (
    PROMPT_VERSION,
    DATASET_VERSION
)

BASE_DIR = Path(__file__).resolve().parents[1]

DATASET_PATH = BASE_DIR / "evaluation" / "dataset.json"

RESULTS_DIR = BASE_DIR / "evaluation" / "results"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# Evaluation prompt for LLM-as-a-Judge

JUDGE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """
You are an impartial evaluator of AI-generated answers.

Evaluate the candidate answer against the question and reference answer.

Give three scores from 1 to 5:

1. correctness:
   Is the answer factually correct compared with the reference?

2. relevance:
   Does the answer directly address the question?

3. completeness:
   Does the answer cover the important information?

Scoring:
1 = Very poor
2 = Poor
3 = Acceptable
4 = Good
5 = Excellent

Do not reward an answer merely because it is long.

Return ONLY valid JSON with this exact structure:

{{
    "correctness": 4,
    "relevance": 5,
    "completeness": 4,
    "reason": "Short explanation"
}}

Do not include Markdown or code fences.
"""
    ),
    (
        "human",
        """
Question:
{question}

Reference answer:
{reference_answer}

Candidate answer:
{candidate_answer}
"""
    )
])



def load_dataset():

    with open(DATASET_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


def calculate_keyword_coverage(answer, required_keywords):

    if not required_keywords:
        return 1.0

    answer_lower = answer.lower()

    matched = [
        keyword
        for keyword in required_keywords
        if keyword.lower() in answer_lower
    ]

    return round(
        len(matched) / len(required_keywords), 2
    )


def parse_judge_response(raw_response):

    # Remove accidental Markdown code fences
    cleaned = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        raw_response.strip(),
        flags=re.IGNORECASE
    )

    result = json.loads(cleaned)

    required_fields = [
        "correctness",
        "relevance",
        "completeness",
        "reason"
    ]

    for field in required_fields:
        if field not in result:
            raise ValueError(
                f"Missing judge field: {field}"
            )

    for field in ["correctness", "relevance", "completeness"]:
        score = result[field]

        if isinstance(score, bool) or not isinstance(score, int):
            raise ValueError(f"Invalid score: {field}")

        if not 1 <= score <= 5:
            raise ValueError(f"Score must be between 1 and 5: {field}")

    return result


def evaluate_single_case(
    test_case,
    llm_service,
    judge_chain
):

    question = test_case["question"]

    print(f"\nEvaluating: {test_case['id']}")

    # Step 1: Generate candidate answer
    generation = llm_service.generate_response(question)

    candidate_answer = generation["answer"]

    # Step 2: Deterministic keyword coverage
    keyword_coverage = calculate_keyword_coverage(
        candidate_answer,
        test_case.get("required_keywords", [])
    )

    # Step 3: Ask the judge model to evaluate the answer
    judge_response = judge_chain.invoke({
        "question": question,
        "reference_answer": test_case["reference_answer"],
        "candidate_answer": candidate_answer
    })

    judge_result = parse_judge_response(
        judge_response.content
    )

    # Step 4: Calculate combined score
    correctness = judge_result["correctness"]
    relevance = judge_result["relevance"]
    completeness = judge_result["completeness"]

    average_score = round(
        (correctness + relevance + completeness) / 3,
        2
    )

    result = {
        "id": test_case["id"],
        "question": question,
        "model": generation["model"],
        "candidate_answer": candidate_answer,
        "reference_answer": test_case["reference_answer"],
        "scores": {
            "correctness": correctness,
            "relevance": relevance,
            "completeness": completeness,
            "average": average_score
        },
        "keyword_coverage": keyword_coverage,
        "judge_reason": judge_result["reason"],
        "generation_metrics": {
            "input_tokens": generation["input_tokens"],
            "output_tokens": generation["output_tokens"],
            "total_tokens": generation["total_tokens"],
            "latency_seconds": generation["latency_seconds"]
        },
        "status": "passed" if average_score >= 3 else "needs_review"
    }

    return result


def main():

    print("=" * 60)
    print("LLM EVALUATION STARTED")
    print("=" * 60)
    mlflow.langchain.autolog(
        log_traces=True,
        silent=False
    )
    dataset = load_dataset()

    # Reuse the existing application model for generation
    llm_service = LLMService()

    # Use the same Groq model as an evaluator.
    # This makes two model calls per test case.
    judge_chain = JUDGE_PROMPT | llm_service.provider.llm

    results = []

    for test_case in dataset:

        try:
            result = evaluate_single_case(
                test_case,
                llm_service,
                judge_chain
            )

            results.append(result)

            print(
                f"Score: {result['scores']['average']}/5 "
                f"| Status: {result['status']}"
            )

        except Exception as exc:

            print(
                f"Evaluation failed for {test_case['id']}: {exc}"
            )

            results.append({
                "id": test_case["id"],
                "question": test_case["question"],
                "status": "evaluation_error",
                "error": str(exc)
            })

    # Aggregate successful evaluations
    successful = [
        item for item in results
        if "scores" in item
    ]

    total = len(results)
    evaluated = len(successful)
    failed = total - evaluated

  
    if evaluated:
        average_quality = round(
            sum(item["scores"]["average"] for item in successful)
            / evaluated,
            2
        )

        average_keyword_coverage = round(
            sum(item["keyword_coverage"] for item in successful)
            / evaluated,
            2
        )

        # Aggregate generation token usage
        total_input_tokens = sum(
            item["generation_metrics"]["input_tokens"]
            for item in successful
        )

        total_output_tokens = sum(
            item["generation_metrics"]["output_tokens"]
            for item in successful
        )

        total_tokens = sum(
            item["generation_metrics"]["total_tokens"]
            for item in successful
        )

        # Calculate average token usage per question
        average_input_tokens = round(total_input_tokens / evaluated, 2)
        average_output_tokens = round(total_output_tokens / evaluated, 2)

        # Calculate average generation latency
        average_latency = round(
            sum(
                item["generation_metrics"]["latency_seconds"]
                for item in successful
            ) / evaluated,
            3
        )
    else:
        average_quality = 0
        average_keyword_coverage = 0
        total_input_tokens = 0
        total_output_tokens = 0
        total_tokens = 0
        average_input_tokens = 0
        average_output_tokens = 0
        average_latency = 0


    report = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "model": llm_service.provider.llm.model_name,
        "summary": {
    "total_cases": total,
    "evaluated_cases": evaluated,
    "failed_cases": failed,

    "average_quality_score": average_quality,
    "average_keyword_coverage": average_keyword_coverage,

    "total_input_tokens": total_input_tokens,
    "total_output_tokens": total_output_tokens,
    "total_tokens": total_tokens,

    "average_input_tokens": average_input_tokens,
    "average_output_tokens": average_output_tokens,
    "average_latency_seconds": average_latency
},
        "results": results
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_path = RESULTS_DIR / f"evaluation_{timestamp}.json"

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=4, ensure_ascii=False)
    
# Stage 5: Log evaluation experiment to MLflow

    
    track_evaluation(
    run_name=f"groq-{PROMPT_VERSION}-{timestamp}",

    model_name=llm_service.provider.llm.model_name,

    average_quality=average_quality,
    keyword_coverage=average_keyword_coverage * 100,

    total_cases=total,
    evaluated_cases=evaluated,
    failed_cases=failed,

    report_path=str(output_path),
    dataset_version=DATASET_VERSION,

    prompt_version=PROMPT_VERSION
)



    

    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)

    print(f"Total cases: {total}")
    print(f"Evaluated: {evaluated}")
    print(f"Failed: {failed}")
    print(f"Average quality: {average_quality}/5")
    print(f"Keyword coverage: {average_keyword_coverage * 100}%")

    print(f"\nReport saved: {output_path}")


if __name__ == "__main__":
    main()
