# Security Policy

The African Bioinformatics Data Hub takes the security and integrity of scientific data, research infrastructure, and user credentials seriously. We appreciate responsible disclosure of security vulnerabilities.

---

## Supported Versions

Only the latest active development versions receive security updates and patches.

| Component | Branch / Version | Supported |
|---|---|---|
| Server Hub (`/server`) | `main` | :white_check_mark: |
| Web Frontend (`/web`) | `main` | :white_check_mark: |
| Python Client (`afrihub`) | `>= 0.1.0` | :white_check_mark: |
| OpenXet CAS Service (`/xet`) | Pinned release | :white_check_mark: |

---

## Reporting a Vulnerability

**Please do NOT report security vulnerabilities through public GitHub issues.**

If you discover a vulnerability, misconfiguration, or security risk:
1. **Email security details** directly to:
   - **security@afrihub.org** *(or directly message the project lead / repository owner)*
2. Include the following details to help us investigate:
   - Type of issue (e.g., authorization bypass, credential exposure, path traversal, denial of service)
   - Step-by-step reproduction instructions or a minimal Proof of Concept (PoC)
   - Affected components (`server`, `web`, `client`, `xet`, or deployment configurations)
   - Impact assessment on datasets, user metadata, or cluster infrastructure

### Response Timelines & SLA
- **Initial acknowledgment:** Within 48 hours of receipt.
- **Triage & severity assessment:** Within 5 business days.
- **Fix & patch deployment:** 
  - *Critical / High severity:* Within 14 calendar days.
  - *Medium / Low severity:* Within 30 calendar days or next minor release.
- **Public disclosure:** Coordinated disclosure after the patch has been published and deployed.

---

## Scope & Critical Security Boundaries

When auditing or reviewing code for this repository, pay special attention to:

1. **Access Control Enforcement**:
   - Gated and Private datasets **MUST NEVER** generate presigned download URLs or CAS read tokens for unauthorized callers.
   - Access decisions must be centralized in the server's authorization module and covered by comprehensive test suites.
2. **CAS Token Scoping**:
   - Short-lived CAS tokens issued for OpenXet must be strictly scoped to specific repositories and revisions.
   - Tokens must have expiration limits (max 15 minutes).
3. **Audit Logging**:
   - All access to gated and controlled datasets must record immutable audit logs (user ORCID, timestamp, file ID, IP hash) to support scientific provenance and benefit-sharing accountability.
4. **Data Validation & Sanitization**:
   - Metadata cards (`README.md` YAML front-matter) and `samples.tsv` inputs must be strictly validated before parsing.
   - User-supplied markdown rendered on the web frontend must be sanitized against Cross-Site Scripting (XSS).
5. **Secrets & Credentials**:
   - Never commit tokens, private keys, database passwords, or S3 credentials to Git.
   - Pre-commit hooks (`detect-secrets`) and CI scanning are enforced.
