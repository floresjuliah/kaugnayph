from django.core.management.base import BaseCommand
from core.models import AvatarOptions


class Command(BaseCommand):
    help = "Seeds the 6 default resident profile avatars."

    def handle(self, *args, **options):
        avatars = [
            {"name": "Avatar 1", "image_path": "images/avatars/residentprofile1.png"},
            {"name": "Avatar 2", "image_path": "images/avatars/residentprofile2.png"},
            {"name": "Avatar 3", "image_path": "images/avatars/residentprofile3.png"},
            {"name": "Avatar 4", "image_path": "images/avatars/residentprofile4.png"},
            {"name": "Avatar 5", "image_path": "images/avatars/residentprofile5.png"},
            {"name": "Avatar 6", "image_path": "images/avatars/residentprofile6.png"},
        ]

        for av in avatars:
            obj, created = AvatarOptions.objects.update_or_create(
                image_path=av["image_path"],
                defaults={"name": av["name"], "is_active": True},
            )
            status = "Created" if created else "Already exists (updated)"
            self.stdout.write(self.style.SUCCESS(f"{status}: {obj.name}"))