import app.core.observability as observability


def test_record_llm_request_persists_all_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(
        observability,
        "DB_PATH",
        tmp_path / "observability.db"
    )

    observability.initialize_observability_db()
    observability.migrate_cost_columns()

    observability.record_llm_request(
        provider="Groq",
        model="openai/gpt-oss-120b",
        status="success",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        latency_seconds=0.25,
        question_length=3,
        answer_length=8,
        input_cost=0.01,
        output_cost=0.02,
        total_cost=0.03
    )

    requests = observability.get_recent_requests()

    assert len(requests) == 1
    assert requests[0]["total_tokens"] == 15
    assert requests[0]["total_cost"] == 0.03
