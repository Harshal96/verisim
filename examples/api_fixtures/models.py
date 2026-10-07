from django.db import models


class Customer(models.Model):
    email = models.EmailField()
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "fixture_example"
