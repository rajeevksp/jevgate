# Security Policy

JevGate is an early-stage Python library for evaluating and selecting evidence in RAG pipelines. It is not a security boundary for the applications that integrate it.

## Reporting a Vulnerability

Please do not disclose exploitable vulnerabilities or sensitive details in a public issue.

If GitHub private vulnerability reporting is enabled for this repository, use **Security → Report a vulnerability**. Otherwise, open an issue requesting a private reporting channel without including exploit details.

Reports are handled on a best-effort basis. No response time or security-fix SLA is guaranteed.

## Security Considerations

### External data transmission

Live evaluation sends eligible queries and passage data to OpenRouter's Jev Decisions API. Before enabling live evaluation, confirm that your data-handling requirements permit this transmission.

Use `allow_external_transmission=True` only when this external processing is intentional. This opt-in is a library-level safeguard, not a compliance guarantee. Review the applicable provider terms and data-handling policies.

### Evidence is not authorization

JevGate evaluates retrieved passages; it does not replace application-level access control.

Enforce document permissions, tenant isolation, and authorization before passing retrieved content to JevGate. Do not use its relevance judgments or routing decisions as proof that a user is authorized to access a document.

### Prompt injection and untrusted content

Retrieved passages must be treated as untrusted input. JevGate's prompt-injection score is a detection signal, not a guarantee that malicious content will be identified or removed.

Keep appropriate prompt-injection mitigations and output validation in the downstream application. Do not rely on JevGate alone to protect tools, credentials, or privileged operations.

### Credentials and operational limits

- Keep OpenRouter API keys in environment variables or an appropriate secrets manager. Never commit credentials to the repository or include them in logs or bug reports.
- Apply appropriate timeouts, concurrency limits, and candidate-count limits in your application. Review the implementation's documented limitations before using it in production.
- Keep dependencies updated and review changes before deploying new versions.

## Scope

This policy covers security issues in JevGate's code, including its input validation, external API handling, credential handling, evidence-routing behavior, and failure handling.

Issues involving OpenRouter or the underlying Jev model should also be reported to the relevant provider where appropriate.

JevGate is provided under the Apache-2.0 license. No guarantee of security or fitness for a particular deployment is implied.