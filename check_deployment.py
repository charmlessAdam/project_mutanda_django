#!/usr/bin/env python3
"""
Quick script to check which endpoints are available on the backend.
Run this locally to see what's registered.
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_mutanda_django.settings')
django.setup()

from django.urls import get_resolver
from rest_framework.routers import DefaultRouter

def list_order_endpoints():
    """List all order-related endpoints"""
    from orders.views import OrderViewSet

    # Get all action methods from OrderViewSet
    actions = []
    for attr_name in dir(OrderViewSet):
        attr = getattr(OrderViewSet, attr_name)
        if hasattr(attr, 'mapping') or hasattr(attr, 'detail'):
            actions.append(attr_name)

    print("=" * 60)
    print("ORDER VIEWSET ACTIONS:")
    print("=" * 60)
    for action in sorted(actions):
        print(f"  - {action}")

    print("\n" + "=" * 60)
    print("CHECKING SPECIFIC NEW ENDPOINTS:")
    print("=" * 60)

    # Check specific endpoints
    endpoints_to_check = [
        'manager_approve',
        'submit_quote',
        'approve_quote',
        'complete_payment',
        'complete'
    ]

    for endpoint in endpoints_to_check:
        has_it = hasattr(OrderViewSet, endpoint)
        status = "✓ EXISTS" if has_it else "✗ MISSING"
        print(f"  {endpoint:20s} {status}")

if __name__ == '__main__':
    list_order_endpoints()
