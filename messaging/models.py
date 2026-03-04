from django.conf import settings
from django.db import models


class Conversation(models.Model):
    TYPE_DIRECT = 'direct'
    TYPE_GROUP = 'group'
    TYPE_CHOICES = [
        (TYPE_DIRECT, 'Direct'),
        (TYPE_GROUP, 'Group'),
    ]

    STATUS_OPEN = 'open'
    STATUS_CLOSED = 'closed'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Open'),
        (STATUS_CLOSED, 'Closed'),
    ]

    conversation_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_DIRECT)
    title = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_conversations')
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, through='ConversationParticipant', related_name='conversations')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Conversation {self.id} ({self.conversation_type})"


class ConversationParticipant(models.Model):
    ROLE_OWNER = 'owner'
    ROLE_MEMBER = 'member'
    ROLE_MODERATOR = 'moderator'
    ROLE_CHOICES = [
        (ROLE_OWNER, 'Owner'),
        (ROLE_MEMBER, 'Member'),
        (ROLE_MODERATOR, 'Moderator'),
    ]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='conversation_participants')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='conversation_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    last_read_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('conversation', 'user')
        ordering = ['joined_at']

    def __str__(self):
        return f"{self.user.username} in {self.conversation_id}"


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
    body = models.TextField()
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Message {self.id} in {self.conversation_id}"
