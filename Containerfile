# Containerfile for the FastAPI + HTMX school-lunch planner.
# Single user-mode image; runs as UID 1000; expects /app/.env and a
# writable /app mount for app.db (both bind-mounted at run time).

FROM docker.io/library/python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create a non-root user matching the typical rootless host UID (1000).
# The bind mount will pass through the host UID via --userns=keep-id, so
# file ownership matches the host user.
RUN groupadd -g 1000 app && useradd -u 1000 -g 1000 -d /app -s /bin/bash app

WORKDIR /app

# git is needed only to install pyskylight from GitHub at build time.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first so the layer caches across code changes.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the application code.
COPY fastapi_app.py school_menu.py skylight_menu.py /app/
COPY templates /app/templates
COPY static /app/static

# Give the non-root user ownership of the app directory so it can
# create app.db on first startup.
RUN chown -R app:app /app

USER app
EXPOSE 8000

# Container-internal default; the bind mount at /app/.env overrides this
# at run time.
CMD ["uvicorn", "fastapi_app:app", "--host", "0.0.0.0", "--port", "8000"]
