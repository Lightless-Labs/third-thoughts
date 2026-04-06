"""convention_epidemiology — Batch 3 Python technique for middens."""
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime
import numpy as np
from scipy.optimize import curve_fit
from scipy.integrate import odeint

NAME = "convention_epidemiology"
MIN_SESSIONS = 15

def sanitize(obj):
    """Recursively replace NaN/Infinity with None for JSON safety. Handles numpy scalars/arrays."""
    if isinstance(obj, np.ndarray):
        return sanitize(obj.tolist())
    if isinstance(obj, (np.floating, np.integer)):
        obj = obj.item()
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

def get_first_ts(session):
    """Get first timestamp from session messages."""
    for msg in session.get("messages", []):
        ts = msg.get("timestamp")
        if ts:
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
    return None

# Common source-tree subdirectories that should be stripped when deriving a
# project_id, so two sessions from the same repo (e.g. /repo/src vs /repo/tests)
# hash to the same opaque project id. Lowercased for case-insensitive match.
#
# Kept deliberately NARROW: only includes names that are almost never used
# as repo names themselves. Names like `api`, `service`, `backend`, `web`,
# `frontend`, `client`, `server`, `app`, `apps` are deliberately excluded —
# they're very common as actual repository names (e.g. a repo literally
# called `api` or `web`) and stripping them would merge distinct repos into
# one canonical key, the opposite of the desired behavior.
_PROJECT_SUBDIR_BLOCKLIST = frozenset({
    "src", "lib", "pkg", "pkgs", "crates", "packages",
    "test", "tests", "spec", "specs", "__tests__",
    "docs", "doc", "documentation",
    "examples", "example", "sample", "samples", "demo", "demos",
    "scripts", "tools", "bin", "utils",
    "internal", "cmd",
    "build", "dist", "out", "target",
    "node_modules", "vendor",
})


def get_project_id(session):
    """Derive an opaque project_id from cwd.

    The raw normalized path may contain sensitive directory or repo names
    (e.g., "workspace/secret-project"). We hash a normalized canonical form
    so downstream tables never leak filesystem or business context.

    Canonicalization walks up the cwd from the tail, stripping known
    source-tree subdirectories (src/, tests/, docs/, etc.) so that sessions
    run from different subfolders of the same repo hash identically. This
    prevents `/workspace/repo/src` and `/workspace/repo/tests` from being
    counted as two distinct projects, which would inflate `projects_detected`
    and distort cross-project propagation metrics.

    Sessions without cwd return None and are bucketed into "_unknown" by the
    caller.
    """
    cwd = session.get("environment", {}).get("cwd") or session.get("metadata", {}).get("cwd")
    if not cwd:
        return None

    # Strip leading /Users/<name>/ or /home/<name>/ so the same project under
    # different home directories hashes identically.
    path = cwd
    if path.startswith("/Users/") or path.startswith("/home/"):
        parts = path.split("/", 3)
        if len(parts) >= 3:
            path = "/" + parts[3] if len(parts) > 3 else ""
    path = path.rstrip("/")

    components = [p for p in path.split("/") if p]

    # Walk up from the tail, discarding known source-tree subdirectories
    # until we find a component that plausibly names the repo root. Stop as
    # soon as we hit something not in the blocklist. This keeps `repo/src`
    # and `repo/tests` both mapping to `repo` for the final component.
    while components and components[-1].lower() in _PROJECT_SUBDIR_BLOCKLIST:
        components.pop()

    if not components:
        return "project_root"

    # Take up to two trailing components as the canonical key. Using only
    # the deepest component would collide unrelated repos with the same
    # basename (e.g. `/workspace/team-a/service` and
    # `/workspace/team-b/service` → both `service`). Including the parent
    # directory disambiguates organisation/team/account-scoped layouts
    # while still collapsing `/repo/src` and `/repo/tests` to the same
    # `parent/repo` canonical after the blocklist walk above.
    if len(components) >= 2:
        canonical = f"{components[-2]}/{components[-1]}"
    else:
        canonical = components[-1]

    short_hash = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:8]
    return f"project_{short_hash}"

