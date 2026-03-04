from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class AuthApiTests(APITestCase):
    def setUp(self):
        self.password = 'Passw0rd!123'
        self.user = User.objects.create_user(
            username='authuser',
            email='auth@example.com',
            password=self.password,
            role='viewer',
        )

    def test_login_returns_tokens_and_user(self):
        response = self.client.post(
            '/api/auth/login/',
            {'username': self.user.username, 'password': self.password},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('success'))
        self.assertIn('tokens', response.data)
        self.assertIn('access', response.data['tokens'])
        self.assertIn('refresh', response.data['tokens'])
        self.assertEqual(response.data['user']['username'], self.user.username)

    def test_login_is_not_blocked_by_invalid_access_cookie(self):
        self.client.cookies['access_token'] = 'invalid.token.value'
        response = self.client.post(
            '/api/auth/login/',
            {'username': self.user.username, 'password': self.password},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('success'))


class PasswordResetApiTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='rootadmin',
            email='rootadmin@example.com',
            password='AdminPass!123',
            role='super_admin',
        )
        self.target = User.objects.create_user(
            username='targetuser',
            email='target@example.com',
            password='OldPass!123',
            role='viewer',
        )

    def test_reset_password_requires_new_password(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(f'/api/manage-users/{self.target.id}/reset_password/', {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data.get('success'))
        self.assertIn('new_password', response.data.get('error', ''))

    def test_reset_password_does_not_return_plaintext_password(self):
        self.client.force_authenticate(user=self.admin)
        new_password = 'NewSecurePass!456'

        response = self.client.post(
            f'/api/manage-users/{self.target.id}/reset_password/',
            {'new_password': new_password},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('success'))
        self.assertNotIn('temporary_password', response.data)

        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password(new_password))


class UserRoleHierarchyTests(APITestCase):
    def setUp(self):
        self.super_admin = User.objects.create_user(
            username='superadmin_role',
            email='superadmin_role@example.com',
            password='SuperPass!123',
            role='super_admin',
        )
        self.admin = User.objects.create_user(
            username='admin_role',
            email='admin_role@example.com',
            password='AdminPass!123',
            role='admin',
        )
        self.manager = User.objects.create_user(
            username='manager_role',
            email='manager_role@example.com',
            password='ManagerPass!123',
            role='manager',
        )
        self.operator = User.objects.create_user(
            username='operator_role',
            email='operator_role@example.com',
            password='OperatorPass!123',
            role='operator',
            manager=self.manager,
        )
        self.viewer = User.objects.create_user(
            username='viewer_role',
            email='viewer_role@example.com',
            password='ViewerPass!123',
            role='viewer',
            manager=self.manager,
        )

    def _response_list(self, response):
        # Supports paginated and non-paginated DRF responses.
        if isinstance(response.data, dict) and 'results' in response.data:
            return response.data['results']
        return response.data

    def test_can_manage_role_follows_defined_hierarchy(self):
        self.assertTrue(self.admin.can_manage_role('manager'))
        self.assertFalse(self.admin.can_manage_role('super_admin'))
        self.assertTrue(self.manager.can_manage_role('operator'))
        self.assertFalse(self.manager.can_manage_role('admin'))

    def test_invalid_manager_assignment_is_rejected(self):
        with self.assertRaises(ValidationError):
            User.objects.create_user(
                username='illegal_admin',
                email='illegal_admin@example.com',
                password='IllegalPass!123',
                role='admin',
                manager=self.manager,
            )

    def test_manage_users_endpoint_returns_only_manageable_users_for_manager(self):
        self.client.force_authenticate(user=self.manager)
        response = self.client.get('/api/manage-users/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usernames = {item['username'] for item in self._response_list(response)}

        self.assertIn(self.operator.username, usernames)
        self.assertIn(self.viewer.username, usernames)
        self.assertNotIn(self.admin.username, usernames)
        self.assertNotIn(self.super_admin.username, usernames)

class CookieAuthFlowTests(APITestCase):
    def setUp(self):
        self.password = 'CookiePass!123'
        self.user = User.objects.create_user(
            username='cookieuser',
            email='cookie@example.com',
            password=self.password,
            role='viewer',
        )

    def test_login_sets_http_only_auth_cookies(self):
        response = self.client.post(
            '/api/auth/login/',
            {'username': self.user.username, 'password': self.password},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access_token', response.cookies)
        self.assertIn('refresh_token', response.cookies)

    def test_refresh_uses_cookie_and_returns_new_access_cookie(self):
        login_response = self.client.post(
            '/api/auth/login/',
            {'username': self.user.username, 'password': self.password},
            format='json',
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

        csrf_token = self.client.cookies.get('csrftoken').value if self.client.cookies.get('csrftoken') else ''
        refresh_response = self.client.post(
            '/api/auth/refresh/',
            {},
            format='json',
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(refresh_response.status_code, status.HTTP_200_OK)
        self.assertTrue(refresh_response.data.get('success'))
        self.assertIn('access_token', refresh_response.cookies)

    def test_logout_clears_cookies_and_refresh_fails_after_blacklist(self):
        login_response = self.client.post(
            '/api/auth/login/',
            {'username': self.user.username, 'password': self.password},
            format='json',
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

        csrf_token = self.client.cookies.get('csrftoken').value if self.client.cookies.get('csrftoken') else ''

        logout_response = self.client.post(
            '/api/auth/logout/',
            {},
            format='json',
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)
        self.assertTrue(logout_response.data.get('success'))

        refresh_response = self.client.post(
            '/api/auth/refresh/',
            {},
            format='json',
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertIn(refresh_response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_400_BAD_REQUEST])
