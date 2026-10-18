"""Keep structured Gemini output within its generation budget."""


def thinking_config(model_name):
    from google.genai import types

    # Gemini 2.5 Flash shares the output limit with thinking tokens. These
    # short extraction/scoring tasks need the budget for the JSON itself.
    if model_name.startswith("gemini-2.5-flash"):
        return types.ThinkingConfig(thinking_budget=0)
    return None


def ensure_complete(response):
    candidates = getattr(response, "candidates", None)
    reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    if str(getattr(reason, "value", reason)).upper() == "MAX_TOKENS":
        raise ValueError("Gemini output was truncated (MAX_TOKENS); no assessment was approved.")
