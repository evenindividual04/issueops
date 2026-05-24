# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.x     | ✅ Active          |
| < 1.0   | ❌ End of life     |

## Reporting a Vulnerability

**Do not open public GitHub issues for security vulnerabilities.**

If you discover a security issue in IssueOps, please report it privately:

1. **Preferred:** Open a [GitHub Security Advisory](https://github.com/evenindividual04/issueops/security/advisories/new) on this repository.
2. **Alternative:** Email `anmol@issueops.dev` with the subject line `[SECURITY] <short description>`.

Please include:
- A description of the vulnerability and its impact.
- Steps to reproduce (minimal proof-of-concept preferred).
- Affected version(s).
- Any suggested mitigation.

## Response Timeline

| Stage                 | Target              |
|-----------------------|---------------------|
| Acknowledgement       | Within 48 hours     |
| Initial assessment    | Within 5 business days |
| Fix or mitigation plan| Within 14 days for High/Critical |
| Public disclosure     | After fix is released, coordinated with reporter |

## Scope

In scope:
- The `issueops` CLI and Action entrypoint.
- All services under `app/services/`.
- Configuration parsing and rules evaluation.
- Cache and audit log handling.

Out of scope:
- Vulnerabilities in upstream dependencies (report to those projects directly; we will track via Dependabot).
- Social engineering or physical attacks.
- Denial of service against GitHub or Gemini APIs.

## Secret Handling

IssueOps consumes two secrets:
- `GEMINI_API_KEY` — required, must be passed via GitHub Actions secrets.
- `GITHUB_TOKEN` — provided automatically by GitHub Actions; never hardcode.

If you suspect a key was exposed:
1. Rotate the key immediately via the Google AI Studio or GitHub settings.
2. Audit the repository's Action logs for unauthorized usage.
3. Open a security advisory if the exposure resulted from a defect in IssueOps.

## Credits

We thank the security researchers who help keep IssueOps safe. Reporters will be credited in release notes unless they request anonymity.
