from django.contrib import admin
from .models import Category, Product, ProductType, ProductVariation

admin.site.register(Category)


@admin.register(ProductType)
class ProductTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'shop', 'option1_name', 'option2_name', 'option3_name')
    list_filter = ('shop',)

class ProductVariationInline(admin.TabularInline):
    model = ProductVariation
    extra = 1

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'product_type', 'category', 'base_price', 'needs_review', 'created_at')
    inlines = [ProductVariationInline]

@admin.register(ProductVariation)
class ProductVariationAdmin(admin.ModelAdmin):
    list_display = ('product', 'option1', 'option2', 'option3', 'stock_quantity', 'sku')
    readonly_fields = ('stock_quantity',)

