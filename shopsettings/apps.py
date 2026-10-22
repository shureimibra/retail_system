from django.apps import AppConfig


class ShopSettingsConfig(AppConfig):
    """Settings: how the shop works, set once and changed rarely. Never on the dashboard."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'shopsettings'
    verbose_name = 'Settings'
