from django.apps import AppConfig


class ProductsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'products'

    def ready(self):
        # Every new shop starts with the fashion product types.
        from django.db.models.signals import post_save
        from accounts.models import Shop
        from .services import seed_product_types_for_new_shop
        post_save.connect(seed_product_types_for_new_shop, sender=Shop, dispatch_uid='seed_product_types')

