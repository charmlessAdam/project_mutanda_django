from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework import serializers

from users.models import User
from .models import Conversation, ConversationParticipant, Message


class ParticipantUserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'full_name', 'role', 'email')


class MessageSerializer(serializers.ModelSerializer):
    sender = ParticipantUserSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ('id', 'conversation', 'sender', 'body', 'is_deleted', 'created_at', 'edited_at')
        read_only_fields = ('id', 'conversation', 'sender', 'is_deleted', 'created_at', 'edited_at')


class ConversationSerializer(serializers.ModelSerializer):
    participant_ids = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_deleted=False, is_active=True),
        write_only=True,
        many=True,
        required=False,
    )
    participants = serializers.SerializerMethodField(read_only=True)
    last_message = serializers.SerializerMethodField(read_only=True)
    unread_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Conversation
        fields = (
            'id',
            'conversation_type',
            'title',
            'status',
            'created_by',
            'created_at',
            'updated_at',
            'participant_ids',
            'participants',
            'last_message',
            'unread_count',
        )
        read_only_fields = ('id', 'created_by', 'created_at', 'updated_at')

    def validate(self, attrs):
        request = self.context['request']
        conversation_type = attrs.get('conversation_type', Conversation.TYPE_DIRECT)
        participant_ids = attrs.get('participant_ids', [])

        participant_set = {u.id for u in participant_ids}
        participant_set.add(request.user.id)

        if conversation_type == Conversation.TYPE_DIRECT and len(participant_set) != 2:
            raise serializers.ValidationError('Direct conversation must include exactly 2 participants including creator.')

        if conversation_type == Conversation.TYPE_GROUP and len(participant_set) < 3:
            raise serializers.ValidationError('Group conversation must include at least 3 participants including creator.')

        title = attrs.get('title', '').strip()
        if conversation_type == Conversation.TYPE_GROUP and not title:
            raise serializers.ValidationError('Group conversation requires title.')

        attrs['title'] = title
        return attrs

    def _find_existing_direct_conversation(self, user_a_id, user_b_id):
        return (
            Conversation.objects.filter(conversation_type=Conversation.TYPE_DIRECT)
            .annotate(participant_count=Count('conversation_participants', distinct=True))
            .filter(participant_count=2)
            .filter(conversation_participants__user_id=user_a_id)
            .filter(conversation_participants__user_id=user_b_id)
            .order_by('-updated_at')
            .first()
        )

    @transaction.atomic
    def create(self, validated_data):
        request = self.context['request']
        users = validated_data.pop('participant_ids', [])

        user_map = {u.id: u for u in users}
        user_map[request.user.id] = request.user
        participants = list(user_map.values())

        conversation_type = validated_data.get('conversation_type', Conversation.TYPE_DIRECT)

        if conversation_type == Conversation.TYPE_DIRECT:
            other_user = next(u for u in participants if u.id != request.user.id)
            existing = self._find_existing_direct_conversation(request.user.id, other_user.id)
            if existing:
                return existing

        conversation = Conversation.objects.create(created_by=request.user, **validated_data)

        rows = []
        now = timezone.now()
        for user in participants:
            role = ConversationParticipant.ROLE_OWNER if user.id == request.user.id else ConversationParticipant.ROLE_MEMBER
            rows.append(
                ConversationParticipant(
                    conversation=conversation,
                    user=user,
                    role=role,
                    last_read_at=now if user.id == request.user.id else None,
                )
            )
        ConversationParticipant.objects.bulk_create(rows)

        return conversation

    def get_participants(self, obj):
        users = [p.user for p in obj.conversation_participants.select_related('user').all()]
        return ParticipantUserSerializer(users, many=True).data

    def get_last_message(self, obj):
        msg = obj.messages.select_related('sender').order_by('-created_at').first()
        return MessageSerializer(msg).data if msg else None

    def get_unread_count(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0

        membership = obj.conversation_participants.filter(user=request.user).first()
        if not membership:
            return 0

        qs = obj.messages.exclude(sender=request.user)
        if membership.last_read_at:
            qs = qs.filter(created_at__gt=membership.last_read_at)
        return qs.count()
