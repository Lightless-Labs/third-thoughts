#!/usr/bin/env python3
"""ena_analysis — Batch 3 Python technique for middens."""
import json
import math
import re
import sys
from collections import Counter

import numpy as np

NAME = "ena_analysis"
MIN_SESSIONS = 5
MIN_MESSAGES_PER_SESSION = 3
WINDOW_SIZE = 5

CODES = [
    "PROBLEM_FRAMING",
    "HYPOTHESIS",
    "EVIDENCE_SEEK",
    "TOOL_USE",
    "SELF_CORRECT",
    "PLAN",
    "RESULT_INTERP",
]
CODE_INDEX = {code: index for index, code in enumerate(CODES)}
KEYWORDS = {
    "PROBLEM_FRAMING": [
        "problem",
        "issue",
        "error",
        "bug",
        "fail",
        "failed",
        "broken",
        "unexpected",
    ],
    "HYPOTHESIS": [
        "maybe",
        "perhaps",
        "might",
        "could be",
        "suspect",
        "likely",
        "i think",
        "i believe",
    ],
    "EVIDENCE_SEEK": ["read", "check", "look", "inspect", "verify", "confirm", "examine"],
    "SELF_CORRECT": ["wait", "actually", "sorry", "mistake", "revert", "undo", "let me"],
    "PLAN": ["plan", "step", "first", "next", "then", "finally", "approach", "strategy"],
    "RESULT_INTERP": ["found", "shows", "indicates", "means", "suggests", "confirms", "because"],
}
PATTERNS = {
    code: [re.compile(r"\b" + re.escape(keyword) + r"\b", re.IGNORECASE) for keyword in keywords]
    for code, keywords in KEYWORDS.items()
}


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


def message_blob(message):
    parts = []
    for field in ("text", "thinking"):
        value = message.get(field)
        if value:
            parts.append(str(value))
    return " ".join(parts)



def code_turn(message):
    codes = set()
    blob = message_blob(message)

    for code, patterns in PATTERNS.items():
        if any(pattern.search(blob) for pattern in patterns):
            codes.add(code)

    if message.get("tool_calls", []) or []:
        codes.add("TOOL_USE")

    return codes



def correction_rate(messages):
    user_total = 0
    correction_total = 0
    for message in messages:
        if message.get("role") != "User":
            continue
        user_total += 1
        if message.get("classification") == "HumanCorrection":
            correction_total += 1
    if user_total == 0:
        return 0.0
    return correction_total / user_total



def session_matrix(turns):
    matrix = np.zeros((len(CODES), len(CODES)), dtype=float)
    for turn_index in range(len(turns)):
        start = max(0, turn_index - (WINDOW_SIZE - 1))
        union_codes = set()
        for _, code_set in turns[start : turn_index + 1]:
            union_codes.update(code_set)

        indices = sorted(CODE_INDEX[code] for code in union_codes)
        for left in range(len(indices)):
            for right in range(left + 1, len(indices)):
                code_a = indices[left]
                code_b = indices[right]
                matrix[code_a, code_b] += 1.0
                matrix[code_b, code_a] += 1.0

    matrix /= float(len(turns))
    return matrix



def analyze_session(session):
    messages = session.get("messages", []) or []
    turns = []
    frequencies = Counter()

    for message_index, message in enumerate(messages):
        if message.get("role") == "System":
            continue
        codes = code_turn(message)
        turns.append((message_index, codes))
        frequencies.update(codes)

    if len(turns) < MIN_MESSAGES_PER_SESSION:
        return None

    return {
        "id": session.get("id"),
        "turns": turns,
        "frequencies": frequencies,
        "correction_rate": correction_rate(messages),
        "matrix": session_matrix(turns),
    }



def mean_matrix(session_entries):
    if not session_entries:
        return np.zeros((len(CODES), len(CODES)), dtype=float)
    return np.mean(np.stack([entry["matrix"] for entry in session_entries]), axis=0)



def strongest_edge(matrix):
    best_pair = None
    best_weight = None

    for left in range(len(CODES)):
        for right in range(left + 1, len(CODES)):
            weight = float(matrix[left, right])
            pair = tuple(sorted((CODES[left], CODES[right])))
            if best_pair is None or weight > best_weight or (weight == best_weight and pair < best_pair):
                best_pair = pair
                best_weight = weight

    if best_pair is None or best_weight is None or best_weight <= 0.0:
        return "none"

    return f"{best_pair[0]}↔{best_pair[1]}"



def discriminative_rows(low_matrix, high_matrix):
    rows = []
    for left in range(len(CODES)):
        for right in range(left + 1, len(CODES)):
            low_weight = float(low_matrix[left, right])
            high_weight = float(high_matrix[left, right])
            difference = abs(low_weight - high_weight)
            if difference <= 0.0:
                continue
            code_a, code_b = sorted((CODES[left], CODES[right]))
            rows.append((code_a, code_b, low_weight, high_weight, difference))

    rows.sort(key=lambda row: (-row[4], row[0], row[1]))
    return [
        [code_a, code_b, round4(low_weight), round4(high_weight), round4(difference)]
        for code_a, code_b, low_weight, high_weight, difference in rows[:10]
    ]



