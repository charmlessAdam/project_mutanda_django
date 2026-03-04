import json
import time
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Max, Q
from django.http import StreamingHttpResponse, HttpResponse
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.renderers import BaseRenderer
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from .models import Conversation, ConversationParticipant, Message
from .serializers import ConversationSerializer, MessageSerializer
from orders.models import OrderNotification

User = get_user_model()


class ServerSentEventRenderer(BaseRenderer):
    media_type = 'text/event-stream'
    format = 'event-stream'
    charset = None
    render_style = 'binary'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'patch']

    def get_queryset(self):
        user = self.request.user
        return (
            Conversation.objects.filter(conversation_participants__user=user)
            .select_related('created_by')
            .prefetch_related('conversation_participants__user')
            .annotate(last_message_at=Max('messages__created_at'))
            .order_by('-last_message_at', '-updated_at')
        )

    def perform_create(self, serializer):
        serializer.save()

    def _calculate_unread_count(self, user):
        """Calculate total unread messages across all conversations for the user."""
        memberships = ConversationParticipant.objects.filter(user=user)
        total = 0
        for membership in memberships:
            qs = Message.objects.filter(conversation_id=membership.conversation_id).exclude(sender=user)
            if membership.last_read_at:
                qs = qs.filter(created_at__gt=membership.last_read_at)
            total += qs.count()
        return total

    def _latest_incoming_message_info(self, user):
        """Get the latest incoming message ID and sender name for notifications."""
        try:
            message = (
                Message.objects.filter(conversation__conversation_participants__user=user)
                .exclude(sender=user)
                .select_related('sender')
                .order_by('-id')
                .first()
            )
            if message:
                return {
                    'id': message.id,
                    'sender': message.sender.full_name or message.sender.username,
                    'body_preview': (message.body[:50] + '...') if len(message.body) > 50 else message.body
                }
        except Exception as e:
            print(f"Error fetching latest message info: {e}")
        return {'id': 0, 'sender': '', 'body_preview': ''}

    @action(detail=False, methods=['get'], url_path='users')
    def users(self, request):
        """Return company users that can be selected for new conversations."""
        search = (request.query_params.get('search') or '').strip()

        queryset = User.objects.filter(is_deleted=False, is_active=True).exclude(id=request.user.id)
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )

        users = queryset.order_by('username')[:200]

        data = [
            {
                'id': u.id,
                'username': u.username,
                'full_name': u.full_name,
                'email': u.email,
                'role': u.role,
                'role_display': u.get_role_display(),
            }
            for u in users
        ]
        return Response(data)

    @action(detail=True, methods=['get', 'post'])
    def messages(self, request, pk=None):
        conversation = self.get_object()

        if request.method == 'GET':
            messages = conversation.messages.select_related('sender').all()

            after_id = request.query_params.get('after_id')
            before_id = request.query_params.get('before_id')
            limit_raw = request.query_params.get('limit')
            try:
                limit = int(limit_raw) if limit_raw is not None else 50
            except ValueError:
                return Response({'error': 'limit must be an integer'}, status=status.HTTP_400_BAD_REQUEST)
            limit = max(1, min(limit, 200))

            if after_id:
                try:
                    after_id_int = int(after_id)
                    if after_id_int > 0:
                        messages = messages.filter(id__gt=after_id_int)
                except ValueError:
                    return Response({'error': 'after_id must be an integer'}, status=status.HTTP_400_BAD_REQUEST)

            if before_id:
                try:
                    before_id_int = int(before_id)
                    if before_id_int > 0:
                        messages = messages.filter(id__lt=before_id_int)
                except ValueError:
                    return Response({'error': 'before_id must be an integer'}, status=status.HTTP_400_BAD_REQUEST)

            # For initial loads and loading older history, fetch from the newest side
            # then reverse for chronological rendering.
            if after_id:
                items = list(messages.order_by('id')[:limit])
            else:
                items = list(messages.order_by('-id')[:limit])
                items.reverse()

            serializer = MessageSerializer(items, many=True)

            oldest_id = items[0].id if items else None
            newest_id = items[-1].id if items else None
            has_more_older = bool(oldest_id and conversation.messages.filter(id__lt=oldest_id).exists())

            return Response(
                {
                    'results': serializer.data,
                    'has_more_older': has_more_older,
                    'oldest_id': oldest_id,
                    'newest_id': newest_id,
                }
            )

        body = (request.data.get('body') or '').strip()
        if not body:
            return Response({'error': 'Message body is required.'}, status=status.HTTP_400_BAD_REQUEST)

        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            body=body,
        )
        Conversation.objects.filter(id=conversation.id).update(updated_at=timezone.now())

        recipients = conversation.conversation_participants.exclude(user=request.user).select_related('user')
        sender_name = request.user.full_name or request.user.username
        body_preview = (body[:120] + '...') if len(body) > 120 else body
        for membership in recipients:
            OrderNotification.objects.create(
                recipient=membership.user,
                actor=request.user,
                category='message',
                notification_type='new_message',
                title=f'New message from {sender_name}',
                message=body_preview,
                source_url='/customer-messages',
                metadata={
                    'conversation_id': conversation.id,
                    'message_id': message.id,
                },
            )

        serializer = MessageSerializer(message)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        conversation = self.get_object()
        membership = ConversationParticipant.objects.filter(
            conversation=conversation,
            user=request.user,
        ).first()

        if not membership:
            return Response({'error': 'Not a conversation participant.'}, status=status.HTTP_403_FORBIDDEN)

        membership.last_read_at = timezone.now()
        membership.save(update_fields=['last_read_at'])

        OrderNotification.objects.filter(
            recipient=request.user,
            category='message',
            notification_type='new_message',
            is_read=False,
            metadata__conversation_id=conversation.id,
        ).update(is_read=True, read_at=timezone.now())

        return Response({'success': True, 'message': 'Conversation marked as read.'})

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        total = self._calculate_unread_count(request.user)
        return Response({'unread_count': total})


