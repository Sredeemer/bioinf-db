FROM python:3.12-slim

# Install system dependencies (git, build tools, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    git-lfs \
    libgit2-dev \
    pkg-config \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Copy dependency specifications
COPY pyproject.toml README.md ./

# Install dependencies using uv
RUN uv sync --frozen --no-dev || uv sync --no-dev

# Copy application source
COPY src/ src/

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "ubuntubio.main:app", "--host", "0.0.0.0", "--port", "8000"]
