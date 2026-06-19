from django.contrib import admin
from .models import Category, Product, ProductVariation

admin.site.register(Category)

class ProductVariationInline(admin.TabularInline):
    model = ProductVariation
    extra = 1

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'base_price', 'created_at')
    inlines = [ProductVariationInline]

@admin.register(ProductVariation)
class ProductVariationAdmin(admin.ModelAdmin):
    list_display = ('product', 'size', 'color', 'stock_quantity', 'sku')
    list_editable = ('stock_quantity',)