def analyze(sessions):
    surviving_sessions = []
    for session in sessions:
        analyzed = analyze_session(session)
        if analyzed is not None:
            surviving_sessions.append(analyzed)

    if len(surviving_sessions) < MIN_SESSIONS:
        return empty_result(
            "insufficient data: need at least 5 sessions with at least 3 non-system messages, "
            f"got {len(surviving_sessions)}"
        )

    overall_matrix = mean_matrix(surviving_sessions)
    frequency_counter = Counter()
    for entry in surviving_sessions:
        frequency_counter.update(entry["frequencies"])

    observed_codes = [code for code in CODES if frequency_counter[code] > 0]
    total_matrix_weight = float(np.sum(overall_matrix))
    centrality = {}
    for code in observed_codes:
        index = CODE_INDEX[code]
        if total_matrix_weight > 0.0:
            centrality[code] = float(np.sum(overall_matrix[index, :])) / total_matrix_weight
        else:
            centrality[code] = 0.0

    if observed_codes:
        ranked_codes = sorted(observed_codes, key=lambda code: (-centrality[code], code))
        top_code = ranked_codes[0]
        top_code_centrality = round4(centrality[top_code])
    else:
        ranked_codes = []
        top_code = "none"
        top_code_centrality = 0.0

    low_correction_sessions = [
        entry for entry in surviving_sessions if entry["correction_rate"] <= 0.10
    ]
    high_correction_sessions = [
        entry for entry in surviving_sessions if entry["correction_rate"] > 0.25
    ]

    strongest_low_edge = "none"
    strongest_high_edge = "none"
    discriminative_edge_rows = []
    if low_correction_sessions and high_correction_sessions:
        low_matrix = mean_matrix(low_correction_sessions)
        high_matrix = mean_matrix(high_correction_sessions)
        strongest_low_edge = strongest_edge(low_matrix)
        strongest_high_edge = strongest_edge(high_matrix)
        discriminative_edge_rows = discriminative_rows(low_matrix, high_matrix)

    code_centrality_rows = []
    for code in ranked_codes:
        code_centrality_rows.append(
            [code, round4(centrality[code]), frequency_counter[code]]
        )

    findings = [
        {"label": "sessions_analyzed", "value": len(surviving_sessions)},
        {"label": "top_code", "value": top_code},
        {"label": "top_code_centrality", "value": top_code_centrality},
        {"label": "strongest_low_correction_edge", "value": strongest_low_edge},
        {"label": "strongest_high_correction_edge", "value": strongest_high_edge},
    ]

    if top_code == "none":
        summary = (
            f"Epistemic network analysis (ENA) of {len(surviving_sessions)} sessions found no coded "
            "epistemic activity, so centrality and co-occurrence remained zero across the surviving sessions."
        )
        if low_correction_sessions and high_correction_sessions:
            summary += " Discriminative co-occurrence analysis found no non-zero group differences."
        else:
            summary += (
                " Discriminative co-occurrence analysis was unavailable because low- and "
                "high-correction groups were not both present."
            )
    else:
        summary = (
            f"Epistemic network analysis (ENA) of {len(surviving_sessions)} sessions identified "
            f"{top_code} as the most central code (centrality={top_code_centrality})."
        )
        if strongest_low_edge != "none" and strongest_high_edge != "none":
            summary += (
                f" Co-occurrence analysis found {strongest_low_edge} dominant in low-correction "
                f"sessions and {strongest_high_edge} dominant in high-correction sessions."
            )
        elif low_correction_sessions and high_correction_sessions:
            summary += " Co-occurrence analysis found no non-zero discriminative edges between the groups."
        else:
            summary += (
                " Discriminative co-occurrence analysis was unavailable because low- and "
                "high-correction groups were not both present."
            )

    return {
        "name": NAME,
        "summary": summary,
        "findings": findings,
        "tables": [
            {
                "name": "Code Centrality",
                "columns": ["code", "centrality", "frequency"],
                "rows": code_centrality_rows,
            },
            {
                "name": "Discriminative Edges",
                "columns": [
                    "code_a",
                    "code_b",
                    "low_correction_weight",
                    "high_correction_weight",
                    "difference",
                ],
                "rows": discriminative_edge_rows,
            },
        ],
        "figures": [],
    }



def main():
    if len(sys.argv) < 2:
        print("usage: ena_analysis.py <sessions.json>", file=sys.stderr)
        sys.exit(1)
    try:
        with open(sys.argv[1]) as handle:
            sessions = json.load(handle)
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
