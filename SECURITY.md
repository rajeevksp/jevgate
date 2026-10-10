# Security policy

JevGate is a small, early-stage open-source project. Only the latest commit on `master` is maintained.

## Reporting a vulnerability

Please do not open a public issue with exploit details. Use GitHub's private reporting: on the repository's
**Security** tab choose **Report a vulnerability**. If that option is not available, open a public issue
that asks for a private contact channel and contains no technical details.

Reports are handled on a best-effort basis; no response time is promised.

## Scope and known limits

- Live evaluation sends the query and passage text to OpenRouter's Jev Decisions endpoint. Treat that as
  a data-sharing decision; see "Limitations, security and privacy" in the README.
- `contains_prompt_injection` is a model-derived risk signal, not a complete defence against prompt injection.
- Never commit API keys. Keys are read from `OPENROUTER_API_KEY` or passed to `JevClient` by your code.
