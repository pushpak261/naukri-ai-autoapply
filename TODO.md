# TODO

## Screening Question Answering Accuracy Upgrade ✅
- [x] Normalize question text (punctuation/whitespace/case) for direct-answer + cache keys
- [x] Update QA cache to use normalized keys (both `get` and `set`)
- [x] Constrain answers to provided `options` (fuzzy match fallback for AI answers)
- [x] Add JSON parsing repair (strip code fences, retry parse)
- [x] Add one correction LLM retry when JSON parsing fails
- [x] Improve PDF raw-text usage by selecting relevant snippets
- [x] Save updated answers back to cache
- [x] Run test suite (333 passed)

