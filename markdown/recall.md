# memory_recall.md

## Purpose

Add a `<recall>` → `<memo>` mechanism to the list-pet agent. When the LLM emits a `<recall>` tag, the runtime returns a previously user-uprated `<memo>` selected via embedding similarity. This mechanism supports contextual reuse of SQL examples and patterns, aiding accurate reasoning over local OLAP data.

---

## Flow Summary

- User uprates a message → stored as a `memo`
- LLM emits `<recall>...</recall>` → runtime computes query embedding
- Nearest `memo` is retrieved via cosine similarity over stored embeddings
- Returned as `<memo>...</memo>` to LLM
- LLM continues reasoning with the memo in context

---

## Memory Format (`<memo>`)

- XML block containing at least one of `<reasoning>`, `<sql>`, `<chart>`
- `<dataframe>` is excluded (runtime-generated and not durable)
- Example:

  <memo>
  <reasoning>Show recent sequencing runs with QC status and reportable calls</reasoning>
  <sql>SELECT ... FROM dim_sequencing_runs ...</sql>
  </memo>

---

## Trigger Format (`<recall>`)

- Free-form LLM query in natural language
- Example:

  <recall>examples of run-level QC summary queries</recall>

---

## Embedding

- Model: `text-embedding-3-small` (OpenAI)
- Generated at memory creation (on uprate)
- Deleted on memory removal (undo/downvote)
- Used fields for embedding similarity:
  - Default: User prompt + `<reasoning>` (if present)
  - Exclude: `<dataframe>` content
  - Include: `<sql>` block content — high weight

---

## Storage: DuckDB Schema

CREATE TABLE memo_store (
  id INTEGER PRIMARY KEY,
  content TEXT,                  -- full <memo> block
  embedding DOUBLE[],            -- 1536-dim vector
  created_at TIMESTAMP,
  source TEXT,                   -- 'uprated_by_user'
  user_message TEXT,             -- original prompt
  message_ids TEXT[]             -- optional traceability
);

---

## Memory Lifecycle

- `add_memo`: called when user uprates a message (may involve LLM summary if multi-message)
- `delete_memo`: called on downvote or undo
- `recall(query_str)`: returns top-matching memo from store
- Memory is team-shared (not user-isolated)

---

## Open Questions

- Should LLM generate the `<memo>` itself on uprate? Or runtime snapshot?
- Should multiple memos be returned for `<recall>`? (Default: top 1)
- Support for `time_decay` or usage-weighted ranking in recall?
- Visual memory manager in Streamlit?

---

## Implementation Plan (MVP)

1. Add `memo_store` table to DuckDB
2. Hook user uprate to `add_memo()`
3. Hook undo/downvote to `delete_memo()`
4. Add `recall(query)` function with brute-force cosine similarity
5. Handle `<recall>` → `<memo>` at runtime
6. Log which memo was returned for each `<recall>`
7. Optional: implement LLM-assisted `<memo>` summarization from message group
