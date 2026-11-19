
from dashboard.alert_config import ALERT_THRESHOLDS


def evaluate_alerts(metrics, costs, thresholds=None):

    thresholds = thresholds or ALERT_THRESHOLDS
    alerts = []

    total_requests = metrics.get("total_requests") or 0
    failed_requests = metrics.get("failed_requests") or 0

    p95_latency = metrics.get("p95_latency") or 0
    output_tokens = metrics.get("total_output_tokens") or 0

    total_cost = costs.get("total_cost") or 0

    # 1. Latency alert
    if (
        total_requests > 0
        and p95_latency > thresholds["max_p95_latency"]
    ):
        alerts.append({
            "severity": "WARNING",
            "category": "Performance",
            "message": (
                f"P95 latency is {p95_latency:.2f}s. "
                f"Threshold: {thresholds['max_p95_latency']}s"
            )
        })

    # 2. Failure rate alert
    failure_rate = (
        failed_requests / total_requests * 100
        if total_requests > 0 else 0
    )

    if (
        total_requests > 0
        and failure_rate > thresholds["max_failure_rate"]
    ):
        alerts.append({
            "severity": "CRITICAL",
            "category": "Reliability",
            "message": (
                f"Failure rate is {failure_rate:.2f}%. "
                f"Threshold: {thresholds['max_failure_rate']}%"
            )
        })

    # 3. Output token alert
    if output_tokens > thresholds["max_output_tokens"]:
        alerts.append({
            "severity": "WARNING",
            "category": "Output Tokens",
            "message": (
                f"Output tokens reached {output_tokens}. "
                f"Threshold: {thresholds['max_output_tokens']}"
            )
        })

    # 4. Cost alert
    if total_cost > thresholds["max_total_cost"]:
        alerts.append({
            "severity": "CRITICAL",
            "category": "Cost",
            "message": (
                f"Total cost is ${total_cost:.4f}. "
                f"Threshold: ${thresholds['max_total_cost']}"
            )
        })

    return alerts