def extract_bigrams(session):
    """Extract tool-call bigrams from session."""
    tools = []
    for msg in session.get("messages", []):
        if msg.get("role") == "Assistant":
            for tc in msg.get("tool_calls", []) or []:
                name = tc.get("name")
                if name:
                    tools.append(name)
    
    bigrams = []
    for i in range(len(tools) - 1):
        bigrams.append((tools[i], tools[i+1]))
    return bigrams

def logistic(t, L, k, t0):
    """Logistic growth function."""
    return L / (1 + np.exp(-k * (t - t0)))

def sir_model(state, t, beta, gamma, N):
    """SIR model differential equations."""
    S, I, R = state
    dSdt = -beta * S * I / N
    dIdt = beta * S * I / N - gamma * I
    dRdt = gamma * I
    return [dSdt, dIdt, dRdt]

def sir_cumulative(t, beta, gamma, N):
    """Get cumulative adopters from SIR model."""
    S0, I0, R0 = N - 1, 1, 0
    state0 = [S0, I0, R0]
    t_arr = np.array(t)
    sol = odeint(sir_model, state0, t_arr, args=(beta, gamma, N))
    S, I, R = sol[:, 0], sol[:, 1], sol[:, 2]
    return R + I  # cumulative adopters

def fit_logistic(y, N):
    """Fit logistic model to cumulative adoption curve."""
    t = np.arange(len(y))
    try:
        popt, _ = curve_fit(
            logistic, t, y, 
            p0=[max(y), 0.1, N/2],
            bounds=([1, 0, 0], [N, 5, N])
        )
        y_pred = logistic(t, *popt)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        if ss_tot == 0:
            r2 = 0
        else:
            r2 = 1 - ss_res / ss_tot
        return {"r2": r2, "L": popt[0], "k": popt[1], "t0": popt[2]}
    except Exception as e:
        return {"r2": 0, "L": max(y), "k": 0, "t0": N/2}

def fit_sir(y, N):
    """Fit SIR model to cumulative adoption curve."""
    t = np.arange(len(y))
    
    def wrapper(t_data, beta, gamma):
        return sir_cumulative(t_data, beta, gamma, N)
    
    try:
        popt, _ = curve_fit(
            wrapper, t, y,
            bounds=([0.01, 0.01], [5, 5])
        )
        beta, gamma = popt
        y_pred = wrapper(t, beta, gamma)
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        if ss_tot == 0:
            r2 = 0
        else:
            r2 = 1 - ss_res / ss_tot
        
        # Find peak of I(t)
        state0 = [N - 1, 1, 0]
        t_dense = np.linspace(0, N-1, 1000)
        sol = odeint(sir_model, state0, t_dense, args=(beta, gamma, N))
        I = sol[:, 1]
        peak_idx = int(t_dense[np.argmax(I)])
        
        R0 = beta / gamma if gamma > 0 else 0
        
        return {"r2": r2, "beta": beta, "gamma": gamma, "peak": peak_idx, "R0": R0}
    except Exception as e:
        return {"r2": 0, "beta": 0, "gamma": 0, "peak": 0, "R0": 0}

def classify_trajectory(logistic_fit, sir_fit, best_model, N, final_adopters):
    """Classify temporal trajectory of a convention."""
    if best_model == "sir" and sir_fit.get("R0", 0) > 1.5:
        return "epidemic"
    
    if best_model == "logistic":
        t0 = logistic_fit.get("t0", N/2)
        L = logistic_fit.get("L", 0)
        k = logistic_fit.get("k", 0.1)
        
        if t0 < N/3 and L/N > 0.7:
            return "early-saturated"
        elif t0 > 2*N/3:
            return "late-emergent"
        elif k < 0.05:
            return "plateaued"
        else:
            return "other"
    else:  # SIR
        peak = sir_fit.get("peak", N/2)
        
        if peak < N/3 and final_adopters/N > 0.7:
            return "early-saturated"
        elif peak > 2*N/3:
            return "late-emergent"
        elif sir_fit.get("gamma", 0) > sir_fit.get("beta", 0):
            return "plateaued"
        else:
            return "other"

