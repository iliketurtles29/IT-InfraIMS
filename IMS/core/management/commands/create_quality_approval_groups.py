from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group


class Command(BaseCommand):
    help = "Create the four Computer Quality Inspection approver groups."

    GROUPS = [
        "Technical Supervisor",
        "Server Supervisor",
        "NAV/SAP Supervisor",
        "IT Manager",
    ]

    def handle(self, *args, **options):
        for group_name in self.GROUPS:
            group, created = Group.objects.get_or_create(
                name=group_name
            )

            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created group: {group_name}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Already exists: {group_name}"
                    )
                )
