# TODO

## Screening Question Answering Accuracy Upgrade
- [ ] Normalize question text (punctuation/whitespace/case) for direct-answer + cache keys
- [ ] Update QA cache to use normalized keys
- [ ] Constrain answers to provided `options` (if present)
- [ ] Add JSON parsing repair (strip code fences, retry parse)
- [ ] Add one correction LLM retry when JSON parsing fails
- [ ] Improve PDF raw-text usage by selecting relevant snippets (CTC/notice/experience/skills)
- [ ] Save updated answers back to cache
- [ ] Run test suite (or at least question_answerer-related tests)

