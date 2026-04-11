
import sys
import json
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import grangercausalitytests
from scipy.stats import chi2
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

def shannon_entropy(dist):
    dist = dist[dist > 0]
    return -np.sum(dist * np.log2(dist))

def get_tool_dist(tool_calls):
    dist = {'read': 0, 'edit': 0, 'bash': 0, 'search': 0, 'skill': 0, 'other': 0}
    if not tool_calls:
        return dist
    for call in tool_calls:
        name = call.get('name', '').lower()
        if any(sub in name for sub in ['read', 'glob', 'grep']): dist['read'] += 1
        elif any(sub in name for sub in ['edit', 'write']): dist['edit'] += 1
        elif 'bash' in name: dist['bash'] += 1
        elif any(sub in name for sub in ['websearch', 'webfetch']): dist['search'] += 1
        elif 'skill' in name: dist['skill'] += 1
        else: dist['other'] += 1
    return dist

def create_time_series(session):
    series_data = []
    messages = session['messages']
    assistant_msgs = []
    
    # Pre-build a map of tool call IDs to their results for the session
    tool_results = {res['tool_use_id']: res for m in messages if m.get('tool_results') for res in m['tool_results']}

    # Find assistant messages and their next user message's classification
    for i, msg in enumerate(messages):
        if msg['role'] == 'Assistant':
            is_corrected = False
            if (i + 1) < len(messages) and messages[i+1]['role'] == 'User':
                if messages[i+1].get('classification') == 'HumanCorrection':
                    is_corrected = True
            assistant_msgs.append((msg, is_corrected))

    for msg, is_corrected in assistant_msgs:
        text_len = len(msg.get('text') or '')
        thinking_len = len(msg.get('thinking') or '')
        thinking_ratio = thinking_len / text_len if text_len > 0 else 0
        message_length = np.log1p(text_len)
        correction_indicator = 1 if is_corrected else 0
        
        tool_failure_indicator = 0
        if msg.get('tool_calls'):
            call_ids = {c['id'] for c in msg['tool_calls']}
            for call_id in call_ids:
                if tool_results.get(call_id, {}).get('is_error'):
                    tool_failure_indicator = 1
                    break
        
        series_data.append([thinking_ratio, message_length, correction_indicator, tool_failure_indicator])

    if not series_data:
        return pd.DataFrame(columns=['thinking_ratio', 'tool_diversity', 'message_length', 'correction_indicator', 'tool_failure_indicator'])

    df = pd.DataFrame(series_data, columns=['thinking_ratio', 'message_length', 'correction_indicator', 'tool_failure_indicator'])

    tool_dists = [get_tool_dist(m.get('tool_calls')) for m, _ in assistant_msgs]
    tool_counts_df = pd.DataFrame(tool_dists)
    
    rolling_sum = tool_counts_df.rolling(window=5, min_periods=1).sum()
    rolling_total = rolling_sum.sum(axis=1)
    
    rolling_props = rolling_sum.div(rolling_total, axis=0).fillna(0)
    
    df['tool_diversity'] = rolling_props.apply(shannon_entropy, axis=1)

    return df[['thinking_ratio', 'tool_diversity', 'message_length', 'correction_indicator', 'tool_failure_indicator']]

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"name": "granger_causality", "summary": "Error: No input file path provided.", "findings": [], "tables": [], "figures": []}))
        sys.exit(1)

    input_path = sys.argv[1]
    try:
        with open(input_path, 'r') as f:
            sessions = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        import sys as _sys; print(f"Error: Cannot read or parse session file at {input_path}", file=_sys.stderr); print(json.dumps({"name": "granger_causality", "summary": f"Error: Cannot read or parse session file at {input_path}", "findings": [], "tables": [], "figures": []}))
        sys.exit(1)


    if not sessions:
        print(json.dumps({"name": "granger_causality", "summary": "No sessions found in the input file.", "findings": [], "tables": [], "figures": []}))
        return
        
    series_names = ['thinking_ratio', 'tool_diversity', 'message_length', 'correction_indicator', 'tool_failure_indicator']
    pairs = [(c, e) for c in series_names for e in series_names if c != e]
    
    session_p_values = {pair: [] for pair in pairs}
    sessions_analyzed = 0
    min_turns = 25
    skipped_sessions = 0

    for session in sessions:
        df = create_time_series(session)
        
        if len(df) < min_turns:
            skipped_sessions += 1
            continue
        
        sessions_analyzed += 1
        
        # Adjust max_lags based on data length to avoid errors
        # grangercausalitytests requires: nobs - lags * k > 0
        # where k is number of variables (2)
        # So, len(df) - max_lags * 2 > 0  => max_lags < len(df) / 2
        max_lags = min(5, int(len(df) / 2) - 1)
        if max_lags < 1:
            continue

        for cause, effect in pairs:
            try:
                # Ensure data has some variance
                if df[cause].std() < 1e-6 or df[effect].std() < 1e-6:
                    continue

                test_result = grangercausalitytests(df[[effect, cause]], maxlag=max_lags, verbose=False)

                p_value = test_result[max_lags][0]['ssr_ftest'][1]
                if p_value > 0:  # Avoid log(0)
                    session_p_values[(cause, effect)].append(p_value)

            except Exception:
                continue
    
    if sessions_analyzed == 0:
        summary = f"Insufficient data: no sessions had the required {min_turns} assistant turns."
        print(json.dumps({"name": "granger_causality", "summary": summary, "findings": [{"label":"sessions_analyzed", "value":0}], "tables": [], "figures": []}))
        return

    final_results = []
    for pair, p_vals in session_p_values.items():
        if not p_vals:
            continue
        
        # Fisher's method for aggregating p-values from different sessions
        chi_squared_stat = -2 * np.sum(np.log(p_vals))
        combined_p = chi2.sf(chi_squared_stat, df=2 * len(p_vals))
        final_results.append({'pair': pair, 'p_value': combined_p})

    if not final_results:
        summary = f"Granger causality analysis on {sessions_analyzed} sessions yielded no valid results."
        print(json.dumps({"name": "granger_causality", "summary": summary, "findings": [], "tables": []}))
        return

    num_pairs = len(final_results)
    for res in final_results:
        res['p_value_corr'] = min(res['p_value'] * num_pairs, 1.0)
    
    final_results.sort(key=lambda x: x['p_value_corr'])
    
    strongest_pair_res = final_results[0]
    strongest_pair = f"{strongest_pair_res['pair'][0]} -> {strongest_pair_res['pair'][1]}"
    strongest_pair_p = strongest_pair_res['p_value_corr']
    
    significant_pairs = sum(1 for res in final_results if res['p_value_corr'] < 0.05)
    
    thinking_causes_correction_p = 1.0
    for res in final_results:
        if res['pair'] == ('thinking_ratio', 'correction_indicator'):
            thinking_causes_correction_p = res['p_value_corr']
            break
    thinking_causes_correction = thinking_causes_correction_p < 0.05
    
    findings = [
        {"label": "significant_pairs", "value": significant_pairs},
        {"label": "strongest_pair", "value": strongest_pair},
        {"label": "strongest_pair_p", "value": strongest_pair_p},
        {"label": "thinking_causes_correction", "value": bool(thinking_causes_correction)},
        {"label": "sessions_analyzed", "value": sessions_analyzed}
    ]

    table_rows = []
    for res in sorted(final_results, key=lambda x: x['p_value_corr']):
        cause, effect = res['pair']
        p_val = res['p_value_corr']
        table_rows.append([cause, effect, p_val, p_val < 0.05])

    tables = [{"name": "Granger Causality Results", "columns": ["Cause", "Effect", "Corrected P-Value", "Is Significant"], "rows": table_rows}]

    summary = f"Performed Granger causality analysis on {sessions_analyzed} sessions with Bonferroni correction. Found {significant_pairs} significant relationships."
    if skipped_sessions > 0:
        summary += f" Skipped {skipped_sessions} sessions due to insufficient turns (< {min_turns})."
    
    output = {"name": "granger_causality", "summary": summary, "findings": findings, "tables": tables}
    print(json.dumps(sanitize_for_json(output)))

if __name__ == "__main__":
    main()
