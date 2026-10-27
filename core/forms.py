from django import forms


class PhotoFieldsMixin:
    """
    Photo uploads without Django's "Clear + Change" puzzle: choosing a new file replaces the old one,
    and a separate "Remove this photo" tick clears it. Render with templates/ui/photo_field.html.
    """
    photo_fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.photo_fields:
            self.fields[name].widget = forms.FileInput(attrs={'accept': 'image/*', 'class': 'visually-hidden'})
            self.fields[f'remove_{name}'] = forms.BooleanField(required=False, label='Remove this photo')

    def clean(self):
        cleaned = super().clean()
        for name in self.photo_fields:
            uploaded = self.files.get(self.add_prefix(name))
            if cleaned.get(f'remove_{name}') and not uploaded:
                cleaned[name] = False  # tells the file field to clear itself
        return cleaned
