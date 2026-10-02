import json


def parse_json_object(raw: str) -> dict:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end < start:
        raise ValueError("No JSON object found in AI response")
    data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("AI response is not a JSON object")
    return data
