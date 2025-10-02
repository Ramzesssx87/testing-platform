from django.core.management.base import BaseCommand
from django.utils import timezone
from tests.models import QuizSession, QuizParticipant, UserProfile
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Обновляет участников активных зачетов, добавляя новых пользователей группы'
    
    def handle(self, *args, **options):
        now = timezone.now()
        
        # Получаем активные зачеты (которые еще не закончились)
        active_quizzes = QuizSession.objects.filter(
            ends_at__gte=now
        )
        
        updated_count = 0
        
        for quiz in active_quizzes:
            # Получаем всех пользователей группы создателя
            creator_profile = quiz.creator.profile
            group_users = creator_profile.get_group_users()
            
            # Добавляем создателя, если его нет
            if quiz.creator not in group_users:
                group_users = list(group_users) + [quiz.creator]
            
            # Добавляем всех пользователей группы в зачет
            for user in group_users:
                # Проверяем, не является ли пользователь уже участником
                if not QuizParticipant.objects.filter(
                    quiz_session=quiz, 
                    user=user
                ).exists():
                    QuizParticipant.objects.create(
                        quiz_session=quiz,
                        user=user
                    )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Добавлен пользователь {user.username} в зачет "{quiz.test.name}"'
                        )
                    )
                    updated_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Обновление завершено. Добавлено {updated_count} новых участников.'
            )
        )