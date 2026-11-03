FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 RETENTIONOPS_ROOT=/workspace
WORKDIR /app
COPY requirements.lock ./
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-deps --no-build-isolation . \
    && useradd --create-home --uid 10001 appuser \
    && mkdir /workspace && chown appuser:appuser /workspace
USER appuser
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "retentionops.api:app", "--host", "0.0.0.0", "--port", "8000"]
