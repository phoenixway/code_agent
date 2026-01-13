import json
def _extract_json(text: str):
    print(f"DEBUG: Extracting from: {text!r}")
    start_idx = text.find('{')
    if start_idx == -1:
        print("DEBUG: No start brace found")
        return None
    
    next_close = start_idx
    while True:
        next_close = text.find('}', next_close + 1)
        if next_close == -1:
            print("DEBUG: No more closing braces")
            break
        
        candidate = text[start_idx : next_close + 1]
        # print(f"DEBUG: Trying candidate: {candidate!r}")
        try:
            data = json.loads(candidate)
            print("DEBUG: Success!")
            return data
        except json.JSONDecodeError:
            continue
    
    return None

text = '{"type": "write_file", "content": "if (a) { return b; }"}'
res = _extract_json(text)
print(f"Result: {res}")
