from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Conversation, ConversationParticipant

User = get_user_model()


class MessagingApiTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='msg_user_1',
            email='msg1@example.com',
            password='Passw0rd!123',
            role='viewer',
        )
        self.user2 = User.objects.create_user(
            username='msg_user_2',
            email='msg2@example.com',
            password='Passw0rd!123',
            role='viewer',
        )
        self.user3 = User.objects.create_user(
            username='msg_user_3',
            email='msg3@example.com',
            password='Passw0rd!123',
            role='viewer',
        )

    def test_create_direct_conversation_and_send_message(self):
        self.client.force_authenticate(user=self.user1)

        create_response = self.client.post(
            '/api/messaging/conversations/',
            {
                'conversation_type': 'direct',
                'participant_ids': [self.user2.id],
            },
            format='json',
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        conversation_id = create_response.data['id']

        msg_response = self.client.post(
            f'/api/messaging/conversations/{conversation_id}/messages/',
            {'body': 'Hello from user1'},
            format='json',
        )
        self.assertEqual(msg_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(msg_response.data['body'], 'Hello from user1')

    def test_duplicate_direct_conversation_returns_existing(self):
        self.client.force_authenticate(user=self.user1)

        first = self.client.post(
            '/api/messaging/conversations/',
            {
                'conversation_type': 'direct',
                'participant_ids': [self.user2.id],
            },
            format='json',
        )
        second = self.client.post(
            '/api/messaging/conversations/',
            {
                'conversation_type': 'direct',
                'participant_ids': [self.user2.id],
            },
            format='json',
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(Conversation.objects.count(), 1)

    def test_create_group_conversation(self):
        self.client.force_authenticate(user=self.user1)

        response = self.client.post(
            '/api/messaging/conversations/',
            {
                'conversation_type': 'group',
                'title': 'Ops Team',
                'participant_ids': [self.user2.id, self.user3.id],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['conversation_type'], 'group')
        self.assertEqual(response.data['title'], 'Ops Team')

    def test_non_participant_cannot_access_conversation(self):
        self.client.force_authenticate(user=self.user1)
        create_response = self.client.post(
            '/api/messaging/conversations/',
            {
                'conversation_type': 'direct',
                'participant_ids': [self.user2.id],
            },
            format='json',
        )
        conversation_id = create_response.data['id']

        outsider = User.objects.create_user(
            username='msg_user_4',
            email='msg4@example.com',
            password='Passw0rd!123',
            role='viewer',
        )
        self.client.force_authenticate(user=outsider)
        response = self.client.get(f'/api/messaging/conversations/{conversation_id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_mark_read_updates_last_read_at(self):
        self.client.force_authenticate(user=self.user1)
        create_response = self.client.post(
            '/api/messaging/conversations/',
            {
                'conversation_type': 'direct',
                'participant_ids': [self.user2.id],
            },
            format='json',
        )
        conversation_id = create_response.data['id']

        self.client.post(
            f'/api/messaging/conversations/{conversation_id}/messages/',
            {'body': 'Ping'},
            format='json',
        )

        self.client.force_authenticate(user=self.user2)
        read_response = self.client.post(f'/api/messaging/conversations/{conversation_id}/read/', {}, format='json')
        self.assertEqual(read_response.status_code, status.HTTP_200_OK)

        membership = ConversationParticipant.objects.get(conversation_id=conversation_id, user=self.user2)
        self.assertIsNotNone(membership.last_read_at)

    def test_messages_after_id_returns_only_newer(self):
        self.client.force_authenticate(user=self.user1)
        create_response = self.client.post(
            '/api/messaging/conversations/',
            {
                'conversation_type': 'direct',
                'participant_ids': [self.user2.id],
            },
            format='json',
        )
        conversation_id = create_response.data['id']

        first = self.client.post(
            f'/api/messaging/conversations/{conversation_id}/messages/',
            {'body': 'm1'},
            format='json',
        )
        second = self.client.post(
            f'/api/messaging/conversations/{conversation_id}/messages/',
            {'body': 'm2'},
            format='json',
        )

        response = self.client.get(f'/api/messaging/conversations/{conversation_id}/messages/?after_id={first.data["id"]}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], second.data['id'])

    def test_users_endpoint_lists_company_users_except_self(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.get('/api/messaging/conversations/users/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item['id'] for item in response.data}

        self.assertIn(self.user2.id, ids)
        self.assertIn(self.user3.id, ids)
        self.assertNotIn(self.user1.id, ids)

    def test_users_endpoint_supports_search(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.get('/api/messaging/conversations/users/?search=msg_user_2')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], self.user2.id)

    def test_realtime_endpoint_requires_auth(self):
        response = self.client.get('/api/messaging/realtime/', HTTP_ORIGIN='http://localhost:5173')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_realtime_endpoint_returns_sse_content_type_for_valid_cookie(self):
        refresh = RefreshToken.for_user(self.user1)
        access_token = str(refresh.access_token)
        cookie_name = getattr(settings, 'JWT_ACCESS_COOKIE_NAME', 'access_token')
        self.client.cookies[cookie_name] = access_token

        response = self.client.get(
            '/api/messaging/realtime/',
            HTTP_ACCEPT='text/event-stream',
            HTTP_ORIGIN='http://localhost:5173',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('text/event-stream', response.get('Content-Type', ''))
        self.assertEqual(response.get('Access-Control-Allow-Origin'), 'http://localhost:5173')
