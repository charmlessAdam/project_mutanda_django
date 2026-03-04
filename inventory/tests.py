from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import InventoryCategory

User = get_user_model()


class InventoryPermissionsTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='inventory_user',
            email='inventory@example.com',
            password='InventoryPass!123',
            role='viewer',
        )

    def test_anonymous_cannot_access_categories(self):
        response = self.client.get('/api/inventory/categories/')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_authenticated_user_can_list_and_create_categories(self):
        self.client.force_authenticate(user=self.user)

        list_response = self.client.get('/api/inventory/categories/')
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)

        create_response = self.client.post(
            '/api/inventory/categories/',
            {
                'name': 'Supplements',
                'description': 'Nutritional supplements',
            },
            format='json',
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        category = InventoryCategory.objects.get(name='Supplements')
        self.assertEqual(category.created_by, self.user)
