
import sys
import json
import numpy as np
import pandas as pd
from lifelines import KaplanMeierFitter, NelsonAalenFitter, CoxPHFitter
import warnings

warnings.filterwarnings("ignore")

def sanitize_for_json(obj):
    if isinstance(obj, (np.integer, np.floating, np.bool_)):
        return obj.item()
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(elem) for elem in obj]
    if isinstance(obj, tuple):
        return tuple(sanitize_for_json(elem) for elem in obj)
    if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
        return None
    return obj

def process_session_for_survival(session):
    user_turns = 0
    time_to_event = None
    event_observed = 0
    tool_calls_5 = 0
    has_thinking = 0
    assistant_turn_count = 0

    for msg in session['messages']:
        if msg['role'] == 'User':
            user_turns += 1
            if msg.get('classification') == 'HumanCorrection' and event_observed == 0:
                event_observed = 1
                time_to_event = user_turns
        
        if msg['role'] == 'Assistant':
            assistant_turn_count += 1
            if msg.get('thinking'):
                has_thinking = 1
            if assistant_turn_count <= 5 and msg.get('tool_calls'):
                tool_calls_5 += len(msg['tool_calls'])
    
    if time_to_event is None:
        time_to_event = user_turns

    first_prompt_length = 0
    if session['messages'] and session['messages'][0]['role'] == 'User':
        first_prompt_length = len(session['messages'][0].get('text', ''))

    return {
        'duration': time_to_event,
        'event': event_observed,
        'first_prompt_length': first_prompt_length,
        'tool_calls_first_5_turns': tool_calls_5,
        'has_thinking': has_thinking,
        'session_type': session.get('session_type', 'Unknown')
    }

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"name": "survival_analysis", "summary": "Error: No input file path provided.", "findings": [], "tables": [], "figures": []}))
        sys.exit(1)

    input_path = sys.argv[1]
    try:
        with open(input_path, 'r') as f:
            sessions = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        import sys as _sys; print(f"Error: Cannot read or parse session file at {input_path}", file=_sys.stderr); print(json.dumps({"name": "survival_analysis", "summary": f"Error: Cannot read or parse session file at {input_path}", "findings": [], "tables": [], "figures": []}))
        sys.exit(1)


    if not sessions:
        summary = "No sessions found in the input file."
        print(json.dumps({"name": "survival_analysis", "summary": summary, "findings": [], "tables": [], "figures": []}))
        return

    survival_data = [process_session_for_survival(s) for s in sessions]
    df = pd.DataFrame(survival_data)
    
    if len(df) < 10:
        summary = f"Insufficient data: at least 10 sessions are required, found {len(df)}."
        print(json.dumps({"name": "survival_analysis", "summary": summary, "findings": [], "tables": [], "figures": []}))
        return

    if df['event'].sum() == 0:
        summary = "No 'HumanCorrection' events observed in any session. Cannot perform survival analysis."
        print(json.dumps({"name": "survival_analysis", "summary": summary, "findings": [], "tables": [], "figures": []}))
        return
    
    findings = []
    tables = []
    
    try:
        # Kaplan-Meier Fitter
        kmf = KaplanMeierFitter()
        kmf.fit(df['duration'], event_observed=df['event'])
        
        median_survival = kmf.median_survival_time_
        survival_at_10 = kmf.predict(10)
        survival_at_20 = kmf.predict(20)

        findings.extend([
            {"label": "median_survival_turns", "value": median_survival if not np.isinf(median_survival) else -1},
            {"label": "survival_at_10", "value": survival_at_10},
            {"label": "survival_at_20", "value": survival_at_20}
        ])
        tables.append({"name": "Survival Probabilities", "columns": ["Turn", "Survival Probability"], "rows": list(kmf.survival_function_.reset_index().itertuples(index=False, name=None))})

        # Nelson-Aalen Fitter for hazard trend
        naf = NelsonAalenFitter()
        naf.fit(df['duration'], event_observed=df['event'])
        
        cum_hazard = naf.cumulative_hazard_
        hazard_trend = "flat"
        if len(cum_hazard) > 2:
            y = cum_hazard.values.flatten()
            second_derivative = np.diff(y, 2)
            if np.mean(second_derivative) > 0.001:
                hazard_trend = "increasing"
            elif np.mean(second_derivative) < -0.001:
                hazard_trend = "decreasing"
        
        findings.append({"label": "hazard_trend", "value": hazard_trend})
        tables.append({"name": "Nelson-Aalen Hazard", "columns": ["Turn", "Cumulative Hazard"], "rows": list(naf.cumulative_hazard_.reset_index().itertuples(index=False, name=None))})
    
    except Exception as e:
        summary = f"Could not perform basic survival analysis. Error: {e}"
        print(json.dumps({"name": "survival_analysis", "summary": summary, "findings": [], "tables": []}))
        return

    # Cox Proportional Hazards Fitter
    try:
        df_cph = pd.get_dummies(df, columns=['session_type'], drop_first=True, dtype=float)
        
        # Remove columns with no variance
        cols_to_use = [col for col in df_cph.columns if df_cph[col].std() > 0 and col not in ['duration', 'event']]
        
        if not cols_to_use:
            raise ValueError("No covariates with sufficient variance for CoxPH model.")

        cph = CoxPHFitter()
        cph.fit(df_cph[['duration', 'event'] + cols_to_use], duration_col='duration', event_col='event')
        
        cox_concordance = cph.concordance_index_
        cph_summary = cph.summary.reset_index()

        findings.append({"label": "cox_concordance", "value": cox_concordance})
        
        cph_summary_values = cph_summary.values
        cph_rows = [list(map(lambda x: round(x, 4) if isinstance(x, (float, np.float64)) else x, r)) for r in cph_summary_values]
        tables.append({"name": "Cox PH Model Covariates", "columns": list(cph_summary.columns), "rows": cph_rows})

    except Exception:
        # This can fail for many reasons (e.g. convergence error), so we just report it.
        findings.append({"label": "cox_concordance", "value": None})
        tables.append({"name": "Cox PH Model Covariates", "columns": ["error"], "rows": [["failed to compute"]]})

    findings.extend([
        {"label": "sessions_with_correction", "value": int(df['event'].sum())},
        {"label": "sessions_censored", "value": int(len(df) - df['event'].sum())}
    ])
    
    summary = f"Kaplan-Meier and Cox Proportional Hazards survival analysis on {len(df)} sessions. {int(df['event'].sum())} sessions had a correction event."
    output = {"name": "survival_analysis", "summary": summary, "findings": findings, "tables": tables}
    print(json.dumps(sanitize_for_json(output)))


if __name__ == "__main__":
    main()
