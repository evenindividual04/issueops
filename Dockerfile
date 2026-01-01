# Multi-stage build for minimal size
FROM python:3.12-slim as builder

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir --upgrade pip

# Install dependencies into a virtual environment
COPY requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# --- Final Stage ---
FROM python:3.12-slim

WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY . .

# Default entrypoint (can be overridden by action.yml)
ENTRYPOINT ["python", "main.py"]
