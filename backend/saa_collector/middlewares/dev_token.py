from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class DevTokenMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.dev_token = getattr(settings, 'DEV_MODE_TOKEN', None)
        
        if self.dev_token:
            logger.info("DevTokenMiddleware enabled with DEV_MODE_TOKEN")
        else:
            logger.debug("DevTokenMiddleware enabled but DEV_MODE_TOKEN not set")
    
    def __call__(self, request):
        dev_token = request.headers.get('X-Dev-Token')
        
        if self.dev_token and dev_token == self.dev_token:
            request.user = type('User', (), {
                'is_authenticated': True,
                'is_active': True,
                'username': 'dev_user',
                'id': None,
                'is_anonymous': False,
            })()
            logger.debug(f"Request authenticated via dev token: {request.path}")
        elif not hasattr(request, 'user'):
            request.user = type('User', (), {
                'is_authenticated': False,
                'is_active': False,
                'is_anonymous': True,
            })()
        
        response = self.get_response(request)
        return response
