import json
import math
import re
import sys
from collections import Counter


# Category patterns (case-insensitive)
CORRECTION = [r'\bno[,]?\s', r'^no$', r'\bwrong\b', r'\bnot that\b', r'\binstead\b',
              r'\bactually[,]?\s', r'\bi said\b', r'\bi meant\b', r'\bnope\b', r'\bundo\b',
              r'\brevert\b', r'\btry again\b', r'\bincorrect\b']
REDIRECT = [r'^stop\b', r'^wait\b', r'\bhold on\b', r"^let's\b", r'\bforget\b', r'\bskip\b',
            r'\bignore\b', r'\bnever\s?mind\b', r'\bnvm\b']
DIRECTIVE = [r'^(make|create|add|remove|delete|write|implement|build|run|fix|update|change|refactor|rename|move|test|check|verify|show|explain|list)\b']
APPROVAL = [r'^(good|great|perfect|excellent|nice|yes|yep|yeah|ok|okay|sure|thanks|thank you)\b',
            r'\blooks good\b', r'\blgtm\b', r'\bwell done\b']
QUESTION = [r'\?\s*$', r'^(what|how|why|when|where|which|who|can you|could you|would you|should)\b']

# Frustration patterns
FRUSTRATION_MILD = [r'\bhmm\b', r'\bsigh\b', r'\bugh\b', r'\bmeh\b']
FRUSTRATION_MEDIUM = [r'\bno\b', r'\bnope\b', r'\bwrong\b', r'\bstop\b']
FRUSTRATION_FIRM = [r'\bi said\b', r'\bstill wrong\b', r'\blisten\b']
FRUSTRATION_EXASPERATED = [r'\bwhy did you\b', r'\bwhy are you\b', r'\bfor the (last|nth) time\b']

