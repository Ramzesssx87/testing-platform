from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from tests.models import UserProfile

class Command(BaseCommand):
    help = 'Fix existing user profiles by copying data from User to UserProfile'
    
    def handle(self, *args, **options):
        users = User.objects.all()
        fixed_count = 0
        
        for user in users:
            profile, created = UserProfile.objects.get_or_create(user=user)
            
            # Если в профиле нет данных, но есть в User - копируем
            if not profile.first_name and user.first_name:
                profile.first_name = user.first_name
                self.stdout.write(f'Fixed first_name for user {user.username}')
                fixed_count += 1
                
            if not profile.last_name and user.last_name:
                profile.last_name = user.last_name
                self.stdout.write(f'Fixed last_name for user {user.username}')
                fixed_count += 1
                
            # Если в User нет данных, но есть в профиле - копируем обратно
            if not user.first_name and profile.first_name:
                User.objects.filter(id=user.id).update(first_name=profile.first_name)
                self.stdout.write(f'Fixed User.first_name from profile for {user.username}')
                fixed_count += 1
                
            if not user.last_name and profile.last_name:
                User.objects.filter(id=user.id).update(last_name=profile.last_name)
                self.stdout.write(f'Fixed User.last_name from profile for {user.username}')
                fixed_count += 1
                
            # Сохраняем профиль
            profile.save()
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully fixed {fixed_count} user records')
        )