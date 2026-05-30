"""
chatbot/views.py  — RAG chat with smart sync/async fallback + rate limiting + validation
"""
import json, uuid, logging
from django.http       import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.conf       import settings
from django.core.cache import cache

from core.validators import validate_chat
from contact.models  import ChatMessage

logger = logging.getLogger(__name__)


def _get_or_create_session(request):
    sid = request.session.get('chat_session_id')
    if not sid:
        sid = str(uuid.uuid4())
        request.session['chat_session_id'] = sid
    return sid


def _check_rate_limit(request, limit=20, window=60):
    ip  = (request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
           or request.META.get('REMOTE_ADDR', 'unknown'))
    key = f'chat_rl:{ip}'
    try:
        count = cache.get(key, 0)
        if count >= limit:
            return True
        cache.set(key, count + 1, timeout=window)
    except Exception:
        pass  # if Redis is down, don't block the user
    return False


def _run_rag_direct(query, history, session_id):
    """
    Run RAG pipeline directly (synchronous, no Celery).
    Used as fallback when Celery/Redis is unavailable.
    """
    from rag.retriever   import retrieve, index_exists
    from rag.prompt_builder import build_prompt, build_simple_prompt
    from rag.llm_client  import call_llm

    try:
        if index_exists():
            retrieved = retrieve(query, top_k=5, score_threshold=0.22)
            prompt    = build_prompt(query, retrieved, history)
        else:
            retrieved = []
            prompt    = build_simple_prompt(query, history)
    except Exception as e:
        logger.warning(f'Retrieval failed, using simple prompt: {e}')
        retrieved = []
        prompt    = build_simple_prompt(query, history)

    reply = call_llm(prompt, temperature=0.3, max_tokens=512)

    # Persist to DB
    try:
        ChatMessage.objects.create(session_id=session_id, role='user',      content=query)
        ChatMessage.objects.create(session_id=session_id, role='assistant', content=reply)
    except Exception:
        pass

    return {
        'reply':        reply,
        'sources':      [{'source': c.get('metadata',{}).get('source','kb'), 'score': round(c.get('score',0),3)} for c in retrieved],
        'cached':       False,
        'chunks_found': len(retrieved),
    }


# ── SYNC endpoint  (backward-compatible — this is what the frontend uses) ────

@csrf_exempt
@require_POST
def chat(request):
    """
    POST /api/chat/
    Smart sync endpoint:
      1. Validates + rate-limits the request
      2. Tries to run via Celery task (async worker)
      3. If Celery/Redis is unavailable, falls back to direct inline execution
      4. Returns the reply once complete
    This guarantees a response whether or not Celery is running.
    """
    if _check_rate_limit(request, limit=20, window=60):
        return JsonResponse(
            {'success': False, 'reply': 'Too many requests. Please wait a moment.'},
            status=429,
        )

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'reply': 'Invalid JSON payload.'}, status=400)

    cleaned, errors = validate_chat(data)
    if errors:
        return JsonResponse(
            {'success': False, 'reply': next(iter(errors.values())), 'errors': errors},
            status=400,
        )

    session_id = _get_or_create_session(request)

    # Try Celery first (non-blocking task)
    # For the SYNC endpoint we call the task function directly (not .delay())
    # so it runs in the web process and we wait for the result.
    # This avoids the polling timeout problem entirely for the default flow.
    try:
        from chatbot.tasks import run_rag_pipeline
        result = run_rag_pipeline(
            query=cleaned['message'],
            history=cleaned['history'],
            session_id=session_id,
        )
    except Exception as e:
        logger.warning(f'Celery task failed inline, falling back to direct RAG: {e}')
        try:
            result = _run_rag_direct(cleaned['message'], cleaned['history'], session_id)
        except Exception as e2:
            logger.error(f'Direct RAG also failed: {e2}', exc_info=True)
            result = {
                'reply': ('I encountered an error. Please contact us at '
                          'info@anupambearings.com or call +91-98844-00741.'),
                'sources': [], 'cached': False, 'chunks_found': 0,
            }

    return JsonResponse({
        'success':      True,
        'reply':        result['reply'],
        'sources':      result.get('sources', []),
        'cached':       result.get('cached', False),
        'chunks_found': result.get('chunks_found', 0),
    })


