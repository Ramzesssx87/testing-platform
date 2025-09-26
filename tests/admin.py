from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import UserProfile

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Профиль'

class CustomUserAdmin(UserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'get_department_code', 'is_staff')
    
    def get_department_code(self, obj):
        return obj.profile.department_code if hasattr(obj, 'profile') else 'Не указан'
    get_department_code.short_description = 'Код подразделения'

# Перерегистрируем UserAdmin
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

# Регистрируем UserProfile отдельно
@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'department_code', 'created_at')
    list_filter = ('department_code', 'created_at')
    search_fields = ('user__username', 'user__email', 'department_code')