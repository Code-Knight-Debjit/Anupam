# Anupam Bearings — Premium Industrial Website + RAG Chatbot

Full-stack Django website for Anupam Bearings (certified Timken parts supplier) with a production-ready RAG AI chatbot powered by FAISS + sentence-transformers + Ollama + Celery.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 5.x |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Frontend | Django Templates + Custom CSS + GSAP |
| Task Queue | Celery + Redis |
| RAG Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Vector Store | FAISS (local, CPU) |
| LLM | Ollama (llama3 / mistral / any local model) |
| Cache | Redis (1-hour TTL for repeated queries) |
| Email | Resend API |

---

## Project Structure

```
anupam_bearings/
├── anupam_bearings/        # Django project config
│   ├── settings.py         # Celery + Redis + RAG config
│   ├── celery.py           # Celery app
│   └── __init__.py
├── rag/                    # RAG pipeline
│   ├── embeddings.py       # sentence-transformers (lru_cache singleton)
│   ├── retriever.py        # FAISS: create/load/save/search/add_documents
│   ├── prompt_builder.py   # System + context + history + query
│   ├── llm_client.py       # Ollama HTTP (semaphore 4, retry x2, timeout 45s)
│   └── chunker.py          # 400-token chunks, .txt/.pdf/.json loaders
├── chatbot/
│   ├── views.py            # /api/chat/ sync + async + health + stats
│   ├── tasks.py            # Celery: run_rag_pipeline, ingest_documents_task
│   └── management/commands/ingest_rag_data.py
├── dashboard/              # Custom branded admin
│   └── templates/dashboard/rag_status.html   # RAG management UI
├── data/
│   ├── knowledge_base/     # 4 JSON files, 38 documents
│   └── faiss_index/        # Auto-generated FAISS binary
├── docker-compose.yml      # Full production stack
├── Dockerfile
└── nginx.conf
```

---

## Quick Start (Development)

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env   # edit with your values

# 3. Database
python manage.py migrate
python manage.py seed_data
python manage.py createsuperuser

# 4. Start Redis
redis-server
# or: docker run -d -p 6379:6379 redis:alpine

# 5. Start Ollama
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3
ollama serve

# 6. Build RAG index
python manage.py ingest_rag_data --also-seed-products

# 7. Start Celery
celery -A anupam_bearings worker --loglevel=info --concurrency=4

# 8. Run
python manage.py runserver
```

- Website: http://localhost:8000
- Dashboard: http://localhost:8000/dashboard/ (admin / admin123)
- RAG Page: http://localhost:8000/dashboard/rag/
- Health: http://localhost:8000/api/chat/health/

---

## Production (Docker)

```bash
cp .env.example .env  # set SECRET_KEY, DB_PASSWORD

docker compose up -d

docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_data
docker compose exec web python manage.py createsuperuser
docker compose exec ollama ollama pull llama3
docker compose exec web python manage.py ingest_rag_data --also-seed-products

curl http://localhost/api/chat/health/
```

---

## VPS + Cloudflare Deployment

This project can run on a VPS behind Cloudflare using the existing Docker stack and nginx reverse proxy.

### 1. Provision the VPS

- Use Ubuntu 22.04 or 24.04.
- Install Docker and Docker Compose.
- Clone the repository to the server.

### 2. Configure environment variables

Create `.env` from `.env.example` and set production values:

```bash
DEBUG=False
ALLOWED_HOSTS=anupambearings.com,www.anupambearings.com
CSRF_TRUSTED_ORIGINS=https://anupambearings.com,https://www.anupambearings.com
USE_X_FORWARDED_HOST=True
SECRET_KEY=your-production-secret
DB_PASSWORD=your-strong-database-password
```

If you use a single domain, keep only that host in `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`.

### 3. Point Cloudflare at the VPS

- Add an `A` record for your domain to the VPS public IP.
- Turn on the Cloudflare proxy so the record is orange-clouded.
- Set SSL/TLS mode to `Full (strict)`.
- Prefer a Cloudflare Origin Certificate or another valid certificate on the VPS.

### 4. Start the stack

```bash
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py seed_data
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py collectstatic --noinput
```

If you want one of the Cloudflare-specific modes, use a compose profile:

```bash
docker compose -f docker-compose.yml -f docker-compose.cloudflare.yml --profile cloudflare-tunnel up -d
docker compose -f docker-compose.yml -f docker-compose.cloudflare.yml --profile cloudflare-origin up -d
```

### 5. Check the site

- Visit `https://anupambearings.com`
- Verify `/about/`, `/products/`, and `/contact/`
- Confirm the admin dashboard works behind HTTPS

