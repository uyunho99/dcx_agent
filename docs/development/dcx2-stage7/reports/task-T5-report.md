# T5 report — complete

Implemented design 4.1 / AC-06 in:
- `backend/app/evidence/queries.py`
- `backend/app/evidence/prompts/queries.v1.md`
- `backend/tests/evidence/test_queries.py`

## Behavior

`PersonaQueryOut`, `validate_queries`, `QueryResult`, and `generate_queries` follow the brief's public interface. Generation uses `LLMTask(task='evidence.queries')`, the Pydantic output schema, and injected/default `registry.run_task`, checking `result.ok`.

The Korean prompt receives oneLiner as its first input line, Persona name/Desire/Goal/Artifact keywords, and Context rows in the required format. Context and Artifact keywords pass through `filter_words(words, bk)`, with bk read from the session's projectContext. Inputs are not mutated.

Validation checks exact anchor union, Context membership, exactly eight nonempty dimension keys, the shared forbidden regex, and the Persona two-desire/one-artifact sentence contract. A failed first result triggers one regeneration with every violation listed in the instructions. Failed backend/schema results also receive at most one corrective task invocation.

After the second failure, affected Contexts receive all eight fallback rows using `Context name + first three filtered keywords`, with origin `fallback`. Valid Context rows remain usable. Missing anchors affect their corresponding Context; unusable responses, unknown IDs, or invalid Persona output affect all Contexts. If fewer than three valid keywords exist, the fallback uses those available without adding stopwords. Successful first-attempt rows use `llm`; successful second-attempt rows use `regen`.

## Persistence and downstream integration

As specified by the function contract, generation returns rows rather than opening an EvidenceStore for an implicit active version. The caller writes rows into its chosen version/run and records `query_gen_fail` for the IDs in `QueryResult.failed`. This avoids writing into the wrong version during concurrent work.

Persona row dimensions are `desire_check_1`, `desire_check_2`, and `artifact`. Distinct desire dimensions preserve both sentences under the existing `(owner, dim)` primary key. The persistence test saves and reads all three Persona rows and eight rows per Context through the committed EvidenceStore.

## TDD and validation

1. Created tests first and ran `backend/.venv/bin/python -m pytest backend/tests/evidence/test_queries.py -q`: expected RED, `ModuleNotFoundError: app.evidence.queries`.
2. Implemented generation and prompt: GREEN, 23 passed.
3. Refactored forbidden matching to a compiled shared regex and added boundary coverage for missing anchors and short keyword lists (26 T5 cases total).
4. Ran the requested full command exactly once: `backend/.venv/bin/python -m pytest backend/tests/evidence -q`: **110 passed, 2 warnings in 7.62s**.
5. `git diff --check` reported no tracked whitespace errors.

No network credentials were needed. No git add or commit was performed. Other workers' candidates and rerank files were not modified.

## Concerns

No blocking concerns. Existing warnings concern Pydantic class-based config deprecation and joblib physical-core detection. The future pipeline must persist the returned rows and map `failed` to `query_gen_fail`; that remains T11's responsibility. `calls` counts run_task invocations; the existing registry may independently retry provider parse/schema failures internally.
