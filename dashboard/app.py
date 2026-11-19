
import os

import requests
import pandas as pd
import plotly.express as px
import streamlit as st

from dashboard.alert_service import evaluate_alerts


# ==================================================
# 1. PAGE CONFIGURATION
# ==================================================

st.set_page_config(
    page_title="LLMOps Monitoring",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

import os

API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000/api/v1"
)

CURRENCY = "USD"


# ==================================================
# 2. API CLIENT
# ==================================================

@st.cache_data(ttl=10)
def fetch_api_data(endpoint, params=None):

    url = f"{API_BASE_URL}{endpoint}"

    response = requests.get(
        url,
        params=params,
        timeout=10
    )

    response.raise_for_status()

    return response.json()


def load_dashboard_data(days):

    metrics = fetch_api_data(
        "/monitoring/metrics"
    )

    costs = fetch_api_data(
        "/monitoring/costs"
    )

    trends = fetch_api_data(
        "/monitoring/trends",
        params={"days": days}
    )

    recent = fetch_api_data(
        "/monitoring/recent",
        params={"limit": 100}
    )

    return metrics, costs, trends, recent


# ==================================================
# 3. SIDEBAR
# ==================================================

st.sidebar.title("LLMOps Monitor")

st.sidebar.caption(
    "Groq + LangChain + FastAPI"
)

days = st.sidebar.selectbox(
    "Analytics period",
    options=[7, 14, 30, 90],
    index=0,
    format_func=lambda x: f"Last {x} days"
)

if st.sidebar.button(
    "Refresh dashboard",
    use_container_width=True
):

    st.cache_data.clear()
    st.rerun()


st.sidebar.divider()

st.sidebar.subheader("Backend Configuration")

st.sidebar.code(API_BASE_URL)

st.sidebar.caption(
    "Data source: FastAPI monitoring APIs"
)


# ==================================================
# 4. ALERT CONFIGURATION
# ==================================================

st.sidebar.divider()

st.sidebar.subheader("Alert Thresholds")

max_latency = st.sidebar.number_input(
    "Maximum P95 latency (seconds)",
    min_value=0.1,
    value=5.0,
    step=0.5
)

max_failure_rate = st.sidebar.number_input(
    "Maximum failure rate (%)",
    min_value=0.0,
    max_value=100.0,
    value=10.0,
    step=1.0
)

max_tokens = st.sidebar.number_input(
    "Maximum total tokens",
    min_value=1,
    value=100000,
    step=10000
)

max_cost = st.sidebar.number_input(
    "Maximum estimated cost (USD)",
    min_value=0.01,
    value=1.0,
    step=0.5
)


# ==================================================
# 5. HEADER
# ==================================================

st.title("LLMOps Monitoring Dashboard")

st.markdown(
    """
    Monitor your LLM application in real time.

    Track request volume, token consumption, latency,
    estimated costs, model performance and failures.
    """
)

st.divider()


# ==================================================
# 6. FETCH DASHBOARD DATA
# ==================================================

try:

    metrics, costs, trends, recent = load_dashboard_data(days)

except requests.exceptions.ConnectionError:

    st.error(
        "Cannot connect to FastAPI. "
        "Please start your backend server."
    )

    st.code(
        "uvicorn app.main:app --reload"
    )

    st.stop()


except requests.exceptions.Timeout:

    st.error(
        "The monitoring API request timed out. "
        "Check whether your backend is responding."
    )

    st.stop()


except requests.exceptions.HTTPError as exc:

    st.error(
        f"Monitoring API returned an HTTP error: {exc}"
    )

    st.stop()


except requests.exceptions.RequestException as exc:

    st.error(
        f"Monitoring API error: {exc}"
    )

    st.stop()


except (ValueError, TypeError) as exc:

    st.error(
        f"Invalid monitoring API response: {exc}"
    )

    st.stop()


# Validate response types.

if not all(
    isinstance(data, dict)
    for data in [metrics, costs]
):

    st.error(
        "Metrics or cost API returned an invalid response."
    )

    st.stop()


if not isinstance(trends, list):

    st.error(
        "Trend API must return a list of records."
    )

    st.stop()


if not isinstance(recent, list):

    st.error(
        "Recent requests API must return a list."
    )

    st.stop()


# ==================================================
# 7. METRIC CALCULATIONS
# ==================================================

total_requests = metrics.get("total_requests") or 0

successful = metrics.get("successful_requests") or 0

failed = metrics.get("failed_requests") or 0

success_rate = metrics.get("success_rate_percent") or 0

total_tokens = metrics.get("total_tokens") or 0

input_tokens = metrics.get("total_input_tokens") or 0

output_tokens = metrics.get("total_output_tokens") or 0

average_latency = metrics.get("average_latency") or 0

p95_latency = metrics.get("p95_latency") or 0

