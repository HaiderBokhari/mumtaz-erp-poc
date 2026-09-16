from django.contrib.auth.models import Group, User
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from .permissions import RolePermission
from .serializers import GroupSerializer, MeSerializer, UserSerializer


class MeView(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        return Response(MeSerializer(request.user).data)


class UserViewSet(viewsets.ModelViewSet):
    """
    Admin-only: create/edit/block users and assign roles.
    Requirement doc, Access Control #3: "Administrator will be able to
    create, edit, and block users, assign or change their role."
    """
    queryset = User.objects.select_related('profile').prefetch_related('groups').order_by('username')
    serializer_class = UserSerializer
    permission_classes = [IsAdminUser]
    filterset_fields = ['is_active', 'groups']
    search_fields = ['username', 'first_name', 'last_name', 'email']

    @action(detail=True, methods=['post'])
    def block(self, request, pk=None):
        user = self.get_object()
        user.profile.is_blocked = True
        user.profile.save()
        user.is_active = False
        user.save()
        return Response(UserSerializer(user).data)

    @action(detail=True, methods=['post'])
    def unblock(self, request, pk=None):
        user = self.get_object()
        user.profile.is_blocked = False
        user.profile.save()
        user.is_active = True
        user.save()
        return Response(UserSerializer(user).data)


class GroupViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only list of the fixed roles, for populating role pickers in the UI."""
    queryset = Group.objects.all().order_by('name')
    serializer_class = GroupSerializer
    permission_classes = [IsAuthenticated]
