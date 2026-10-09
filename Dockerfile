# Multi-stage build for minimal final image
FROM --platform=$TARGETPLATFORM ghcr.io/astral-sh/uv:latest AS uv

FROM --platform=$TARGETPLATFORM python:3.11-slim AS builder

# Install uv for faster dependency management
COPY --from=uv /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Version is derived from git via hatch-vcs at build time, but the .git
# directory is not in the Docker build context. The CI workflow builds a
# wheel locally to compute the version and passes it through as a build-arg.
ARG PKG_VERSION=0.0.0+docker
ENV SETUPTOOLS_SCM_PRETEND_VERSION=$PKG_VERSION

# Copy dependency files and README (needed for package metadata)
COPY pyproject.toml uv.lock* README.md ./

# Copy source code (needed for building the package)
COPY src/ ./src/

# Install dependencies into a virtual environment
RUN uv sync --frozen --no-dev

# Final stage - minimal runtime image
FROM --platform=$TARGETPLATFORM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY src/ ./src/
COPY pyproject.toml ./

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Health check uses the stdlib liveness probe; its default timeout is 2 seconds.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -m intervals_icu_mcp.healthcheck

# Run the MCP server
ENTRYPOINT ["python", "-m", "intervals_icu_mcp.server"]