maximum_latency = metrics.get("maximum_latency") or 0

total_cost = costs.get("total_cost") or 0

average_cost = costs.get("average_cost_per_request") or 0


# ==================================================
# 8. ALERT EVALUATION
# ==================================================

custom_thresholds = {
    "max_p95_latency": 5.0,
    "max_failure_rate": 10.0,
    "max_output_tokens": 10000,
    "max_total_cost": 1.0
}

alerts = evaluate_alerts(
    metrics=metrics,
    costs=costs,
    thresholds=custom_thresholds
)


# ==================================================
# 9. SYSTEM ALERTS
# ==================================================

st.subheader("System Alerts")

if alerts:

    critical_count = sum(
        1 for alert in alerts
        if alert["severity"] == "CRITICAL"
    )

    warning_count = sum(
        1 for alert in alerts
        if alert["severity"] == "WARNING"
    )

    col1, col2 = st.columns(2)

    col1.metric(
        "Critical Alerts",
        critical_count
    )

    col2.metric(
        "Warnings",
        warning_count
    )

    for alert in alerts:

        message = (
            f"**{alert['category']}** — "
            f"{alert['message']}"
        )

        if alert["severity"] == "CRITICAL":

            st.error(message)

        else:

            st.warning(message)

else:

    st.success(
        "All monitoring thresholds are within limits."
    )

st.caption(
    "Alerts use cumulative monitoring metrics and costs, "
    "not only the selected chart period."
)

st.divider()


# ==================================================
# 10. REQUEST OVERVIEW
# ==================================================

st.subheader("Request Overview")

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Total Requests",
    f"{total_requests:,}"
)

col2.metric(
    "Successful Requests",
    f"{successful:,}"
)

col3.metric(
    "Failed Requests",
    f"{failed:,}"
)

col4.metric(
    "Success Rate",
    f"{success_rate:.2f}%"
)


# ==================================================
# 11. TOKEN AND COST ANALYTICS
# ==================================================

st.divider()

st.subheader("Token & Cost Analytics")

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Total Tokens",
    f"{total_tokens:,}"
)

col2.metric(
    "Input Tokens",
    f"{input_tokens:,}"
)

col3.metric(
    "Output Tokens",
    f"{output_tokens:,}"
)

col4.metric(
    "Estimated Total Cost",
    f"{CURRENCY} {total_cost:.6f}"
)

st.caption(
    f"Average estimated cost per successful request: "
    f"{CURRENCY} {average_cost:.8f}"
)


# ==================================================
# 12. PERFORMANCE ANALYTICS
# ==================================================

st.divider()

st.subheader("Performance Analytics")

col1, col2, col3 = st.columns(3)

col1.metric(
    "Average Latency",
    f"{average_latency:.3f} sec"
)

col2.metric(
    "P95 Latency",
    f"{p95_latency:.3f} sec"
)

col3.metric(
    "Maximum Latency",
    f"{maximum_latency:.3f} sec"
)


# ==================================================
# 13. REQUEST TRENDS
# ==================================================

st.divider()

st.subheader(
    f"Request Trends — Last {days} Days"
)

if trends:

    trends_df = pd.DataFrame(trends)

    required_columns = [
        "date",
        "successful_requests",
        "failed_requests",
        "total_tokens",
        "total_cost",
        "average_latency"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in trends_df.columns
    ]

    if missing_columns:

        st.warning(
            f"Trend data is missing columns: {missing_columns}"
        )

    else:

        trends_df["date"] = pd.to_datetime(
            trends_df["date"],
            errors="coerce"
        )

        trends_df = trends_df.dropna(
            subset=["date"]
        )

        if not trends_df.empty:

            col1, col2 = st.columns(2)

            with col1:

                fig = px.line(
                    trends_df,
                    x="date",
                    y=[
                        "successful_requests",
                        "failed_requests"
                    ],
                    markers=True,
                    title="Successful vs Failed Requests",
                    labels={
                        "date": "Date",
                        "value": "Requests",
                        "variable": "Status"
                    }
                )

                st.plotly_chart(
                    fig,
                    use_container_width=True
                )

            with col2:

                fig = px.area(
                    trends_df,
                    x="date",
                    y="total_tokens",
                    title="Daily Token Consumption",
                    labels={
                        "date": "Date",
                        "total_tokens": "Tokens"
                    }
                )

                st.plotly_chart(
                    fig,
                    use_container_width=True
                )

            col1, col2 = st.columns(2)

            with col1:

                fig = px.bar(
                    trends_df,
                    x="date",
                    y="total_cost",
                    title="Daily Estimated Cost",
                    labels={
                        "date": "Date",
                        "total_cost": f"Cost ({CURRENCY})"
                    }
                )

                st.plotly_chart(
                    fig,
                    use_container_width=True
                )

            with col2:

                fig = px.line(
                    trends_df,
                    x="date",
                    y="average_latency",
                    markers=True,
                    title="Daily Average Latency",
                    labels={
                        "date": "Date",
                        "average_latency": "Seconds"
                    }
                )

                st.plotly_chart(
                    fig,
                    use_container_width=True
                )

        else:

            st.info(
                "No valid trend records available."
            )

