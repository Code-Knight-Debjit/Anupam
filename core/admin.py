from django.contrib import admin

from .models import GalleryImage, IndustryCard


@admin.register(IndustryCard)
class IndustryCardAdmin(admin.ModelAdmin):
	list_display = ['title', 'order', 'is_active']
	list_editable = ['order', 'is_active']
	search_fields = ['title', 'description']


@admin.register(GalleryImage)
class GalleryImageAdmin(admin.ModelAdmin):
	list_display = ['title', 'category', 'order', 'is_active', 'created_at']
	list_filter = ['is_active', 'category']
	search_fields = ['title', 'category', 'caption']
	list_editable = ['order', 'is_active']
