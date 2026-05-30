"""
rag/llm_client.py
─────────────────
LLM backend with three options (set LLM_BACKEND in .env):
  - groq    → Groq API (llama3, free, 1–3s) ← RECOMMENDED for speed
  - ollama  → Local Ollama (free, 60–180s on CPU, 3–8s on GPU)
  - openai  → OpenAI-compatible endpoint (paid, very fast)

Default: groq (fastest free option)
"""

import os, time, logging, threading, requests
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
MAX_CONCURRENT = int(os.getenv('OLLAMA_MAX_CONCURRENT', '4'))
_semaphore     = threading.Semaphore(MAX_CONCURRENT)

LLM_BACKEND    = os.getenv('LLM_BACKEND', 'groq').lower()
LLM_TIMEOUT    = int(os.getenv('LLM_TIMEOUT', '30'))   # 30s covers all backends
MAX_RETRIES    = int(os.getenv('LLM_MAX_RETRIES', '2'))
RETRY_DELAY    = float(os.getenv('LLM_RETRY_DELAY', '1.0'))

# ── Groq ──────────────────────────────────────────────────────────────────────
GROQ_API_KEY   = os.getenv('GROQ_API_KEY', '')
GROQ_MODEL     = os.getenv('GROQ_MODEL', 'llama3-8b-8192')
GROQ_URL       = 'https://api.groq.com/openai/v1/chat/completions'

# ── Ollama ────────────────────────────────────────────────────────────────────
OLLAMA_URL_CFG = os.getenv('OLLAMA_URL', 'http://localhost:11434/api/generate')
OLLAMA_MODEL   = os.getenv('OLLAMA_MODEL', 'gemma2:2b')  # default to small fast model


def _get_settings():
    try:
        from django.conf import settings
        return {
            'backend':     getattr(settings, 'LLM_BACKEND',   LLM_BACKEND),
            'groq_key':    getattr(settings, 'GROQ_API_KEY',  GROQ_API_KEY),
            'groq_model':  getattr(settings, 'GROQ_MODEL',    GROQ_MODEL),
            'ollama_url':  getattr(settings, 'OLLAMA_URL',    OLLAMA_URL_CFG),
            'ollama_model':getattr(settings, 'OLLAMA_MODEL',  OLLAMA_MODEL),
            'timeout':     getattr(settings, 'LLM_TIMEOUT',   LLM_TIMEOUT),
        }
    except Exception:
        return {
            'backend': LLM_BACKEND, 'groq_key': GROQ_API_KEY,
            'groq_model': GROQ_MODEL, 'ollama_url': OLLAMA_URL_CFG,
            'ollama_model': OLLAMA_MODEL, 'timeout': LLM_TIMEOUT,
        }


# ── PUBLIC INTERFACE ──────────────────────────────────────────────────────────

def call_llm(
    prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 512,
    model_override: Optional[str] = None,
) -> str:
    cfg = _get_settings()

    acquired = _semaphore.acquire(timeout=cfg['timeout'])
    if not acquired:
        return _fallback('concurrency_timeout')
    try:
        backend = cfg['backend']
        if backend == 'groq':
            return _call_groq(prompt, temperature, max_tokens, cfg, model_override)
        elif backend == 'ollama':
            return _call_ollama(prompt, temperature, max_tokens, cfg, model_override)
        else:
            logger.error(f"Unknown LLM_BACKEND: {backend}. Use 'groq' or 'ollama'.")
            return _fallback('unknown_backend')
    finally:
        _semaphore.release()


# ── GROQ BACKEND (1–3 seconds, free) ─────────────────────────────────────────

def _call_groq(prompt, temperature, max_tokens, cfg, model_override):
    api_key = cfg['groq_key']
    if not api_key:
        logger.error("GROQ_API_KEY not set. Get one free at console.groq.com")
        # Fall back to Ollama if key missing
        logger.warning("Falling back to Ollama since GROQ_API_KEY is missing.")
        return _call_ollama(prompt, temperature, max_tokens, cfg, model_override)

    model   = model_override or cfg['groq_model']
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type':  'application/json',
    }
    payload = {
        'model': model,
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens':  max_tokens,
        'temperature': temperature,
        'stream':      False,
    }

    for attempt in range(MAX_RETRIES + 1):
        try:
            if attempt > 0:
                time.sleep(RETRY_DELAY * attempt)
            r = requests.post(GROQ_URL, headers=headers, json=payload, timeout=cfg['timeout'])
            if r.status_code == 200:
                text = r.json()['choices'][0]['message']['content'].strip()
                logger.info(f"Groq response OK ({len(text)} chars, model={model})")
                return text
            elif r.status_code == 429:
                logger.warning("Groq rate limit hit — retrying")
                time.sleep(2 * (attempt + 1))
            elif r.status_code == 401:
                logger.error("Groq API key invalid")
                return _fallback('auth_error')
            else:
                logger.warning(f"Groq HTTP {r.status_code}: {r.text[:200]}")
        except requests.exceptions.Timeout:
            logger.warning(f"Groq timeout (attempt {attempt+1})")
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Groq connection error: {e}")

    return _fallback('groq_failed')


