# ADR 0002: OpenXet CAS Integration, Authentication, and Token Scoping

## Status
Accepted (Go on OpenXet for v1)

## Context
UbuntuBio requires Content Addressable Storage (CAS) with chunk-level deduplication to support large biological sequence files (FASTQ, BAM, VCF, Assemblies) without duplicating millions of shared genetic sequences across iterations.

[OpenXet](https://github.com/ggoggam/openxet) (Apache-2.0, Rust) implements the Xet Protocol v1.0.0 wire specification using Hugging Face's official `xet-core` crates (`xet-core-structures`, `xet-data`). We evaluated:
1. **Protocol Compatibility**: Does OpenXet speak the exact `/v1` wire protocol expected by `hf_xet`?
2. **Authentication Hand-off**: Can our FastAPI backend act as the authoritative identity provider via OIDC/JWKS?
3. **Repository-Level Authorization**: How are access boundaries between Public, Gated, and Private datasets enforced?

## Evaluation Findings
1. **Wire Compatibility**:
   - OpenXet directly reuses Hugging Face's Gearhash CDC chunker and Blake3 keyed Merkle tree hashing.
   - The official `hf_xet` Python client connects cleanly to OpenXet instances via the `--endpoint` argument.
2. **Authentication Hand-off**:
   - OpenXet natively supports bearer token verification via `OPENXET_OIDC_ISSUERS`.
   - The UbuntuBio Hub exposes `/.well-known/jwks.json` and `/.well-known/openid-configuration` with RS256 public keys, allowing OpenXet to validate incoming requests with zero tight coupling to our database.
3. **Authorization & Repository Scoping**:
   - Because a CAS engine is fundamentally content-addressed (hashing chunks rather than tracking directory trees), the authoritative repository access boundary sits at the **UbuntuBio Hub API**:
     - **Pre-upload**: The client calls `POST /api/repos/{id}/preupload`. The hub verifies user permissions and returns an ephemeral (15-minute) CAS write token.
     - **Download**: The client requests file download or clone. The hub verifies Public, Gated DUA approval, or Private organization membership before issuing an ephemeral CAS read token.
     - **Data Invariant**: Untrusted parties cannot enumerate or deduce file hashes without hub authorization.
4. **Storage Layout**:
   - OpenXet's filesystem backend (`OPENXET_STORAGE_BACKEND=filesystem`) mounts cleanly under our single-folder architecture at `/srv/ubuntubio/data/xet/`.

## Decision
- **Proceed with OpenXet** as the primary storage and deduplication engine for UbuntuBio v1.
- **Maintain a pinned fork** (`github.com/ubuntubio/openxet`) to ensure dependency stability against unannounced `xet-core` crate releases.
- Authorize all data plane transfers using UbuntuBio-minted RS256 JWTs.

## Consequences
- Eliminates the need to construct a custom Rust CAS server from scratch, saving an estimated 8+ weeks of foundational engineering.
- The Python client library `ubuntu-bio` can leverage `hf_xet` under the hood for chunking, dedup, and resumable transfers.