### 6. Optional hardening

- Restrict firewall access on ports 80 and 443 to Cloudflare IP ranges.
- Enable HSTS after confirming HTTPS works end to end.
- Keep `DEBUG=False` in production.

### Option A: Cloudflare Tunnel

Use a tunnel if you do not want to expose ports 80/443 on the VPS.

1. Install `cloudflared` on the VPS.
2. Create a tunnel in the Cloudflare dashboard.
3. Save the tunnel credentials under `deploy/cloudflared/creds/`.
4. Update `deploy/cloudflared/config.yml` with the tunnel UUID and hostname.
5. Use `deploy/cloudflared/run-tunnel.sh` as the container command.
6. Route your hostname to the internal nginx service.

Example tunnel config: [deploy/cloudflared-config.yml.example](deploy/cloudflared-config.yml.example)

Compose service: `cloudflared` in [docker-compose.yml](docker-compose.yml)
Compose override: [docker-compose.cloudflare.yml](docker-compose.cloudflare.yml)

Suggested origin target:

```bash
http://nginx:80
```

### Option B: Full HTTPS on the origin

Use this if you want nginx to terminate TLS with a Cloudflare Origin Certificate.

1. Generate an Origin Certificate in Cloudflare.
2. Place the cert and key at `deploy/certs/origin.pem` and `deploy/certs/origin.key`.
3. Use `listen 443 ssl http2` in nginx.
4. Set Cloudflare SSL/TLS mode to `Full (strict)`.
5. Use [deploy/nginx-origin-https.conf](deploy/nginx-origin-https.conf) with the origin cert mounts.

Example nginx config: [deploy/nginx-origin-https.conf.example](deploy/nginx-origin-https.conf.example)

Production nginx config used by compose: [deploy/nginx-origin-https.conf](deploy/nginx-origin-https.conf)

Recommended proxy headers:

```nginx
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Proto https;
```

---

## Adding Data to RAG

```bash
# Append a new JSON file (no rebuild needed)
python manage.py ingest_rag_data --file data/knowledge_base/new_file.json

# Rebuild everything from scratch
python manage.py ingest_rag_data --rebuild --also-seed-products

# Check index stats
python manage.py ingest_rag_data --stats
```

JSON document format:
```json
{
  "title": "Document Title",
  "content": "Full text content...",
  "metadata": {"source": "catalogue", "tags": ["product", "bearing"]}
}
```

---

## Swap LLM Model

```bash
# In .env:
OLLAMA_MODEL=mistral   # or llama3.2, gemma2, phi3, qwen2.5

ollama pull mistral
# Restart Django/Celery - no code changes needed
```

---

## API Endpoints

```
POST /api/chat/                    # Sync RAG chat (frontend uses this)
POST /api/chat/async/              # Async - returns task_id immediately
GET  /api/chat/result/<task_id>/   # Poll for async result
GET  /api/chat/health/             # FAISS + Ollama + Redis health
GET  /api/chat/stats/              # Index statistics
```

---

## Environment Variables

```bash
SECRET_KEY=...
DEBUG=False
REDIS_URL=redis://localhost:6379/0
OLLAMA_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=llama3
OLLAMA_MAX_CONCURRENT=4
OLLAMA_TIMEOUT=45
RAG_TOP_K=5
RAG_SCORE_THRESHOLD=0.22
EMBEDDING_MODEL=all-MiniLM-L6-v2
RESEND_API_KEY=...
```

---

## Dashboard: http://localhost:8000/dashboard/
Username: `admin` | Password: `admin123` (change before production)