def sanitize(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return obj

def is_english(text):
    """Check if text is English: fraction of ASCII letters >= 0.85"""
    non_space = [c for c in text if not c.isspace()]
    if not non_space:
        return True
    ascii_letters = [c for c in non_space if c.isascii() and c.isalpha()]
    return len(ascii_letters) / len(non_space) >= 0.85

def strip_boilerplate(text):
    """Remove system-reminder, command-name, and Request interrupted"""
    text = re.sub(r'<system-reminder>.*?</system-reminder>', '', text, flags=re.DOTALL)
    text = re.sub(r'<command-name>.*?</command-name>', '', text, flags=re.DOTALL)
    text = re.sub(r'\[Request interrupted\]', '', text)
    return text.strip()

def compute_frustration(text):
    """Compute frustration score 0-5"""
    text_lower = text.lower()
    score = 0
    
    # Mild
    if any(re.search(p, text_lower) for p in FRUSTRATION_MILD):
        score += 1
    
    # Medium
    if any(re.search(p, text_lower) for p in FRUSTRATION_MEDIUM):
        score += 2
    
    # Firm
    if any(re.search(p, text_lower) for p in FRUSTRATION_FIRM):
        score += 3
    
    # Exasperated
    if any(re.search(p, text_lower) for p in FRUSTRATION_EXASPERATED):
        score += 4
    
    # Bonus
    if len(text) > 20:
        letters = [c for c in text if c.isalpha()]
        if letters:
            upper_frac = sum(1 for c in letters if c.isupper()) / len(letters)
            if upper_frac >= 0.5:
                score += 1
    
    return min(score, 5)

def classify_message(text):
    """Classify message into categories"""
    text_lower = text.lower()
    categories = []
    
    if any(re.search(p, text_lower) for p in CORRECTION):
        categories.append('correction')
    if any(re.search(p, text_lower) for p in REDIRECT):
        categories.append('redirect')
    if any(re.search(p, text_lower) for p in DIRECTIVE):
        categories.append('directive')
    if any(re.search(p, text_lower) for p in APPROVAL):
        categories.append('approval')
    if any(re.search(p, text_lower) for p in QUESTION):
        categories.append('question')
    
    return categories if categories else ['unclassified']

def find_escalations(session_id, messages, frustrations):
    """Find escalation sequences in a session.

    Runs are computed over the filtered sequence of classified *user* messages
    (entries where frustrations[i] is not None), so intervening assistant turns
    (None) do not break a run. start_index is reported as the original message
    index of the run's first user message.
    """
    escalations = []

    # Filter to classified user messages, keeping their original indices.
    user_msgs = [
        (idx, frustrations[idx])
        for idx in range(len(messages))
        if idx < len(frustrations) and frustrations[idx] is not None
    ]

    i = 0
    while i < len(user_msgs):
        run_start = i
        run_max = user_msgs[i][1]

        j = i + 1
        while j < len(user_msgs):
            if user_msgs[j][1] < user_msgs[j - 1][1]:
                break
            run_max = max(run_max, user_msgs[j][1])
            j += 1

        run_length = j - run_start
        if run_length >= 2 and run_max >= 2:
            escalations.append({
                'session_id': session_id,
                'start_index': user_msgs[run_start][0],
                'length': run_length,
                'peak_intensity': run_max
            })

        i = j

    return escalations

def main():
    if len(sys.argv) < 2:
        print("Usage: python user_signal_analysis.py <sessions.json>", file=sys.stderr)
        sys.exit(1)
    
    try:
        with open(sys.argv[1], 'r') as f:
            sessions = json.load(f)
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)
    
    total_user_messages = 0
    messages_classified = 0
    skipped_non_english = 0
    boilerplate_count = 0
    category_counts = Counter()
    frustration_counts = Counter()
    escalations = []
    peak_frustration = -1
    peak_frustration_session_id = ""
    
    for session in sessions:
        session_id = session.get('id', '')
        messages = session.get('messages', [])
        
        # Get frustrations for all messages in this session
        session_frustrations = []
        session_classified = []
        
        for msg in messages:
            if msg.get('role') != 'User':
                session_frustrations.append(None)
                continue
            
            text = msg.get('text', '')
            if not text:
                session_frustrations.append(None)
                continue
            
            total_user_messages += 1
            
            # Strip boilerplate
            stripped = strip_boilerplate(text)
            if not stripped:
                boilerplate_count += 1
                session_frustrations.append(None)
                continue
            
            # Language check
            if not is_english(stripped):
                skipped_non_english += 1
                session_frustrations.append(None)
                continue
            
            messages_classified += 1
            session_classified.append(True)
            
            # Compute frustration
            frustration = compute_frustration(stripped)
            session_frustrations.append(frustration)
            frustration_counts[frustration] += 1
            
            # Track peak
            if frustration > peak_frustration:
                peak_frustration = frustration
                peak_frustration_session_id = session_id
            
            # Classify
            categories = classify_message(stripped)
            for cat in categories:
                category_counts[cat] += 1
        
        # Find escalations in this session
        session_escalations = find_escalations(session_id, messages, session_frustrations)
        escalations.extend(session_escalations)
    
    # Compute findings
    corrections = category_counts['correction']
    redirects = category_counts['redirect']
    directives = category_counts['directive']
    approvals = category_counts['approval']
    questions = category_counts['question']
    unclassified = category_counts['unclassified']
    
    # Category Counts table
    category_rows = []
    if messages_classified > 0:
        for cat in ['correction', 'redirect', 'directive', 'approval', 'question', 'unclassified']:
            count = category_counts[cat]
            pct = count / messages_classified
            category_rows.append([cat, count, pct])
    else:
        category_rows = [[cat, 0, 0.0] for cat in ['correction', 'redirect', 'directive', 'approval', 'question', 'unclassified']]
    
    # Frustration Distribution table
    frustration_rows = [[i, frustration_counts[i]] for i in range(6)]
    
    # Escalation Sequences table
    escalations_sorted = sorted(escalations, key=lambda x: (-x['peak_intensity'], -x['length']))[:20]
    escalation_rows = [[e['session_id'], e['start_index'], e['length'], e['peak_intensity']] for e in escalations_sorted]
    
    # Build result
    if messages_classified == 0:
        summary = "insufficient classified user messages for user signal analysis"
    else:
        summary = f"user signal analysis: {messages_classified} messages classified across {len(sessions)} sessions"
    
    result = {
        "name": "user-signal-analysis",
        "summary": summary,
        "findings": [
            {"label": "total_user_messages", "value": total_user_messages, "description": None},
            {"label": "messages_classified", "value": messages_classified, "description": None},
            {"label": "skipped_non_english_messages", "value": skipped_non_english, "description": None},
            {"label": "boilerplate_messages", "value": boilerplate_count, "description": None},
            {"label": "corrections", "value": corrections, "description": None},
            {"label": "redirects", "value": redirects, "description": None},
            {"label": "directives", "value": directives, "description": None},
            {"label": "approvals", "value": approvals, "description": None},
            {"label": "questions", "value": questions, "description": None},
            {"label": "escalations_found", "value": len(escalations), "description": None},
            {"label": "peak_frustration_session_id", "value": peak_frustration_session_id, "description": None}
        ],
        "tables": [
            {"name": "Category Counts", "columns": ["category", "count", "pct_of_classified"], "rows": category_rows},
            {"name": "Frustration Distribution", "columns": ["intensity", "count"], "rows": frustration_rows},
            {"name": "Escalation Sequences", "columns": ["session_id", "start_index", "length", "peak_intensity"], "rows": escalation_rows}
        ],
        "figures": []
    }
    
    print(json.dumps(sanitize(result), indent=2))

if __name__ == '__main__':
    main()
