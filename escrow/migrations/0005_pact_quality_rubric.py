# Generated manually — adds quality_rubric and confidence_threshold to Pact.

from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("escrow", "0004_pact_retry_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="pact",
            name="quality_rubric",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Buyer requirements and acceptance guidelines.",
            ),
        ),
        migrations.AddField(
            model_name="pact",
            name="confidence_threshold",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.85"),
                help_text="Required minimum AI confidence score (0.50 - 0.99).",
                max_digits=3,
            ),
        ),
    ]
