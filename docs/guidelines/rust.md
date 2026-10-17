# Rust Coding Standards

This guide outlines standards for Rust development, specifically governing our integration with and extensions to **OpenXet** (`/xet`), the CAS server, chunking engines, and high-performance data plane components.

---

## 1. Toolchain & Workspace Standards

- **Edition**: **Rust 2021** (or current stable).
- **Toolchain**: Latest stable `rustc` managed via `rustup`.
- **Formatting**: `cargo fmt --check`.
- **Linter**: `cargo clippy --all-targets --all-features -- -D warnings`.

### Crate-Level Lint Attributes
Include the following in `lib.rs` / `main.rs` for new crates:
```rust
#![deny(rust_2018_idioms)]
#![deny(missing_debug_implementations)]
#![deny(unreachable_pub)]
#![warn(clippy::all)]
#![warn(clippy::pedantic)]
#![allow(clippy::module_name_repetitions)]
```

---

## 2. Error Handling: `thiserror` vs. `anyhow`

### Libraries & Core Crates (`cas_types`, protocol modules)
- Use **[`thiserror`](https://docs.rs/thiserror/)** to define strongly typed, exhaustive error enums.
- Avoid exposing internal error types across public interfaces; wrap or map them explicitly:

```rust
use thiserror::Error;

#[derive(Error, Debug)]
pub enum CasError {
    #[error("Chunk not found in CAS: {hash}")]
    ChunkNotFound { hash: String },

    #[error("Corrupt xorb header: expected magic bytes {expected:?}, found {found:?}")]
    CorruptHeader { expected: [u8; 4], found: [u8; 4] },

    #[error("Authentication failed: {0}")]
    AuthFailed(String),

    #[error("IO failure while reading chunk: {0}")]
    Io(#[from] std::io::Error),
}
```

### Server Binaries & CLI Entrypoints
- Use **[`anyhow`](https://docs.rs/anyhow/)** with descriptive `.context()` calls to annotate failure points:

```rust
use anyhow::{Context, Result};

pub async fn load_xorb_archive(path: &Path) -> Result<XorbArchive> {
    let file = tokio::fs::File::open(path)
        .await
        .with_context(|| format!("Failed to open xorb archive at {:?}", path))?;
    ...
}
```

### Prohibited Patterns
- **No ungrounded `unwrap()` or `expect()`**: Never call `.unwrap()` in production paths. If an invariant makes a panic mathematically impossible, document it explicitly:
  ```rust
  // SAFETY: String is guaranteed non-empty by prior regex match
  let first_char = input.chars().next().expect("invariant: non-empty input");
  ```

---

## 3. Memory Safety & Unsafe Guidelines

- **Minimize `unsafe`**: Code must be 100% safe Rust whenever possible.
- **Mandatory `// SAFETY:` Comments**: Every single `unsafe` block must be immediately preceded by a `// SAFETY:` comment proving why the operation cannot trigger undefined behavior (UB):
  ```rust
  // SAFETY: The pointer is valid, non-null, aligned, and the slice length
  // does not exceed the remaining buffer capacity verified on line 42.
  let slice = unsafe { std::slice::from_raw_parts(ptr, len) };
  ```
- **Bound Checking**: Never bypass slice bounds checking (`get_unchecked`) unless profiling in release mode proves it to be an active bottleneck, and full safety proofs are documented.

---

## 4. Async Execution & Axum Patterns

### Avoid Blocking the Tokio Reactor
- Heavy CPU operations (e.g., Blake3 hashing of multi-gigabyte buffers or Gearhash chunk calculation) must **never** run directly on Tokio async worker threads.
- Offload CPU-bound computation or synchronous file operations to `tokio::task::spawn_blocking`:

```rust
use tokio::task;

pub async fn hash_large_buffer(data: Vec<u8>) -> Result<blake3::Hash, CasError> {
    task::spawn_blocking(move || {
        blake3::hash(&data)
    })
    .await
    .map_err(|e| CasError::Execution(e.to_string()))
}
```

### Streaming Over Full-Buffering
- Never load multi-gigabyte FASTQ/BAM uploads entirely into memory (`Vec<u8>`).
- Stream incoming bytes using `tokio::io::AsyncRead` / `futures_util::Stream` into fixed chunk buffers (64 KiB target for Gearhash CDC).

---

## 5. Content Addressable Storage (CAS) Invariants

When working with OpenXet data structures:
1. **Blake3 Keyed Hashing**: Every chunk and xorb identity must use Blake3 keyed hashing matching the official `xet-core` specification.
2. **Byte-Level Verification**: When reconstructing files, the total byte count and reconstructed Merkle root must match the registered shard metadata. Mismatches must immediately abort and return a data corruption error.
3. **Atomic Writes**: Writing shards or xorbs to the filesystem must write to a temporary file (`.tmp.xxx`) and rename atomically (`std::fs::rename`) to prevent partial writes from corrupting the index during sudden host shutdowns.

---

## 6. Testing Rust Code

- **Unit Tests**: Co-located in the same file using `#[cfg(test)] mod tests { ... }`.
- **Integration Tests**: Placed under `tests/` testing the public API and wire protocol.
- **Client Compatibility Tests**: Run the `hf-xet-client` test suite against the built server in CI to guarantee that Hugging Face's official client does not encounter protocol regressions.