def classify_propagation_pattern(reach, latencies, projects_detected):
    """Classify cross-project propagation pattern.

    Precedence (mutually exclusive):
      1. ubiquitous — reach > 0.8
      2. confined   — reach ≤ 0.2 (inclusive; exact 20% reach means the
                      candidate is in at most the origin project bucket
                      for a 5-project corpus, so it's confined, not cross-project)
      3. radial/sequential/diffuse — only when there are ≥3 total adopters
                      (i.e. ≥2 entries in `latencies`, which excludes the origin)
      4. else confined (fewer than 3 adopters, intermediate reach)
    """
    if reach > 0.8:
        return "ubiquitous"
    elif reach <= 0.2:
        return "confined"
    elif len(latencies) >= 2:
        # Check if >=3 adopters within 30 days of origin
        early_adopters = sum(1 for l in latencies if l <= 30)
        if early_adopters >= 2:  # >=3 total including origin
            return "radial"
        
        # Check sequential: monotonically spaced within 60 days
        sorted_latencies = sorted(latencies)
        is_sequential = True
        for i in range(1, len(sorted_latencies)):
            if sorted_latencies[i] > sorted_latencies[i-1] + 60:
                is_sequential = False
                break
        
        if is_sequential and len(latencies) >= 2:
            return "sequential"
        else:
            return "diffuse"
    else:
        return "confined"

