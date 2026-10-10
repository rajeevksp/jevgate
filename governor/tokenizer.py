"""Fixed tokenizer for budget accounting, independent of the app package so
the governor stays standalone (L1-01). Deliberately a separate cache from
app.services.chunking's own tiktoken encoder cache -- a small duplication
that keeps the two packages decoupled.
"""

from __future__ import annotations

from functools import lru_cache

import tiktoken


@lru_cache
def _tokenizer(name: str) -> tiktoken.Encoding:
    return tiktoken.get_encoding(name)


def count_tokens(text: str, tokenizer_name: str = "cl100k_base") -> int:
    return len(_tokenizer(tokenizer_name).encode(text))
