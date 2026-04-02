from rest_framework.permissions import BasePermission, IsAuthenticated
from django.conf import settings


class IsAuthenticatedInProduction(BasePermission):
    """
    生产环境要求认证，开发环境允许所有访问
    """
    def has_permission(self, request, view):
        if settings.DEBUG:
            return True
        return IsAuthenticated().has_permission(request, view)
