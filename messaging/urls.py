from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ConversationViewSet, messaging_events

router = DefaultRouter()
router.register(r'conversations', ConversationViewSet, basename='conversations')

urlpatterns = [
    path('realtime/', messaging_events, name='messaging-events'),
    path('', include(router.urls)),
]
