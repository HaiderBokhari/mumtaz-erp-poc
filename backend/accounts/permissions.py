"""
Role-based access control helpers.

Requirement doc: "Fixed roles-based access control ... Role-based access to
features ... Each role will have create/edit/view/delete/all permissions for
a given feature." We implement that with Django's built-in Group +
Permission machinery (auto-created per model by Django, e.g.
``purchasing.add_purchaseorder``) rather than inventing a parallel system.

``RolePermission`` is a small DRF permission class: it maps the DRF action
(list/retrieve/create/update/destroy) to the equivalent Django permission
codename (view/view/add/change/delete) and checks it against the request
user, which in turn checks their Group memberships. Superusers (and the
Owner group, made superuser-equivalent by the seed command) always pass.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class RolePermission(BasePermission):
    """Generic Django-permission-backed access control for a ViewSet."""

    # Overridden per-viewset via `queryset.model._meta` app_label/model_name.
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if getattr(request.user, 'profile', None) and request.user.profile.is_blocked:
            return False
        if request.user.is_superuser:
            return True

        model = getattr(view.queryset, 'model', None) or view.get_queryset().model
        app_label = model._meta.app_label
        model_name = model._meta.model_name

        action = getattr(view, 'action', None)
        if action in ('list', 'retrieve') or request.method in SAFE_METHODS:
            codename = f'{app_label}.view_{model_name}'
        elif action == 'create':
            codename = f'{app_label}.add_{model_name}'
        elif action in ('update', 'partial_update'):
            codename = f'{app_label}.change_{model_name}'
        elif action == 'destroy':
            codename = f'{app_label}.delete_{model_name}'
        else:
            # Custom @action endpoints (submit/approve/receive/confirm/dispatch/...)
            # all mutate state, so default to requiring "change" rather than the
            # weaker "view" — a view-only role should not be able to trigger them.
            codename = f'{app_label}.change_{model_name}'

        return request.user.has_perm(codename)


class IsWarehouseScoped:
    """
    Mixin for ViewSets whose queryset should be restricted to the
    requesting user's branch/warehouse, unless they belong to a
    branch-unrestricted role (Owner / Distribution Manager have
    profile.warehouse = None, meaning "all branches").
    """

    warehouse_field = 'warehouse'

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser:
            return qs
        profile = getattr(user, 'profile', None)
        if profile and profile.warehouse_id:
            return qs.filter(**{self.warehouse_field: profile.warehouse_id})
        return qs
