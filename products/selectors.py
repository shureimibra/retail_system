from .models import Category, Product, ProductVariation

def get_all_categories(shop):
    return Category.objects.filter(shop=shop).order_by('name')

def get_all_products(shop):
    return Product.objects.filter(shop=shop).select_related('category').order_by('name')

def get_product_variations(product_id):
    return ProductVariation.objects.filter(product_id=product_id).order_by('option1', 'option2', 'option3')
