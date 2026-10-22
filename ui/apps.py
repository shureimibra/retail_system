from django.apps import AppConfig


class UiConfig(AppConfig):
    """Shared template building blocks: the icon tag, form fields and the shell's navigation."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ui'
