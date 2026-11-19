
from dashboard.alert_service import evaluate_alerts


def get_metrics(
    total_requests=100,
    failed_requests=0,
    p95_latency=2.0,
    total_tokens=5000
):
    return {
        "total_requests": total_requests,
        "failed_requests": failed_requests,
        "p95_latency": p95_latency,
        "total_tokens": total_tokens
    }


def get_costs(total_cost=0.2):
    return {
        "total_cost": total_cost
    }


THRESHOLDS = {
    "max_p95_latency": 5.0,
    "max_failure_rate": 10.0,
    "max_total_tokens": 100000,
    "max_total_cost": 1.0
}


def test_high_latency_alert():

    alerts = evaluate_alerts(
        get_metrics(p95_latency=8.5),
        get_costs(),
        THRESHOLDS
    )

    assert any(
        alert["category"] == "Performance"
        and alert["severity"] == "WARNING"
        for alert in alerts
    )


def test_high_failure_rate_alert():

    alerts = evaluate_alerts(
        get_metrics(
            total_requests=100,
            failed_requests=25
        ),
        get_costs(),
        THRESHOLDS
    )

    assert any(
        alert["category"] == "Reliability"
        and alert["severity"] == "CRITICAL"
        for alert in alerts
    )


def test_high_token_usage_alert():

    alerts = evaluate_alerts(
        get_metrics(total_tokens=150000),
        get_costs(),
        THRESHOLDS
    )

    assert any(
        alert["category"] == "Token Usage"
        for alert in alerts
    )


def test_high_cost_alert():

    alerts = evaluate_alerts(
        get_metrics(),
        get_costs(total_cost=2.5),
        THRESHOLDS
    )

    assert any(
        alert["category"] == "Cost"
        and alert["severity"] == "CRITICAL"
        for alert in alerts
    )


def test_no_alerts_within_thresholds():

    alerts = evaluate_alerts(
        get_metrics(),
        get_costs(),
        THRESHOLDS
    )

    assert alerts == []


def test_zero_requests_does_not_trigger_failure_alert():

    alerts = evaluate_alerts(
        get_metrics(
            total_requests=0,
            failed_requests=0
        ),
        get_costs(),
        THRESHOLDS
    )

    assert not any(
        alert["category"] == "Reliability"
        for alert in alerts
    )


if __name__ == "__main__":

    tests = [
        test_high_latency_alert,
        test_high_failure_rate_alert,
        test_high_token_usage_alert,
        test_high_cost_alert,
        test_no_alerts_within_thresholds,
        test_zero_requests_does_not_trigger_failure_alert
    ]

    for test in tests:

        test()

        print(f"PASSED: {test.__name__}")

    print("\nAll alert service tests passed!")
