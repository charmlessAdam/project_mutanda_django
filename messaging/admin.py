from django.contrib import admin

from .models import Conversation, ConversationParticipant, Message


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation_type', 'title', 'status', 'created_by', 'created_at', 'updated_at')
    list_filter = ('conversation_type', 'status', 'created_at')
    search_fields = ('title', 'created_by__username')


@admin.register(ConversationParticipant)
class ConversationParticipantAdmin(admin.ModelAdmin):
    list_display = ('conversation', 'user', 'role', 'last_read_at', 'joined_at')
    list_filter = ('role', 'joined_at')
    search_fields = ('user__username',)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'sender', 'is_deleted', 'created_at')
    list_filter = ('is_deleted', 'created_at')
    search_fields = ('sender__username', 'body')
