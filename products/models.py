from pathlib import Path
from uuid import uuid4

from django.db import models
from django.utils.text import slugify


def product_excel_upload_to(instance, filename):
    base = slugify(instance.slug or instance.name or 'product') or 'product'
    suffix = Path(filename).suffix.lower() or '.xlsx'
    return f'product_tables/{base}-{uuid4().hex[:8]}{suffix}'


def product_image_upload_to(instance, filename):
    base = slugify(instance.product.slug or instance.product.name or 'product') or 'product'
    suffix = Path(filename).suffix.lower() or '.jpg'
    return f'products/{base}/{uuid4().hex[:8]}{suffix}'

class Category(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=100, blank=True, help_text="Icon class or emoji")
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    order = models.IntegerField(default=0)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    specifications = models.JSONField(default=dict, blank=True)
    needs_excel_table = models.BooleanField(default=False)
    excel_table_file = models.FileField(upload_to=product_excel_upload_to, blank=True, null=True)
    excel_table_data = models.JSONField(default=dict, blank=True)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to=product_image_upload_to)
    caption = models.CharField(max_length=200, blank=True)
    order = models.IntegerField(default=0)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Product image'
        verbose_name_plural = 'Product images'

    def __str__(self):
        return f'{self.product.name} image {self.pk or "new"}'


class Enquiry(models.Model):
    STATUS_CHOICES = [('new', 'New'), ('in_progress', 'In Progress'), ('resolved', 'Resolved')]
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    company = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Enquiries'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.product}"
