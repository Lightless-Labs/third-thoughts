import sys
import json
import os

def main():
    if len(sys.argv) < 2:
        print("Usage: python echo.py <input_json_path>", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    if not os.path.exists(input_path):
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with open(input_path, 'r') as f:
        sessions = json.load(f)

    # Echo back the result
    result = {
        "name": "echo",
        "summary": "Echo test",
        "findings": [
            {
                "label": "session_count",
                "value": len(sessions),
                "description": "Number of sessions"
            }
        ],
        "tables": [],
        "figures": []
    }

    print(json.dumps(result))

if __name__ == "__main__":
    main()
