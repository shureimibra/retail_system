from .models import Category, Product, ProductVariation

def get_all_categories():
    return Category.objects.all().order_by('name')

def get_all_products():
    return Product.objects.all().select_related('category').order_by('name')

def get_product_variations(product_id):
    return ProductVariation.objects.filter(product_id=product_id).order_by('size', 'color')
