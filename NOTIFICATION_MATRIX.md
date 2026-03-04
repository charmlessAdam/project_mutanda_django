# Notification Matrix (v1)

This document defines which events create notifications and who should receive them.

## Categories
- `message`
- `order`
- `inventory`
- `access`

## Event Rules

1. `message.new_message`
- Trigger: a new chat message is sent.
- Recipients: all conversation participants except sender.
- Deep link: `/customer-messages`
- Metadata: `conversation_id`, `message_id`

2. `order.approval_needed`
- Trigger: order enters an approval stage.
- Recipients: target approver roles (manager/finance_manager/super_admin depending on stage).
- Deep link: `/order-history`
- Metadata: `order_id`, `order_number`, `stage`

3. `order.approved`
- Trigger: order approved by stage approver.
- Recipients: requester + next stage approvers where applicable.
- Deep link: `/order-history`
- Metadata: `order_id`, `order_number`, `stage`

4. `order.rejected`
- Trigger: order rejected.
- Recipients: requester.
- Deep link: `/order-history`
- Metadata: `order_id`, `order_number`

5. `order.revision_requested`
- Trigger: revision requested by manager/procurement/finance.
- Recipients: requester (and role owners if needed).
- Deep link: `/order-history`
- Metadata: `order_id`, `order_number`, `requested_by_role`

6. `order.completed`
- Trigger: order completion/finalization.
- Recipients: requester + super_admin.
- Deep link: `/order-history`
- Metadata: `order_id`, `order_number`

7. `inventory.inventory_alert` (planned)
- Trigger: low stock / out of stock / near expiry.
- Recipients: warehouse_worker, manager, admin, super_admin (by section access policy).
- Deep link: `/storage-inventory`
- Metadata: `item_id`, `item_name`, `alert_type`

8. `access.access_changed` (planned)
- Trigger: role change, section permission change, activation/deactivation.
- Recipients: affected user + super_admin/admin.
- Deep link: `/user-list` or `/roles`
- Metadata: `target_user_id`, `change_type`

## Read Rules
- Single read: mark one notification as read.
- Bulk read: mark all (optionally by category) as read.
- Message read sync: when a conversation is marked read, message notifications for that conversation are auto-marked read.
