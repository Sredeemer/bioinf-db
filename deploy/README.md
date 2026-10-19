# UbuntuBio Deployment Configuration (`/deploy`)

This directory contains the production and local development Docker Compose stack for UbuntuBio.

## Single-Folder Storage Invariant
In accordance with our architectural rules, all persistent runtime data is strictly isolated within a single root folder:
```text
/srv/ubuntubio/data/
├── ubuntubio.db  # SQLite database (relational tables, user sessions, FTS5 BM25 search)
├── xet/          # OpenXet CAS content-addressable storage (xorbs, shards)
├── git/          # Bare Git repositories (<owner>/<repo>.git)
└── tmp/          # Staging directory for multipart LFS ingestion
```

## Quick Start (Local Development)

```bash
# 1. Create the local data directory if not running under /srv
mkdir -p .data/xet .data/git .data/tmp

# 2. Copy sample environment file
cp .env.example .env

# 3. Start core infrastructure
docker compose -f compose.yaml up -d server openxet
```
