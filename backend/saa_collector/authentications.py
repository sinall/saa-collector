from rest_framework import authentication
from django.conf import settings


class DevTokenAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        dev_token = request.headers.get('X-Dev-Token')
        settings_token = getattr(settings, 'DEV_MODE_TOKEN', None)

        if dev_token and settings_token and dev_token == settings_token:
            user = type('User', (), {
                'is_authenticated': True,
                'is_active': True,
                'username': 'dev_user',
                'id': 1,
                'is_anonymous': False,
                'pk': 1,
            })()
            # 禁用 CSRF 检查
            setattr(request, '_dont_enforce_csrf_checks', True)
            return (user, None)

        return None
