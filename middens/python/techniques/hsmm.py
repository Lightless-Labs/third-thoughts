
import sys
import json
import numpy as np
import pandas as pd
from hmmlearn import hmm
from collections import Counter
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

def get_tool_categories(tool_calls):
    categories = {'read': 0, 'edit': 0, 'bash': 0, 'search': 0, 'skill': 0, 'other': 0}
    if not tool_calls:
        return categories, 0
    
    for call in tool_calls:
        name = call.get('name', '').lower()
        if any(sub in name for sub in ['read', 'glob', 'grep']): categories['read'] = 1
        elif any(sub in name for sub in ['edit', 'write']): categories['edit'] = 1
        elif 'bash' in name: categories['bash'] = 1
        elif any(sub in name for sub in ['websearch', 'webfetch']): categories['search'] = 1
        elif 'skill' in name: categories['skill'] = 1
        else: categories['other'] = 1
    
    return categories, len(tool_calls)

def process_sessions(sessions):
    sequences = []
    lengths = []
    all_corrections = []

    for session in sessions:
        features = []
        corrections = []
        messages = session.get('messages', [])
        
        for i in range(len(messages)):
            if messages[i].get('role') == 'Assistant':
                assistant_msg = messages[i]
                
                categories, tool_count = get_tool_categories(assistant_msg.get('tool_calls'))
                log_msg_len = np.log(len(assistant_msg.get('text', '')) + 1)
                thinking_len = len(assistant_msg.get('thinking', '')) if assistant_msg.get('thinking') else 0
                
                turn_features = [
                    categories['read'], categories['edit'], categories['bash'], 
                    categories['search'], categories['skill'], categories['other'],
                    log_msg_len, thinking_len, tool_count
                ]
                features.append(turn_features)

                is_correction = 0
                if (i + 1) < len(messages) and messages[i+1].get('role') == 'User':
                    if messages[i+1].get('classification') == 'HumanCorrection':
                        is_correction = 1
                corrections.append(is_correction)

        if features:
            sequences.append(np.array(features))
            lengths.append(len(features))
            all_corrections.extend(corrections)

    if not sequences:
        return np.array([]), np.array([]), np.array([])
        
    return np.concatenate(sequences), np.array(all_corrections), np.array(lengths)

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"name": "hsmm", "summary": "Error: No input file path provided.", "findings": [], "tables": []}))
        sys.exit(1)

    input_path = sys.argv[1]
    try:
        with open(input_path, 'r') as f:
            sessions = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Error: Cannot read or parse session file at {input_path}", file=sys.stderr)
        summary = f"Error: Cannot read or parse session file at {input_path}"
        print(json.dumps({"name": "hsmm", "summary": summary, "findings": [], "tables": []}))
        sys.exit(1)

    if not sessions:
        summary = "HSMM analysis: 0 sessions were analyzed. No sessions found in the input file."
        print(json.dumps({"name": "hsmm", "summary": summary, "findings": [], "tables": []}))
        return

    if len(sessions) < 10:
        summary = f"HSMM analysis: insufficient data — only {len(sessions)} sessions provided, need at least 10 for reliable HMM fitting."
        print(json.dumps({"name": "hsmm", "summary": summary, "findings": [], "tables": []}))
        return

    try:
        features, corrections, lengths = process_sessions(sessions)

        if features.shape[0] < 20:
            summary = f"HSMM analysis: insufficient data — only {features.shape[0]} assistant turns found, need at least 20."
            print(json.dumps({"name": "hsmm", "summary": summary, "findings": [], "tables": []}))
            return

        n_components_range = range(2, 6)
        best_bic = np.inf
        best_model = None
        
        for n_components in n_components_range:
            if features.shape[0] < n_components: continue
            try:
                model = hmm.GaussianHMM(n_components=n_components, covariance_type="diag", n_iter=100, random_state=42)
                model.fit(features, lengths)
                
                log_likelihood = model.score(features, lengths)
                # Compute BIC manually — _n_parameters() not available in all hmmlearn versions
                # For diagonal covariance GaussianHMM: n_params = n*(n-1) + 2*n*d (transitions + means + diag covars)
                n = n_components
                d = features.shape[1]
                n_params = n * (n - 1) + 2 * n * d
                bic = n_params * np.log(features.shape[0]) - 2 * log_likelihood
                
                if bic < best_bic:
                    best_bic = bic
                    best_model = model
            except (ValueError, np.linalg.LinAlgError):
                continue

        if best_model is None:
            summary = "Could not fit a stable HMM model. The data might be too uniform or sparse."
            print(json.dumps({"name": "hsmm", "summary": summary, "findings": [], "tables": []}))
            return

        best_n_components = best_model.n_components
        state_sequence = best_model.predict(features, lengths)
        
        pre_correction_states = state_sequence[corrections == 1]
        dominant_pre_correction_state = None
        pre_correction_lift = 0.0

        if len(pre_correction_states) > 0:
            pre_correction_counts = Counter(pre_correction_states)
            dominant_pre_correction_state = pre_correction_counts.most_common(1)[0][0]

            state_proportions = Counter(state_sequence)
            p_dominant_overall = state_proportions.get(dominant_pre_correction_state, 0) / len(state_sequence)
            p_dominant_pre_correction = pre_correction_counts.get(dominant_pre_correction_state, 0) / len(pre_correction_states)
            
            if p_dominant_overall > 0:
                pre_correction_lift = p_dominant_pre_correction / p_dominant_overall

        state_durations = {i: [] for i in range(best_n_components)}
        if len(state_sequence) > 0:
            current_state, current_duration = state_sequence[0], 1
            for i in range(1, len(state_sequence)):
                # Check for end of a sequence via lengths array
                if i in np.cumsum(lengths)[:-1]:
                    state_durations[current_state].append(current_duration)
                    current_state, current_duration = state_sequence[i], 1
                    continue
                
                state = state_sequence[i]
                if state == current_state:
                    current_duration += 1
                else:
                    state_durations[current_state].append(current_duration)
                    current_state, current_duration = state, 1
            state_durations[current_state].append(current_duration)

        mean_durations = {s: np.mean(d) if d else 0 for s, d in state_durations.items()}
        
        exploring_durations, executing_durations = [], []
        state_classification = {}
        for i in range(best_n_components):
            means = best_model.means_[i]
            # read, search vs edit, bash, skill
            explore_score = means[0] + means[3]
            execute_score = means[1] + means[2] + means[4] + means[5]
            if explore_score > execute_score:
                state_classification[i] = "Exploring"
                exploring_durations.extend(state_durations.get(i, []))
            else:
                state_classification[i] = "Executing"
                executing_durations.extend(state_durations.get(i, []))
        
        mean_state_duration_exploring = np.mean(exploring_durations) if exploring_durations else 0
        mean_state_duration_executing = np.mean(executing_durations) if executing_durations else 0

        findings = [
            {"label": "optimal_n_states", "value": best_n_components},
            {"label": "pre_correction_lift", "value": pre_correction_lift},
            {"label": "dominant_pre_correction_state", "value": dominant_pre_correction_state},
            {"label": "mean_state_duration_exploring", "value": mean_state_duration_exploring},
            {"label": "mean_state_duration_executing", "value": mean_state_duration_executing}
        ]

        trans_matrix = pd.DataFrame(best_model.transmat_, columns=[f"State {i}" for i in range(best_n_components)], index=[f"State {i}" for i in range(best_n_components)])
        
        char_cols = ["Feature"] + [f"State {i}" for i in range(best_n_components)]
        feature_names = ["Read", "Edit", "Bash", "Search", "Skill", "Other", "Log Msg Len", "Thinking Len", "Tool Count"]
        char_rows = [[fname] + [best_model.means_[j][i] for j in range(best_n_components)] for i, fname in enumerate(feature_names)]
        char_rows.append(["Type"] + [state_classification.get(i, "Unknown") for i in range(best_n_components)])
        char_rows.append(["Mean Duration"] + [mean_durations.get(i, 0) for i in range(best_n_components)])

        tables = [
            {"name": "State Transition Matrix", "columns": ["From State"] + list(trans_matrix.columns), "rows": [[idx, *row.values] for idx, row in trans_matrix.iterrows()]},
            {"name": "State Characteristics", "columns": char_cols, "rows": char_rows }
        ]
        
        summary = f"HSMM analysis: fitted a Gaussian HMM with {best_n_components} states. Model analyzed {features.shape[0]} assistant turns from {len(sessions)} sessions."
        if dominant_pre_correction_state is None:
            summary += " No 'HumanCorrection' events were found to identify a pre-correction state."

        result = {"name": "hsmm", "summary": summary, "findings": findings, "tables": tables}
        print(json.dumps(sanitize_for_json(result)))

    except Exception as e:
        summary = f"An unexpected error occurred during analysis: {e}"
        print(json.dumps({"name": "hsmm", "summary": summary, "findings": [], "tables": []}))

if __name__ == "__main__":
    main()
