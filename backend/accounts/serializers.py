from django.contrib.auth.models import Group, User
from rest_framework import serializers

from .models import UserProfile


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'name']


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['phone', 'dr_code', 'warehouse', 'supervisor', 'is_blocked']


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer()
    roles = serializers.SerializerMethodField()
    group_ids = serializers.PrimaryKeyRelatedField(
        source='groups', queryset=Group.objects.all(), many=True, write_only=True, required=False
    )

    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email',
            'is_active', 'roles', 'group_ids', 'profile',
        ]

    def get_roles(self, obj):
        return list(obj.groups.values_list('name', flat=True))

    def create(self, validated_data):
        profile_data = validated_data.pop('profile', {})
        groups = validated_data.pop('groups', [])
        password = self.initial_data.get('password') or User.objects.make_random_password()
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        if groups:
            user.groups.set(groups)
        UserProfile.objects.create(user=user, **profile_data)
        return user

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', None)
        groups = validated_data.pop('groups', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if groups is not None:
            instance.groups.set(groups)
        if profile_data:
            UserProfile.objects.update_or_create(user=instance, defaults=profile_data)
        return instance


class MeSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer()
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email',
            'is_superuser', 'roles', 'profile',
        ]

    def get_roles(self, obj):
        return list(obj.groups.values_list('name', flat=True))
