# Generated manually — adds REVISION_REQUESTED state choice and retry tracking fields to Pact.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("escrow", "0003_pact_deliverable_payload"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pact",
            name="state",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("AUTHORIZED", "Authorized"),
                    ("SUBMITTED", "Submitted"),
                    ("IN_REVIEW", "In Review"),
                    ("CAPTURED", "Captured"),
                    ("VOIDED", "Voided"),
                    ("REJECTED", "Rejected"),
                    ("REVISION_REQUESTED", "Revision Requested"),
                ],
                db_index=True,
                default="DRAFT",
                help_text="Current lifecycle state of the escrow pact.",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="pact",
            name="max_attempts",
            field=models.PositiveSmallIntegerField(
                default=3,
                help_text="Maximum allowed submission attempts before voiding.",
            ),
        ),
        migrations.AddField(
            model_name="pact",
            name="current_attempt",
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text="Current submission attempt index.",
            ),
        ),
        migrations.AddField(
            model_name="pact",
            name="last_rejection_reason",
            field=models.TextField(
                blank=True,
                null=True,
                help_text="AI rationale for previous revision request.",
            ),
        ),
        migrations.AddField(
            model_name="pact",
            name="last_rejection_flags",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Security or quality flags from previous attempt.",
            ),
        ),
    ]
