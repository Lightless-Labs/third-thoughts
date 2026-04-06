#!/usr/bin/env python3
"""spc_control_charts — Batch 3 Python technique for middens."""
import json
import math
import sys
from datetime import datetime, timezone

import numpy as np

NAME = "spc_control_charts"
MIN_SESSIONS = 10
MIN_MESSAGES_PER_SESSION = 20


def sanitize(obj):
    """Recursively replace NaN/Infinity with None for JSON safety."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return obj


def empty_result(summary):
    return {
        "name": NAME,
        "summary": summary,
        "findings": [],
        "tables": [],
        "figures": [],
    }


def round4(value):
    if value is None:
        return None
    return round(float(value), 4)


def parse_iso_timestamp(timestamp):
    if not timestamp or not isinstance(timestamp, str):
        return None
    try:
        normalized = timestamp.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed


def first_session_timestamp(session):
    for message in session.get("messages", []) or []:
        timestamp = message.get("timestamp")
        if timestamp:
            return timestamp
    return None


def sort_key_for_entry(item):
    position, entry = item
    parsed = parse_iso_timestamp(entry["timestamp"])
    if parsed is None:
        return (1, "", position)
    return (0, parsed.isoformat(), position)


def mean(values):
    if not values:
        return 0.0
    return float(np.mean(np.asarray(values, dtype=float)))


def moving_ranges(values):
    return [abs(values[index] - values[index - 1]) for index in range(1, len(values))]


def compute_control_limits(values):
    center = mean(values)
    mr_values = moving_ranges(values)
    mr_bar = mean(mr_values)
    ucl_i = center + 2.66 * mr_bar
    lcl_i = max(0.0, center - 2.66 * mr_bar)
    ucl_mr = 3.267 * mr_bar
    sigma_est = mr_bar / 1.128 if mr_bar > 0 else 0.0
    return {
        "center": center,
        "mr_bar": mr_bar,
        "ucl_i": ucl_i,
        "lcl_i": lcl_i,
        "ucl_mr": ucl_mr,
        "sigma_est": sigma_est,
    }


def compute_session_metrics(session):
    messages = session.get("messages", []) or []

    user_messages = [message for message in messages if message.get("role") == "User"]
    user_total = len(user_messages)
    correction_count = sum(
        1 for message in user_messages if message.get("classification") == "HumanCorrection"
    )
    correction_rate = correction_count / user_total if user_total else 0.0

    tool_results = []
    for message in messages:
        tool_results.extend(message.get("tool_results", []) or [])
    tool_total = len(tool_results)
    tool_error_count = sum(1 for result in tool_results if result.get("is_error") is True)
    tool_error_rate = tool_error_count / tool_total if tool_total else 0.0

    assistant_messages = [message for message in messages if message.get("role") == "Assistant"]
    assistant_lengths = [len(message.get("text") or "") for message in assistant_messages]
    mean_assistant_text_len = mean(assistant_lengths)

    return {
        "correction_rate": correction_rate,
        "tool_error_rate": tool_error_rate,
        "assistant_text_len": mean_assistant_text_len,
    }


def analyze(sessions):
    surviving_sessions = []
    for session in sessions:
        messages = session.get("messages", []) or []
        if len(messages) < MIN_MESSAGES_PER_SESSION:
            continue
        surviving_sessions.append(
            {
                "session": session,
                "timestamp": first_session_timestamp(session),
                "metrics": compute_session_metrics(session),
            }
        )

    if len(surviving_sessions) < MIN_SESSIONS:
        return empty_result(
            "insufficient data: need at least 10 sessions with at least 20 messages, "
            f"got {len(surviving_sessions)}"
        )

    sorted_sessions = [
        entry for _, entry in sorted(enumerate(surviving_sessions), key=sort_key_for_entry)
    ]

    metric_order = [
        ("correction_rate", "correction_rate"),
        ("tool_error_rate", "tool_error_rate"),
        ("assistant_text_len", "assistant_text_len"),
    ]

    metric_series = {}
    metric_limits = {}
    for metric_key, _ in metric_order:
        values = [entry["metrics"][metric_key] for entry in sorted_sessions]
        metric_series[metric_key] = values
        metric_limits[metric_key] = compute_control_limits(values)

    out_of_control_rows = []
    ooc_counts = {metric_key: 0 for metric_key, _ in metric_order}
    for entry in sorted_sessions:
        session_id = entry["session"].get("id")
        for metric_key, metric_label in metric_order:
            value = entry["metrics"][metric_key]
            limits = metric_limits[metric_key]
            if value > limits["ucl_i"]:
                ooc_counts[metric_key] += 1
                out_of_control_rows.append([session_id, metric_label, round4(value), "UCL"])
            elif value < limits["lcl_i"]:
                ooc_counts[metric_key] += 1
                out_of_control_rows.append([session_id, metric_label, round4(value), "LCL"])

    correction_limits = metric_limits["correction_rate"]
    sigma_est = correction_limits["sigma_est"]
    center = correction_limits["center"]
    ucl_2sigma = center + 2 * sigma_est
    lcl_2sigma = center - 2 * sigma_est

    rule2_indices = []
    correction_values = metric_series["correction_rate"]
    for start in range(0, len(correction_values) - 2):
        window = correction_values[start : start + 3]
        above_count = sum(1 for value in window if value > ucl_2sigma)
        below_count = sum(1 for value in window if value < lcl_2sigma)
        if above_count >= 2 or below_count >= 2:
            rule2_indices.append(start + 1)

    k = 0.5 * sigma_est
    h = 4 * sigma_est
    cusum_high = 0.0
    cusum_low = 0.0
    cusum_series = []
    cusum_first_alarm_index = None
    for session_index, value in enumerate(correction_values):
        cusum_high = max(0.0, cusum_high + (value - center - k))
        cusum_low = max(0.0, cusum_low + (center - k - value))
        cusum_value = cusum_high - cusum_low
        cusum_series.append([session_index, round4(cusum_value)])
        if cusum_first_alarm_index is None and (cusum_high > h or cusum_low > h):
            cusum_first_alarm_index = session_index

    findings = [
        {
            "label": "sessions_analyzed",
            "value": len(sorted_sessions),
            "description": "Sessions with at least 20 messages included in the control chart.",
        },
        {
            "label": "correction_rate_mean",
            "value": round4(correction_limits["center"]),
            "description": "Mean correction rate across analyzed sessions.",
        },
        {
            "label": "correction_rate_ucl",
            "value": round4(correction_limits["ucl_i"]),
            "description": "Individuals-chart upper control limit for correction rate.",
        },
        {
            "label": "correction_rate_ooc_count",
            "value": ooc_counts["correction_rate"],
            "description": "Correction-rate sessions beyond control limits.",
        },
        {
            "label": "tool_error_rate_ooc_count",
            "value": ooc_counts["tool_error_rate"],
            "description": "Tool-error-rate sessions beyond control limits.",
        },
        {
            "label": "assistant_len_ooc_count",
            "value": ooc_counts["assistant_text_len"],
            "description": "Assistant-text-length sessions beyond control limits.",
        },
        {
            "label": "cusum_first_alarm_index",
            "value": cusum_first_alarm_index,
            "description": "First session index where the correction-rate CUSUM crossed its threshold.",
        },
        {
            "label": "rule2_violations",
            "value": len(rule2_indices),
            "description": "Western Electric rule 2 violations on correction rate.",
        },
    ]

    control_limits_rows = []
    for metric_key, metric_label in metric_order:
        limits = metric_limits[metric_key]
        control_limits_rows.append(
            [
                metric_label,
                round4(limits["center"]),
                round4(limits["ucl_i"]),
                round4(limits["lcl_i"]),
                round4(limits["mr_bar"]),
            ]
        )

    rule_violation_rows = [["rule2", "correction_rate", index] for index in rule2_indices]

    correction_series_rows = []
    tool_error_series_rows = []
    assistant_len_series_rows = []
    for session_index, entry in enumerate(sorted_sessions):
        session = entry["session"]
        session_id = session.get("id")
        timestamp = entry["timestamp"]
        correction_series_rows.append(
            [session_index, session_id, timestamp, round4(entry["metrics"]["correction_rate"])]
        )
        tool_error_series_rows.append(
            [session_index, session_id, timestamp, round4(entry["metrics"]["tool_error_rate"])]
        )
        assistant_len_series_rows.append(
            [session_index, session_id, timestamp, round4(entry["metrics"]["assistant_text_len"])]
        )

    summary = (
        f"SPC control chart analysis of {len(sorted_sessions)} sessions found "
        f"{ooc_counts['correction_rate']} out-of-control points on correction_rate "
        f"(UCL={round4(correction_limits['ucl_i'])}), "
        f"{ooc_counts['tool_error_rate']} on tool_error_rate, and "
        f"{ooc_counts['assistant_text_len']} on assistant_text_len. "
        f"{len(rule2_indices)} Western Electric rule-2 violation"
        f"{'s' if len(rule2_indices) != 1 else ''}; "
        f"CUSUM alarm at session index "
        f"{cusum_first_alarm_index if cusum_first_alarm_index is not None else 'none'}."
    )

    return {
        "name": NAME,
        "summary": summary,
        "findings": findings,
        "tables": [
            {
                "name": "Control Limits",
                "columns": ["metric", "mean", "ucl", "lcl", "mr_bar"],
                "rows": control_limits_rows,
            },
            {
                "name": "Out-of-Control Sessions",
                "columns": ["session_id", "metric", "value", "limit_violated"],
                "rows": out_of_control_rows[:20],
            },
            {
                "name": "Rule Violations",
                "columns": ["rule", "metric", "session_index"],
                "rows": rule_violation_rows,
            },
            {
                "name": "Correction Rate Series",
                "columns": ["session_index", "session_id", "timestamp", "value"],
                "rows": correction_series_rows,
            },
            {
                "name": "Tool Error Rate Series",
                "columns": ["session_index", "session_id", "timestamp", "value"],
                "rows": tool_error_series_rows,
            },
            {
                "name": "Assistant Text Length Series",
                "columns": ["session_index", "session_id", "timestamp", "value"],
                "rows": assistant_len_series_rows,
            },
            {
                "name": "CUSUM Series",
                "columns": ["session_index", "cusum_value"],
                "rows": cusum_series,
            },
        ],
        "figures": [],
    }


def main():
    if len(sys.argv) < 2:
        print("usage: spc_control_charts.py <sessions.json>", file=sys.stderr)
        sys.exit(1)
    try:
        with open(sys.argv[1]) as file_handle:
            sessions = json.load(file_handle)
    except Exception as exc:
        print(f"Failed to read sessions: {exc}", file=sys.stderr)
        sys.exit(1)

    if not sessions:
        print(json.dumps(empty_result("No sessions to analyze")))
        return

    if len(sessions) < MIN_SESSIONS:
        print(
            json.dumps(
                empty_result(
                    f"insufficient data: need at least {MIN_SESSIONS} sessions, got {len(sessions)}"
                )
            )
        )
        return

    result = analyze(sessions)
    print(json.dumps(sanitize(result), default=str))


if __name__ == "__main__":
    main()
