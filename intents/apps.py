from django.apps import AppConfig


class IntentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'intents'

    def ready(self):
        import intents.signals
