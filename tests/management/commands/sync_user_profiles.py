from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from tests.models import UserProfile

class Command(BaseCommand):
    help = 'Sync data between User and UserProfile models'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--direction',
            type=str,
            default='both',
            choices=['user_to_profile', 'profile_to_user', 'both'],
            help='Direction of sync: user_to_profile, profile_to_user, or both'
        )
    
    def handle(self, *args, **options):
        direction = options['direction']
        users = User.objects.all()
        sync_count = 0
        
        for user in users:
            profile, created = UserProfile.objects.get_or_create(user=user)
            needs_save = False
            
            if direction in ['user_to_profile', 'both']:
                # Sync from User to Profile
                if user.first_name and user.first_name != profile.first_name:
                    profile.first_name = user.first_name
                    needs_save = True
                    self.stdout.write(f'Synced first_name to profile for {user.username}')
                
                if user.last_name and user.last_name != profile.last_name:
                    profile.last_name = user.last_name
                    needs_save = True
                    self.stdout.write(f'Synced last_name to profile for {user.username}')
            
            if direction in ['profile_to_user', 'both']:
                # Sync from Profile to User
                if profile.first_name and profile.first_name != user.first_name:
                    user.first_name = profile.first_name
                    user.save()
                    self.stdout.write(f'Synced first_name to User for {user.username}')
                    sync_count += 1
                
                if profile.last_name and profile.last_name != user.last_name:
                    user.last_name = profile.last_name
                    user.save()
                    self.stdout.write(f'Synced last_name to User for {user.username}')
                    sync_count += 1
            
            if needs_save:
                profile.save()
                sync_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully synchronized {sync_count} records')
        )