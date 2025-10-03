# Generated migration for OrderItem model

from django.db import migrations, models
import django.db.models.deletion
from django.core.validators import MinValueValidator
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0004_quoteoption_buying_company_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('item_name', models.CharField(max_length=200, help_text='Name of the item')),
                ('is_custom_item', models.BooleanField(default=False, help_text='Whether this is a custom item not in predefined list')),
                ('quantity', models.PositiveIntegerField(validators=[MinValueValidator(1)])),
                ('unit', models.CharField(max_length=50, default='pieces')),
                ('estimated_cost', models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))], null=True, blank=True)),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='orders.order')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        # Add index for faster queries
        migrations.AddIndex(
            model_name='orderitem',
            index=models.Index(fields=['order', 'id'], name='orders_orde_order_i_idx'),
        ),
    ]
