from pathlib import Path
from uuid import uuid4

from django.db import models


def industry_image_upload_to(instance, filename):
	suffix = Path(filename).suffix.lower() or '.jpg'
	return f'industries/{uuid4().hex[:12]}{suffix}'


def gallery_image_upload_to(instance, filename):
	suffix = Path(filename).suffix.lower() or '.jpg'
	return f'gallery/{uuid4().hex[:12]}{suffix}'


class IndustryCard(models.Model):
	title = models.CharField(max_length=200)
	description = models.TextField()
	image = models.ImageField(upload_to=industry_image_upload_to, blank=True, null=True)
	cta_label = models.CharField(max_length=80, blank=True, default='Learn More')
	order = models.IntegerField(default=0)
	is_active = models.BooleanField(default=True)

	class Meta:
		ordering = ['order', 'title']
		verbose_name = 'Industry card'
		verbose_name_plural = 'Industry cards'

	def __str__(self):
		return self.title


class GalleryImage(models.Model):
	title = models.CharField(max_length=200)
	category = models.CharField(max_length=100, blank=True)
	caption = models.TextField(blank=True)
	image = models.ImageField(upload_to=gallery_image_upload_to)
	order = models.IntegerField(default=0)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['order', '-created_at']
		verbose_name = 'Gallery image'
		verbose_name_plural = 'Gallery images'

	def __str__(self):
		return self.title