def analyze(sessions):
    """Main analysis function."""
    N = len(sessions)
    
    # Phase 0: Prepare inputs
    session_data = []
    for session in sessions:
        first_ts = get_first_ts(session)
        project_id = get_project_id(session)
        session_data.append({
            "session": session,
            "first_ts": first_ts,
            "project_id": project_id or "_unknown"
        })
    
    # Fall back to array-index ordering if no sessions have timestamps.
    from datetime import datetime, timedelta
    with_ts = [s for s in session_data if s["first_ts"] is not None]
    if not with_ts:
        # Synthesize monotonic timestamps from array index (1 day apart).
        base = datetime(2020, 1, 1)
        for idx, sd in enumerate(session_data):
            sd["first_ts"] = base + timedelta(days=idx)
    else:
        # Keep only sessions with timestamps (preserves original behavior when some have them).
        session_data = with_ts

    if len(session_data) < MIN_SESSIONS:
        return empty_result(f"insufficient data: need at least {MIN_SESSIONS} sessions, got {len(session_data)}")

    # Sort by first_ts
    session_data.sort(key=lambda x: x["first_ts"])
    
    # Group by project
    projects = defaultdict(list)
    for sd in session_data:
        projects[sd["project_id"]].append(sd)
    
    # Sort within each project
    for pid in projects:
        projects[pid].sort(key=lambda x: x["first_ts"])
    
    projects_detected = len([p for p in projects if p != "_unknown"])
    sessions_without_cwd = sum(1 for sd in session_data if sd["project_id"] == "_unknown")
    
    # Phase 1: Candidate conventions
    all_bigrams = Counter()
    bigram_sessions = defaultdict(set)
    bigram_projects = defaultdict(set)
    session_bigrams = {}
    
    for i, sd in enumerate(session_data):
        bigrams = extract_bigrams(sd["session"])
        session_bigrams[i] = bigrams
        for bg in bigrams:
            all_bigrams[bg] += 1
            bigram_sessions[bg].add(i)
            bigram_projects[bg].add(sd["project_id"])
    
    # Filter candidates by session-count thresholds only (Phase 1).
    # Cross-project requirements are applied strictly in Phase 3 — single-project
    # candidates must flow through Phase 2 (within-workflow fits) and surface as
    # "confined" in the Phase 3 classification.
    #
    # The 10% threshold uses math.ceil, not int(), so the "≥10% of sessions"
    # rule is faithful. For N=59, int(0.1*59)=5 (8.5%) passes, but ceil(5.9)=6
    # correctly requires at least 10.2% support.
    candidates = []
    min_sessions_threshold = max(5, math.ceil(0.1 * len(session_data)))

    for bg, count in all_bigrams.items():
        sessions_with = len(bigram_sessions[bg])
        if sessions_with >= min_sessions_threshold and sessions_with >= 5:
            candidates.append(bg)
    
    conventions_detected = len(candidates)
    
    if conventions_detected == 0:
        return {
            "name": NAME,
            "summary": f"Convention epidemiology analysis of {len(session_data)} sessions across {projects_detected} projects detected 0 tool-use conventions.",
            "findings": [
                {"label": "sessions_analyzed", "value": len(session_data)},
                {"label": "projects_detected", "value": projects_detected},
                {"label": "sessions_without_cwd", "value": sessions_without_cwd},
                {"label": "conventions_detected", "value": 0},
                {"label": "conventions_fitted", "value": 0},
                {"label": "top_convention", "value": "none"},
                {"label": "top_convention_r2", "value": None},
                {"label": "top_convention_r0", "value": None},
                {"label": "epidemic_conventions", "value": 0},
                {"label": "cross_project_conventions", "value": 0},
                {"label": "ubiquitous_conventions", "value": 0},
                {"label": "radial_conventions", "value": 0},
                {"label": "sequential_conventions", "value": 0},
                {"label": "top_cross_project_convention", "value": "none"},
                {"label": "top_cross_project_reach", "value": None},
                {"label": "mean_inter_project_latency_days", "value": None},
            ],
            "tables": [
                {"name": "Within-Workflow Fits", "columns": ["bigram", "n_adopters", "best_model", "r2", "k_or_beta", "inflection_or_peak", "trajectory_class"], "rows": []},
                {"name": "Cross-Project Propagation", "columns": ["bigram", "origin_project", "reach", "n_projects_adopted", "median_latency_days", "propagation_pattern"], "rows": []},
                {"name": "Convention × Project Matrix", "columns": ["bigram", "project_id", "first_seen_timestamp", "latency_days_from_origin"], "rows": []},
            ],
            "figures": []
        }
    
    # Phase 2: Within-workflow fits
    M = len(session_data)
    candidate_results = {}
    
    for bg in candidates:
        # Build cumulative adoption curve
        adopting_sessions = sorted(bigram_sessions[bg])
        y = []
        adopters_set = set()
        for i in range(M):
            if i in adopting_sessions:
                adopters_set.add(i)
            y.append(len(adopters_set))
        y = np.array(y, dtype=float)
        
        # Fit models
        log_fit = fit_logistic(y, M)
        sir_fit = fit_sir(y, M)
        
        # Choose best model
        if log_fit["r2"] >= sir_fit["r2"]:
            best_model = "logistic"
            best_r2 = log_fit["r2"]
            k_or_beta = log_fit["k"]
            inflection = int(round(log_fit["t0"]))
        else:
            best_model = "sir"
            best_r2 = sir_fit["r2"]
            k_or_beta = sir_fit["beta"]
            inflection = sir_fit["peak"]
        
        # Classify trajectory
        trajectory = classify_trajectory(log_fit, sir_fit, best_model, M, y[-1])
        
        candidate_results[bg] = {
            "n_adopters": len(adopting_sessions),
            "best_model": best_model,
            "r2": best_r2,
            "k_or_beta": k_or_beta,
            "inflection_or_peak": inflection,
            "trajectory_class": trajectory,
            "logistic_fit": log_fit,
            "sir_fit": sir_fit,
            "adopting_sessions": adopting_sessions
        }
    
    conventions_fitted = sum(1 for cr in candidate_results.values() if cr["r2"] > 0.7)
    epidemic_conventions = sum(1 for cr in candidate_results.values() if cr["trajectory_class"] == "epidemic")
    
    # Find top convention
    top_bg = None
    top_r2 = -1
    for bg, cr in candidate_results.items():
        if cr["r2"] > top_r2:
            top_r2 = cr["r2"]
            top_bg = bg
    
    top_convention_str = f"{top_bg[0]}→{top_bg[1]}" if top_bg else "none"
    top_convention_r2 = round(candidate_results[top_bg]["r2"], 4) if top_bg else None
    top_convention_r0 = None
    if top_bg and candidate_results[top_bg]["best_model"] == "sir":
        top_convention_r0 = round(candidate_results[top_bg]["sir_fit"].get("R0", 0), 4)
    
    # Within-workflow table (top 10 by r2)
    sorted_candidates = sorted(candidate_results.items(), key=lambda x: x[1]["r2"], reverse=True)[:10]
    within_workflow_rows = []
    for bg, cr in sorted_candidates:
        row = [
            f"{bg[0]}→{bg[1]}",
            cr["n_adopters"],
            cr["best_model"],
            round(cr["r2"], 4),
            round(cr["k_or_beta"], 4),
            cr["inflection_or_peak"],
            cr["trajectory_class"]
        ]
        within_workflow_rows.append(row)
    
    # Phase 3: Cross-project propagation
    cross_project_rows = []
    matrix_rows = []
    cross_project_conventions = 0
    ubiquitous_conventions = 0
    radial_conventions = 0
    sequential_conventions = 0
    top_cross_project_convention = "none"
    top_cross_project_reach = None
    mean_inter_project_latency = None
    
    if projects_detected < 3:
        # Skip Phase 3
        summary_suffix = "insufficient projects for cross-project analysis (minimum 3 required)"
    else:
        # Calculate cross-project metrics
        cross_project_data = []
        all_latencies = []
        
        for bg in candidates:
            # First seen per project. Iterate the adopter index set directly
            # (bigram_sessions[bg] already contains the int positional indices
            # from the earlier enumerate). Keying on the positional index is
            # the only identity guaranteed unique in this run — raw
            # session["id"] strings can collide when the parser falls back
            # to file-stem IDs on merged corpora.
            first_seen = {}
            for i in bigram_sessions[bg]:
                sd = session_data[i]
                pid = sd["project_id"]
                # Exclude the no-cwd bucket from cross-project analysis entirely
                # so it can never become origin and never contribute to reach.
                if pid == "_unknown":
                    continue
                if pid not in first_seen or sd["first_ts"] < first_seen[pid]:
                    first_seen[pid] = sd["first_ts"]
            
            # Find origin
            if not first_seen:
                continue
            
            origin_project = min(first_seen, key=first_seen.get)
            origin_ts = first_seen[origin_project]
            
            # Calculate latencies
            latencies = []
            for pid, ts in first_seen.items():
                if pid != origin_project and pid != "_unknown":
                    latency = (ts - origin_ts).total_seconds() / 86400
                    latencies.append(latency)
            
            # Calculate reach
            adopting_projects = len([p for p in first_seen if p != "_unknown"])
            reach = adopting_projects / projects_detected if projects_detected > 0 else 0
            
            # Classify pattern
            pattern = classify_propagation_pattern(reach, latencies, projects_detected)
            
            # Count categories. "cross-project" means "actually spread beyond
            # the origin project", which is only well-defined as
            # adopting_projects >= 2 — a reach-threshold test fails at small
            # project counts (at projects_detected=3, reach=0.333 for an
            # origin-only convention would falsely pass a > 0.2 test).
            if adopting_projects >= 2:
                cross_project_conventions += 1
            if pattern == "ubiquitous":
                ubiquitous_conventions += 1
            elif pattern == "radial":
                radial_conventions += 1
            elif pattern == "sequential":
                sequential_conventions += 1
            
            cross_project_data.append({
                "bigram": bg,
                "origin_project": origin_project,
                "reach": reach,
                "n_projects_adopted": adopting_projects,
                "latencies": latencies,
                "median_latency": np.median(latencies) if latencies else None,
                "pattern": pattern,
                "first_seen": first_seen,
                "origin_ts": origin_ts,
                "r2": candidate_results[bg]["r2"]
            })
            
            if latencies:
                all_latencies.extend(latencies)
        
        # Sort by reach for table
        sorted_cp = sorted(cross_project_data, key=lambda x: x["reach"], reverse=True)
        
        # Top cross-project convention
        if sorted_cp:
            top_cp = sorted_cp[0]
            top_cross_project_convention = f"{top_cp['bigram'][0]}→{top_cp['bigram'][1]}"
            top_cross_project_reach = round(top_cp["reach"], 4)
        
        # Mean inter-project latency
        if all_latencies:
            mean_inter_project_latency = round(np.mean(all_latencies), 2)
        
        # Build tables (top 10 by reach)
        for cp in sorted_cp[:10]:
            row = [
                f"{cp['bigram'][0]}→{cp['bigram'][1]}",
                cp["origin_project"],
                round(cp["reach"], 4),
                cp["n_projects_adopted"],
                round(cp["median_latency"], 4) if cp["median_latency"] is not None else None,
                cp["pattern"]
            ]
            cross_project_rows.append(row)
        
        # Build matrix (top 10 bigrams by reach × projects, cap 100 rows)
        row_count = 0
        for cp in sorted_cp[:10]:
            for pid, ts in cp["first_seen"].items():
                if row_count >= 100:
                    break
                if pid == "_unknown":
                    continue
                latency = (ts - cp["origin_ts"]).total_seconds() / 86400 if pid != cp["origin_project"] else 0
                matrix_row = [
                    f"{cp['bigram'][0]}→{cp['bigram'][1]}",
                    pid,
                    ts.isoformat(),
                    round(latency, 2) if latency > 0 else 0
                ]
                matrix_rows.append(matrix_row)
                row_count += 1
        
        summary_suffix = f"Cross-project propagation shows '{top_cross_project_convention}' reaching {top_cross_project_reach} of projects."
    
    # Build summary
    summary = f"Convention epidemiology analysis of {len(session_data)} sessions across {projects_detected} projects detected {conventions_detected} tool-use conventions, {conventions_fitted} with strong logistic/SIR fits. {summary_suffix}"
    
    # Build findings
    findings = [
        {"label": "sessions_analyzed", "value": len(session_data)},
        {"label": "projects_detected", "value": projects_detected},
        {"label": "sessions_without_cwd", "value": sessions_without_cwd},
        {"label": "conventions_detected", "value": conventions_detected},
        {"label": "conventions_fitted", "value": conventions_fitted},
        {"label": "top_convention", "value": top_convention_str},
        {"label": "top_convention_r2", "value": top_convention_r2},
        {"label": "top_convention_r0", "value": top_convention_r0},
        {"label": "epidemic_conventions", "value": epidemic_conventions},
        {"label": "cross_project_conventions", "value": cross_project_conventions},
        {"label": "ubiquitous_conventions", "value": ubiquitous_conventions},
        {"label": "radial_conventions", "value": radial_conventions},
        {"label": "sequential_conventions", "value": sequential_conventions},
        {"label": "top_cross_project_convention", "value": top_cross_project_convention},
        {"label": "top_cross_project_reach", "value": top_cross_project_reach},
        {"label": "mean_inter_project_latency_days", "value": mean_inter_project_latency},
    ]
    
    # Build tables
    tables = [
        {"name": "Within-Workflow Fits", "columns": ["bigram", "n_adopters", "best_model", "r2", "k_or_beta", "inflection_or_peak", "trajectory_class"], "rows": within_workflow_rows},
        {"name": "Cross-Project Propagation", "columns": ["bigram", "origin_project", "reach", "n_projects_adopted", "median_latency_days", "propagation_pattern"], "rows": cross_project_rows},
        {"name": "Convention × Project Matrix", "columns": ["bigram", "project_id", "first_seen_timestamp", "latency_days_from_origin"], "rows": matrix_rows},
    ]
    
    return {
        "name": NAME,
        "summary": summary,
        "findings": findings,
        "tables": tables,
        "figures": []
    }

def main():
    if len(sys.argv) < 2:
        print("usage: convention_epidemiology.py <sessions.json>", file=sys.stderr)
        sys.exit(1)
    try:
        with open(sys.argv[1]) as f:
            sessions = json.load(f)
    except Exception as e:
        print(f"Failed to read sessions: {e}", file=sys.stderr)
        sys.exit(1)

    if not sessions:
        print(json.dumps(empty_result("No sessions to analyze")))
        return

    if len(sessions) < MIN_SESSIONS:
        print(json.dumps(empty_result(
            f"insufficient data: need at least {MIN_SESSIONS} sessions, got {len(sessions)}"
        )))
        return

    # --- technique-specific analysis ---
    result = analyze(sessions)
    print(json.dumps(sanitize(result), default=str))

if __name__ == "__main__":
    main()
