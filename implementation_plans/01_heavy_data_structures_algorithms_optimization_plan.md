# Heavy Data Structures & Algorithms Optimization Plan

This document outlines the architectural implementation of advanced Data Structures and Algorithms (DSA) into the AI Job Application Agent. The goal is to aggressively reduce time complexity, minimize database queries, prioritize high-quality jobs, and reduce expensive AI API calls.

## User Review Required

> [!WARNING]
> Please review this plan carefully. These are significant architectural changes to the core matching and search loops.
> If you approve, I will begin implementing these algorithms into the codebase.

## Open Questions

> [!IMPORTANT]
> 1. **Aho-Corasick Implementation**: Do you prefer I write a pure Python implementation of a Trie/Aho-Corasick automaton, or can I install the C-optimized `pyahocorasick` library via pip?
> 2. **Pre-filtering Strictness**: We will add a Cosine Similarity algorithm to pre-score jobs before sending them to Gemini. What threshold score (e.g. 30% similarity) should trigger an immediate rejection without consulting the AI?

## Proposed Changes

---

### Deduplication Cache (Hash Set Algorithm)

Currently, the agent performs an `O(N)` database lookup loop checking if a job is already applied. We will implement an `O(1)` Hash Set cache.

#### [MODIFY] `src/database/repository.py`
- Pre-load all applied `naukri_job_id`s into a Python `set()` at agent startup.
- Change `is_already_applied` to check the Hash Set in `O(1)` time complexity rather than performing a SQLAlchemy SQL query for every single job encountered.
- Add methods to dynamically insert new jobs into the Hash Set after a successful application.

---

### Pre-filtering (TF-IDF & Cosine Similarity)

AI evaluations (via Gemini) are heavy, slow, and consume valuable API tokens. We will implement a fast mathematical pre-filter using Vector Space Mathematics.

#### [NEW] `src/ai/similarity.py`
- Implement **Term Frequency-Inverse Document Frequency (TF-IDF)** to vectorize the parsed resume skills and the job description.
- Calculate the **Cosine Similarity** (dot product over magnitude) between the two vectors.
- Reject mathematically poor matches in `O(N)` time complexity before they ever reach the Gemini AI API, saving hundreds of thousands of tokens and drastically increasing performance.

---

### Keyword Exclusion Engine (Aho-Corasick / Trie Automaton)

Currently, exclusion filtering loops over every single keyword and does a substring search over the whole job description, resulting in an `O(N * M)` time complexity (where N is text length and M is keywords).

#### [MODIFY] `src/orchestrator/agent.py`
- Build a **Trie (Prefix Tree)** or **Aho-Corasick Automaton** from the exclusion lists (Companies, Titles, Descriptions).
- Parse the job description in a single `O(N + K)` pass (where K is matches found) to instantly find all prohibited keywords without nested loops.

---

### Job Prioritization (Priority Queue / Max-Heap)

Jobs are currently processed sequentially exactly as they are scraped. If the daily cap is 25, the agent might waste its cap on mediocre jobs early in the list and miss the perfect job at position 30.

#### [MODIFY] `src/orchestrator/agent.py`
- Push all scraped jobs into a **Priority Queue (implemented via Python's `heapq` module as a Max-Heap)**.
- Rank jobs heuristically by "Freshness" (Posted 1 day ago > 30 days ago) and "Initial Keyword Density".
- Pop jobs from the Priority Queue in `O(log N)` time complexity to guarantee that the highest-priority jobs are processed and passed to the AI first.

## Verification Plan

### Automated Tests
- Test the Hash Set lookup against DB queries to ensure identical matching logic but with sub-millisecond execution.
- Validate the Priority Queue orders jobs strictly by our heuristic rules.
- Test the Aho-Corasick string matching to ensure it accurately triggers exclusions.

### Manual Verification
- Run the agent in `dry-run` mode to observe the sorting order of the Max-Heap.
- Verify that API calls are reduced drastically because Cosine Similarity accurately filters out unrelated jobs early.