else:

    st.info(
        "No trend data available for this period. "
        "Generate some LLM requests to populate the charts."
    )


# ==================================================
# 14. MODEL PERFORMANCE
# ==================================================

st.divider()

st.subheader("Model Performance")

models = metrics.get("models", [])

if models:

    model_df = pd.DataFrame(models)

    st.dataframe(
        model_df,
        use_container_width=True,
        hide_index=True
    )

else:

    st.info(
        "No model usage data available."
    )


# ==================================================
# 15. RECENT REQUESTS
# ==================================================

st.divider()

st.subheader("Recent LLM Requests")

if recent:

    recent_df = pd.DataFrame(recent)

    display_columns = [
        "request_id",
        "timestamp",
        "provider",
        "model",
        "status",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "latency_seconds",
        "total_cost"
    ]

    available_columns = [
        column
        for column in display_columns
        if column in recent_df.columns
    ]

    st.dataframe(
        recent_df[available_columns],
        use_container_width=True,
        hide_index=True
    )

    # Failed request analysis.

    if "status" in recent_df.columns:

        failures_df = recent_df[
            recent_df["status"] == "failed"
        ]

        if not failures_df.empty:

            st.error(
                f"{len(failures_df)} failed requests "
                "found in recent records."
            )

            failure_columns = [
                column
                for column in [
                    "request_id",
                    "timestamp",
                    "model",
                    "error_type"
                ]
                if column in failures_df.columns
            ]

            st.dataframe(
                failures_df[failure_columns],
                use_container_width=True,
                hide_index=True
            )

else:

    st.info(
        "No request records available."
    )



# ==================================================
# NOTIFICATION HISTORY
# ==================================================

st.divider()

st.subheader("Notification History")

try:

    notification_history = fetch_api_data(
        "/monitoring/notifications",
        params={"limit": 100}
    )

    if notification_history:

        notification_df = pd.DataFrame(
            notification_history
        )

        # Notification status overview

        total_notifications = len(notification_df)

        sent_count = (
            notification_df["status"] == "sent"
        ).sum()

        pending_count = (
            notification_df["status"] == "pending"
        ).sum()

        failed_count = (
            notification_df["status"] == "failed"
        ).sum()

        col1, col2, col3, col4 = st.columns(4)

        col1.metric(
            "Total Notifications",
            total_notifications
        )

        col2.metric(
            "Sent",
            int(sent_count)
        )

        col3.metric(
            "Pending",
            int(pending_count)
        )

        col4.metric(
            "Failed",
            int(failed_count)
        )

        st.divider()

        # Channel statistics

        if "channel" in notification_df.columns:

            st.subheader("Channel Distribution")

            channel_df = (
                notification_df["channel"]
                .value_counts()
                .reset_index()
            )

            channel_df.columns = [
                "channel",
                "notifications"
            ]

            fig = px.pie(
                channel_df,
                names="channel",
                values="notifications",
                hole=0.45,
                title="Notifications by Channel"
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

        # Notification history table

        st.subheader("Delivery Records")

        display_columns = [
            "id",
            "created_at",
            "channel",
            "severity",
            "category",
            "status",
            "attempts",
            "max_attempts",
            "sent_at",
            "next_retry_at",
            "last_error"
        ]

        available_columns = [
            column
            for column in display_columns
            if column in notification_df.columns
        ]

        st.dataframe(
            notification_df[available_columns],
            use_container_width=True,
            hide_index=True
        )

        # Failed notifications

        failed_notifications = notification_df[
            notification_df["status"] == "failed"
        ]

        if not failed_notifications.empty:

            st.error(
                f"{len(failed_notifications)} "
                "notification(s) permanently failed."
            )

            st.dataframe(
                failed_notifications[
                    [
                        column
                        for column in [
                            "id",
                            "channel",
                            "category",
                            "attempts",
                            "last_error"
                        ]
                        if column in failed_notifications.columns
                    ]
                ],
                use_container_width=True,
                hide_index=True
            )

    else:

        st.info(
            "No notification history available yet."
        )

except requests.exceptions.RequestException as exc:

    st.warning(
        f"Could not load notification history: {exc}"
    )


# ==================================================
# 16. FOOTER
# ==================================================

st.divider()

st.caption(
    "LLMOps Monitoring | Powered by Streamlit, "
    "FastAPI, SQLite, LangChain and Groq"
)
