# ──────────────────────────────────────────────
# Stage 1 – Builder
# ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Create virtualenv
RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Preload embedding model
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# ──────────────────────────────────────────────
# Stage 2 – Runtime
# ──────────────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
libpq5 \
libjpeg62-turbo \
libgomp1 \
&& rm -rf /var/lib/apt/lists/*

# Copy venv
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

# Copy project
COPY . .

# Create required directories
RUN mkdir -p \
data/faiss_index \
data/knowledge_base \
staticfiles \
media/products \
media/categories

# Ensure database tables exist so we can create the admin user in-image
# WARNING: This requires the DB to be reachable during build (works for in-image SQLite).
RUN python manage.py migrate --noinput || true


# 🔥 CLEAN STATIC BUILD
RUN rm -rf staticfiles/* && \
    python manage.py collectstatic --noinput

# Create non-root user
RUN useradd -m -u 1000 appuser && \
chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# 🚀 Runtime: makemigrations + migrate + start server
CMD ["sh", "-c", "\
python manage.py makemigrations --noinput && \
python manage.py migrate --noinput && \
python manage.py seed_data && \
gunicorn anupam_bearings.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 3 \
  --timeout 120"]