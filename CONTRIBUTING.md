# Contributing

Issues and PRs welcome.

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

- Tests must not make live network calls; use `tests/fakes.py` or `httpx.MockTransport`.
- Runtime dependencies stay at `pydantic`, `httpx`, `tiktoken`.
- New routing thresholds go in `governor/policy.py` as a new named, versioned policy, not as edits
  to an existing one.
- When proposing a policy change, include numbers (tokens, cost, correctness).