# ── ASYNC endpoint — enqueues Celery task, returns task_id ───────────────────

@csrf_exempt
@require_POST
def chat_async(request):
    """
    POST /api/chat/async/
    Enqueues a Celery task and returns {task_id} immediately.
    Frontend polls GET /api/chat/result/<task_id>/ for the answer.
    """
    if _check_rate_limit(request, limit=10, window=60):
        return JsonResponse(
            {'success': False, 'reply': 'Too many requests. Please wait a moment.'},
            status=429,
        )

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'reply': 'Invalid JSON payload.'}, status=400)

    cleaned, errors = validate_chat(data)
    if errors:
        return JsonResponse(
            {'success': False, 'reply': next(iter(errors.values())), 'errors': errors},
            status=400,
        )

    session_id = _get_or_create_session(request)

    try:
        from chatbot.tasks import run_rag_pipeline
        task = run_rag_pipeline.delay(
            query=cleaned['message'],
            history=cleaned['history'],
            session_id=session_id,
        )
        return JsonResponse({'success': True, 'task_id': task.id, 'status': 'queued'})
    except Exception as e:
        logger.warning(f'Celery unavailable for async chat: {e}')
        # Celery not running — fall back to sync and return result directly
        try:
            result = _run_rag_direct(cleaned['message'], cleaned['history'], session_id)
            # Return as if task completed immediately
            return JsonResponse({
                'success':      True,
                'task_id':      None,
                'status':       'completed',   # signal frontend to use reply directly
                'reply':        result['reply'],
                'sources':      result.get('sources', []),
                'cached':       False,
                'chunks_found': result.get('chunks_found', 0),
            })
        except Exception as e2:
            logger.error(f'Fallback also failed: {e2}')
            return JsonResponse({'success': False, 'reply': str(e2)}, status=500)


@require_GET
def chat_result(request, task_id):
    """GET /api/chat/result/<task_id>/ — poll for async result."""
    try:
        uuid.UUID(task_id)
    except ValueError:
        return JsonResponse({'status': 'error', 'reply': 'Invalid task ID.'}, status=400)

    try:
        from celery.result import AsyncResult
        result = AsyncResult(task_id)

        if result.state == 'PENDING':
            return JsonResponse({'status': 'pending'})
        elif result.state == 'STARTED':
            return JsonResponse({'status': 'processing'})
        elif result.state == 'SUCCESS':
            d = result.result or {}
            return JsonResponse({
                'status':       'success',
                'reply':        d.get('reply', ''),
                'sources':      d.get('sources', []),
                'cached':       d.get('cached', False),
                'chunks_found': d.get('chunks_found', 0),
            })
        elif result.state == 'FAILURE':
            return JsonResponse({
                'status': 'failure',
                'reply': ('The request failed. Please contact us at '
                          'info@anupambearings.com or call +91-98844-00741.'),
            })
        else:
            return JsonResponse({'status': result.state.lower()})
    except Exception as e:
        logger.error(f'chat_result error: {e}', exc_info=True)
        return JsonResponse({'status': 'error', 'reply': str(e)}, status=500)


# ── HEALTH + STATS ────────────────────────────────────────────────────────────

@require_GET
def chat_health(request):
    from rag.llm_client import check_ollama_health
    from rag.retriever  import get_index_stats

    ollama = check_ollama_health()
    faiss  = get_index_stats()

    redis_ok = False
    try:
        cache.set('_health_ping', 'pong', 5)
        redis_ok = cache.get('_health_ping') == 'pong'
    except Exception:
        pass

    overall = 'healthy' if (ollama['healthy'] and faiss['exists'] and redis_ok) else \
              'degraded' if ollama['healthy'] else 'offline'

    return JsonResponse({
        'ollama':  ollama,
        'faiss':   faiss,
        'redis':   {'healthy': redis_ok},
        'overall': overall,
    })


@require_GET
def chat_stats(request):
    from rag.retriever import get_index_stats
    return JsonResponse(get_index_stats())
