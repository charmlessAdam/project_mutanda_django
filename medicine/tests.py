from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import MedicineClass, StoragePermission

User = get_user_model()


class MedicinePermissionsTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='meduser',
            email='meduser@example.com',
            password='Passw0rd!123',
            role='viewer',
        )

    def test_anonymous_cannot_access_medicine_classes(self):
        response = self.client.get('/api/medicine/classes/')
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_authenticated_without_storage_permission_is_forbidden(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get('/api/medicine/classes/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_authenticated_with_storage_permission_can_create_class_and_medicine(self):
        StoragePermission.objects.create(
            user=self.user,
            permission_type='full_access',
            granted_by=self.user,
            is_active=True,
        )

        self.client.force_authenticate(user=self.user)

        class_response = self.client.post('/api/medicine/classes/', {'name': 'Antibiotics'}, format='json')
        self.assertEqual(class_response.status_code, status.HTTP_201_CREATED)

        med_class = MedicineClass.objects.get(name='Antibiotics')
        medicine_response = self.client.post(
            '/api/medicine/medicines/',
            {
                'medicine_class': med_class.id,
                'product': 'SampleMed',
                'stock_remaining': '10.00',
                'unit': 'ml',
                'minimum_stock': '2.00',
            },
            format='json',
        )

        self.assertEqual(medicine_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(medicine_response.data['product'], 'SampleMed')
