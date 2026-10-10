"""Evidence Governor: a pure library, no FastAPI dependency.

Contracts, validation, the Jev client, policy routing, reranking and budget
assembly land here Kept import-clean from day one so the
"library and API give identical decisions" requirement (L1-11) is checkable
by construction: this package must never import fastapi or starlette.
"""

__version__ = "0.1.0"
