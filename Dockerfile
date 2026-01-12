# Multi-stage build for X-Ray API server
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN pip install --no-cache-dir hatchling

# Copy only files needed for building
COPY pyproject.toml README.md ./
COPY shared/ ./shared/
COPY sdk/ ./sdk/
COPY api/ ./api/

# Build the wheel
RUN pip wheel --no-deps --wheel-dir /wheels .

# Production stage
FROM python:3.12-slim

WORKDIR /app

# Install the wheel and API dependencies
COPY --from=builder /wheels/*.whl /tmp/
RUN WHEEL=$(ls /tmp/xray-*.whl) && pip install --no-cache-dir "${WHEEL}[api]" && rm /tmp/xray-*.whl

# Create non-root user
RUN useradd --create-home --shell /bin/bash xray
USER xray

# Expose port
EXPOSE 8000

# Run uvicorn
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