# ── OLLAMA BACKEND (local, slower on CPU) ─────────────────────────────────────

def _call_ollama(prompt, temperature, max_tokens, cfg, model_override):
    url   = cfg['ollama_url']
    model = model_override or cfg['ollama_model']

    payload = {
        'model':  model,
        'prompt': prompt,
        'stream': False,
        'options': {
            'temperature': temperature,
            'num_predict': max_tokens,
            'stop':        ['User:', 'User Question:'],
        },
    }

    for attempt in range(MAX_RETRIES + 1):
        try:
            if attempt > 0:
                time.sleep(RETRY_DELAY * attempt)
            r = requests.post(url, json=payload, timeout=cfg['timeout'])
            if r.status_code == 200:
                text = r.json().get('response', '').strip()
                if text:
                    return text
                return _fallback('empty_response')
            elif r.status_code == 404:
                logger.error(f"Ollama model '{model}' not found. Run: ollama pull {model}")
                return _fallback('model_not_found', model)
        except requests.exceptions.ConnectionError:
            logger.warning(f"Ollama offline (attempt {attempt+1})")
        except requests.exceptions.Timeout:
            logger.warning(f"Ollama timeout after {cfg['timeout']}s (attempt {attempt+1})")

    return _fallback('connection_error')


# ── FALLBACK MESSAGES ─────────────────────────────────────────────────────────

def _fallback(reason: str, detail: str = '') -> str:
    base = 'Please contact us at info@anupambearings.com or call +91-98844-00741.'
    messages = {
        'connection_error':    f'Our AI assistant is temporarily offline. {base}',
        'groq_failed':         f'Our AI service is temporarily unavailable. {base}',
        'auth_error':          f'AI configuration error. {base}',
        'concurrency_timeout': f'Our AI assistant is busy right now. Please try again in a moment.',
        'empty_response':      f'I received an empty response. {base}',
        'model_not_found':     f"AI model '{detail}' is not available. {base}",
        'unknown_backend':     f'AI configuration error. {base}',
    }
    return messages.get(reason, f'I encountered an error. {base}')


# ── HEALTH CHECK ──────────────────────────────────────────────────────────────

def check_ollama_health() -> dict:
    """Health check — works for both Groq and Ollama."""
    cfg = _get_settings()

    if cfg['backend'] == 'groq':
        if not cfg['groq_key']:
            return {'healthy': False, 'model': cfg['groq_model'],
                    'backend': 'groq', 'error': 'GROQ_API_KEY not set'}
        try:
            r = requests.get(
                'https://api.groq.com/openai/v1/models',
                headers={'Authorization': f'Bearer {cfg["groq_key"]}'},
                timeout=5,
            )
            if r.status_code == 200:
                models = [m['id'] for m in r.json().get('data', [])]
                return {
                    'healthy': True, 'backend': 'groq',
                    'model': cfg['groq_model'],
                    'model_available': cfg['groq_model'] in models,
                    'available_models': [m for m in models if 'llama' in m or 'gemma' in m or 'mixtral' in m],
                    'error': None,
                }
            return {'healthy': False, 'backend': 'groq', 'model': cfg['groq_model'],
                    'error': f'HTTP {r.status_code}'}
        except Exception as e:
            return {'healthy': False, 'backend': 'groq', 'model': cfg['groq_model'], 'error': str(e)}

    else:  # ollama
        base = cfg['ollama_url'].rsplit('/api/', 1)[0]
        try:
            r = requests.get(f'{base}/api/tags', timeout=5)
            if r.status_code == 200:
                models = [m['name'] for m in r.json().get('models', [])]
                return {
                    'healthy': True, 'backend': 'ollama',
                    'model': cfg['ollama_model'],
                    'model_available': any(cfg['ollama_model'] in m for m in models),
                    'available_models': models,
                    'error': None,
                }
            return {'healthy': False, 'backend': 'ollama', 'model': cfg['ollama_model'],
                    'error': f'HTTP {r.status_code}'}
        except Exception as e:
            return {'healthy': False, 'backend': 'ollama', 'model': cfg['ollama_model'], 'error': str(e)}
