from django.urls import path
from . import views

app_name = 'chatbot'
urlpatterns = [
    # Sync (backward-compatible with existing frontend JS)
    path('chat/',                    views.chat,         name='chat'),
    # Async variants
    path('chat/async/',              views.chat_async,   name='chat_async'),
    path('chat/result/<str:task_id>/', views.chat_result, name='chat_result'),
    # Ops
    path('chat/health/',             views.chat_health,  name='chat_health'),
    path('chat/stats/',              views.chat_stats,   name='chat_stats'),
]
