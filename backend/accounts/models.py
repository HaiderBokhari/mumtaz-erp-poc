from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    """
    Extra fields hung off the built-in Django ``User``.

    Access control itself is done with Django's Groups/Permissions (one
    Group per role in ``settings.ALL_ROLES`` — see
    ``accounts.management.commands.seed_demo_data``). This profile adds the
    business-specific bits: which warehouse/branch a user is restricted to
    (Sargodha HQ, Bhalwal, Bhera, ...) and their DR code, used across the
    distribution module (e.g. "SGD_SGD_DR01").
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile'
    )
    phone = models.CharField(max_length=20, blank=True)
    dr_code = models.CharField(
        max_length=20, blank=True,
        help_text='Distribution Representative code, e.g. SGD_SGD_DR01. Only set for DR users.',
    )
    warehouse = models.ForeignKey(
        'warehouses.Warehouse', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='staff',
        help_text='Branch/warehouse this user is restricted to. Blank = all branches (Owner/HQ roles).',
    )
    supervisor = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='subordinates',
        help_text='Field hierarchy: DR -> FSO -> Distribution Manager (an FSO supervises up to ~7 DRs).',
    )
    is_blocked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.get_full_name() or self.user.username} profile'

    @property
    def roles(self):
        return list(self.user.groups.values_list('name', flat=True))
