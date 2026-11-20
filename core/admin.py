from django.contrib import admin
from jalali_suite.admin import JalaliDateModelAdmin
from .models import Testimonial


@admin.register(Testimonial)
class TestimonialAdmin(JalaliDateModelAdmin):
    list_display = ['name', 'role', 'rating', 'is_active', 'order', 'created_at']
    list_editable = ['is_active', 'order']
    list_filter = ['is_active', 'rating']
    search_fields = ['name', 'content']