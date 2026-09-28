"""
Creates the fixed roles from the requirement doc's Access Control section
as Django Groups, and grants each one a sensible default set of
create/edit/view/delete permissions per feature (model) — exactly the
granularity the requirement doc asks for ("Each role will have
create/edit/view/delete/all permissions for a given feature").

An administrator can fine-tune this later from /admin/auth/group/ — this
command only sets a reasonable starting point and is safe to re-run.
"""
from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db.models import Q

# (app_label, model_name) -> which of add/change/delete/view each role gets.
# 'all' is shorthand for every action.
ROLE_MODEL_PERMISSIONS = {
    settings.ROLE_DISTRIBUTION_MANAGER: {
        ('catalog', 'brand'): 'all', ('catalog', 'sku'): 'all',
        ('catalog', 'channel'): 'all', ('catalog', 'channelprice'): 'all',
        ('warehouses', 'warehouse'): 'all', ('warehouses', 'stocklevel'): 'view',
        ('warehouses', 'stockledgerentry'): 'view', ('warehouses', 'stocktransfer'): 'all',
        ('warehouses', 'stockadjustment'): 'all', ('warehouses', 'safetystocklevel'): 'all',
        ('purchasing', 'purchaseorder'): 'all', ('purchasing', 'purchasereturn'): 'all',
        ('distribution', 'shop'): 'all', ('distribution', 'salesorder'): 'all',
        ('distribution', 'salesreturn'): 'all', ('distribution', 'paymentreceipt'): 'all',
        ('distribution', 'salestarget'): 'all',
        ('hr', 'employee'): 'all', ('hr', 'salarypayment'): 'all', ('hr', 'leaverequest'): 'all',
        ('accounting', 'party'): 'all', ('accounting', 'voucher'): 'all',
        ('accounting', 'chartofaccount'): 'view', ('accounting', 'accountgroup'): 'view',
        ('accounting', 'journalentry'): 'view',
    },
    settings.ROLE_FSO: {
        ('catalog', 'brand'): 'view', ('catalog', 'sku'): 'view',
        ('catalog', 'channel'): 'view', ('catalog', 'channelprice'): 'view',
        ('warehouses', 'warehouse'): 'view', ('warehouses', 'stocklevel'): 'view',
        ('purchasing', 'purchaseorder'): 'view',
        ('distribution', 'shop'): {'add', 'change', 'view'},
        ('distribution', 'salesorder'): {'add', 'change', 'view'},
        ('distribution', 'salesreturn'): {'add', 'view'},
        ('distribution', 'paymentreceipt'): {'add', 'view'},
        ('distribution', 'salestarget'): {'add', 'change', 'view'},
        ('hr', 'employee'): 'view', ('hr', 'leaverequest'): {'add', 'change', 'view'},
    },
    settings.ROLE_SALES_MANAGER: {
        ('catalog', 'brand'): 'view', ('catalog', 'sku'): 'view',
        ('catalog', 'channel'): 'view', ('catalog', 'channelprice'): {'add', 'view'},
        ('warehouses', 'warehouse'): 'view', ('warehouses', 'stocklevel'): 'view',
        ('purchasing', 'purchaseorder'): 'view',
        ('distribution', 'shop'): 'all', ('distribution', 'salesorder'): 'all',
        ('distribution', 'salesreturn'): 'all', ('distribution', 'paymentreceipt'): 'all',
        ('distribution', 'salestarget'): 'all',
        ('hr', 'employee'): 'view',
        ('accounting', 'party'): 'view', ('accounting', 'voucher'): 'view',
        ('accounting', 'journalentry'): 'view',
    },
    settings.ROLE_WAREHOUSE_STAFF: {
        ('catalog', 'brand'): 'view', ('catalog', 'sku'): 'view', ('catalog', 'channel'): 'view',
        ('warehouses', 'warehouse'): 'view', ('warehouses', 'stocklevel'): 'view',
        ('warehouses', 'stockledgerentry'): 'view',
        ('warehouses', 'stocktransfer'): 'all', ('warehouses', 'stockadjustment'): 'all',
        ('warehouses', 'safetystocklevel'): {'add', 'change', 'view'},
        ('purchasing', 'purchaseorder'): {'change', 'view'},
        ('distribution', 'salesorder'): 'view',
    },
    settings.ROLE_DR: {
        ('catalog', 'sku'): 'view', ('catalog', 'channel'): 'view', ('catalog', 'channelprice'): 'view',
        ('distribution', 'shop'): 'view',
        ('distribution', 'salesorder'): {'add', 'view'},
        ('distribution', 'paymentreceipt'): {'add', 'view'},
        ('distribution', 'salestarget'): 'view',
        ('warehouses', 'stocklevel'): 'view',
    },
    # Owner is created as a Django superuser (bypasses permission checks entirely)
    # so it intentionally has no explicit grants here.
}

ALL_ACTIONS = {'add', 'change', 'delete', 'view'}


class Command(BaseCommand):
    help = "Create the fixed roles (Groups) from the requirement doc and grant default per-feature permissions."

    def handle(self, *args, **options):
        for role_name in settings.ALL_ROLES:
            Group.objects.get_or_create(name=role_name)

        for role_name, model_perms in ROLE_MODEL_PERMISSIONS.items():
            group, _ = Group.objects.get_or_create(name=role_name)
            query = Q()
            for (app_label, model_name), actions in model_perms.items():
                actions = ALL_ACTIONS if actions == 'all' else set(actions)
                codenames = [f'{a}_{model_name}' for a in actions]
                query |= Q(content_type__app_label=app_label, content_type__model=model_name, codename__in=codenames)

            perms = Permission.objects.filter(query) if model_perms else Permission.objects.none()
            group.permissions.set(perms)
            self.stdout.write(f'{role_name}: {perms.count()} permissions granted.')

        self.stdout.write(self.style.SUCCESS('Roles & permissions seeded.'))
