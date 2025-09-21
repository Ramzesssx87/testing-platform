from django.core.management.base import BaseCommand
from django.conf import settings
import os
from tests.utils.excel_importer import import_test_from_excel

class Command(BaseCommand):
    help = 'Импортирует тест из Excel файла'
    
    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Путь к Excel файлу')
        parser.add_argument('--test_name', type=str, help='Название теста', default=None)
    
    def handle(self, *args, **options):
        file_path = options['file_path']
        test_name = options['test_name']
        
        if not os.path.isabs(file_path):
            file_path = os.path.join(settings.BASE_DIR, file_path)
        
        try:
            test = import_test_from_excel(file_path, test_name)
            self.stdout.write(
                self.style.SUCCESS(
                    f'Успешно импортирован тест "{test.name}" с {test.questions.count()} вопросами'
                )
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка импорта: {str(e)}'))