def messaging_events(request):
    """
    Standalone function-based view for SSE. 
    Bypasses DRF to avoid 406/500 errors and ensures CORS headers are always present.
    """
    # 1. Setup CORS headers for all responses
    origin = request.headers.get('Origin')
    cors_allowed_origins = getattr(settings, 'CORS_ALLOWED_ORIGINS', [])
    allow_all_origins = bool(getattr(settings, 'CORS_ALLOW_ALL_ORIGINS', False))

    normalized_origin = (origin or '').rstrip('/')
    normalized_allowed_origins = {o.rstrip('/') for o in cors_allowed_origins}
    origin_allowed = allow_all_origins or (normalized_origin in normalized_allowed_origins)

    cors_headers = {
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    }
    if origin and origin_allowed:
        cors_headers['Access-Control-Allow-Origin'] = origin
        cors_headers['Access-Control-Allow-Credentials'] = 'true'

    # Handle Preflight
    if request.method == 'OPTIONS':
        response = HttpResponse()
        for k, v in cors_headers.items():
            response[k] = v
        return response

    if origin and not origin_allowed:
        response = HttpResponse(
            json.dumps({'error': 'CORS origin not allowed'}),
            content_type='application/json',
            status=403
        )
        for k, v in cors_headers.items():
            response[k] = v
        return response

    try:
        poll_seconds_raw = request.GET.get('poll_seconds')
        try:
            poll_seconds = int(poll_seconds_raw) if poll_seconds_raw is not None else 5
        except (TypeError, ValueError):
            poll_seconds = 5
        poll_seconds = max(2, min(30, poll_seconds))

        # 2. Manual Authentication (Bypass DRF for stability)
        user = None
        cookie_name = getattr(settings, 'JWT_ACCESS_COOKIE_NAME', 'access_token')
        token = request.COOKIES.get(cookie_name)

        if not token:
            # Check Authorization header as fallback
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]

        if token:
            try:
                jwt_auth = JWTAuthentication()
                validated_token = jwt_auth.get_validated_token(token)
                user = jwt_auth.get_user(validated_token)
            except (InvalidToken, TokenError, User.DoesNotExist) as e:
                print(f"SSE Auth Error: {e}")

        if not user or not user.is_authenticated:
            response = HttpResponse(
                json.dumps({'error': 'Unauthorized', 'detail': 'Valid token required'}), 
                content_type='application/json', 
                status=401
            )
            for k, v in cors_headers.items():
                response[k] = v
            return response

        # 3. Stream Generator
        def stream():
            try:
                def get_unread_and_latest():
                    memberships = list(
                        ConversationParticipant.objects.filter(user=user)
                        .values('conversation_id', 'last_read_at')
                    )
                    conversation_ids = [m['conversation_id'] for m in memberships]

                    unread = 0
                    for membership in memberships:
                        qs = Message.objects.filter(conversation_id=membership['conversation_id']).exclude(sender=user)
                        if membership['last_read_at']:
                            qs = qs.filter(created_at__gt=membership['last_read_at'])
                        unread += qs.count()

                    latest_message = None
                    if conversation_ids:
                        latest_message = (
                            Message.objects.filter(conversation_id__in=conversation_ids)
                            .exclude(sender=user)
                            .select_related('sender')
                            .order_by('-id')
                            .first()
                        )

                    return unread, latest_message

                unread, latest_message = get_unread_and_latest()
                last_unread = unread
                last_message_id = latest_message.id if latest_message else 0

                payload = {
                    'type': 'messaging_unread_update',
                    'unread_count': unread,
                    'latest_message_id': last_message_id,
                    'latest_conversation_id': latest_message.conversation_id if latest_message else 0,
                    'latest_sender': (
                        (latest_message.sender.full_name or latest_message.sender.username)
                        if latest_message else 'System'
                    ),
                    'latest_body': (
                        ((latest_message.body[:50] + '...') if len(latest_message.body) > 50 else latest_message.body)
                        if latest_message else 'Realtime connection established'
                    ),
                }
                yield f"event: messaging\ndata: {json.dumps(payload)}\n\n"

                heartbeat_counter = 0
                heartbeat_every_cycles = max(1, 20 // poll_seconds)
                while True:
                    time.sleep(poll_seconds)
                    heartbeat_counter += 1

                    unread, latest_message = get_unread_and_latest()
                    latest_message_id = latest_message.id if latest_message else 0

                    if unread != last_unread or latest_message_id != last_message_id:
                        last_unread = unread
                        last_message_id = latest_message_id

                        payload = {
                            'type': 'messaging_unread_update',
                            'unread_count': unread,
                            'latest_message_id': latest_message_id,
                            'latest_conversation_id': latest_message.conversation_id if latest_message else 0,
                            'latest_sender': (
                                (latest_message.sender.full_name or latest_message.sender.username)
                                if latest_message else ''
                            ),
                            'latest_body': (
                                ((latest_message.body[:50] + '...') if len(latest_message.body) > 50 else latest_message.body)
                                if latest_message else ''
                            ),
                        }
                        yield f"event: messaging\ndata: {json.dumps(payload)}\n\n"

                    # Keep proxy/server connections alive if no updates happened.
                    if heartbeat_counter >= heartbeat_every_cycles:
                        heartbeat_counter = 0
                        yield ': keep-alive\n\n'
            except GeneratorExit:
                return
            except Exception as stream_err:
                print(f"SSE Stream Error: {stream_err}")

        # 4. Create Streaming Response
        response = StreamingHttpResponse(stream(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        for k, v in cors_headers.items():
            response[k] = v
        return response

    except Exception as global_err:
        # Catch-all to prevent 500 without headers
        print(f"SSE Global Error: {global_err}")
        response = HttpResponse(
            json.dumps({'error': 'Internal Server Error', 'detail': str(global_err)}), 
            content_type='application/json', 
            status=500
        )
        for k, v in cors_headers.items():
            response[k] = v
        return response
