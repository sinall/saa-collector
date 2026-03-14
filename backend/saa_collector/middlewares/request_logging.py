import logging
import json

logger = logging.getLogger(__name__)

MAX_RESPONSE_LENGTH = 500


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in ('POST', 'PUT', 'PATCH'):
            try:
                body = self._get_request_body(request)
                logger.info(f"Request: {request.method} {request.path} Body: {body}")
            except Exception:
                pass

        response = self.get_response(request)

        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            self._log_response(request, response)

        return response

    def _get_request_body(self, request):
        if hasattr(request, 'body'):
            try:
                content_type = request.content_type
                if content_type and 'application/json' in content_type:
                    body = request.body.decode('utf-8')
                    if len(body) > MAX_RESPONSE_LENGTH:
                        return body[:MAX_RESPONSE_LENGTH] + '...(truncated)'
                    return body
            except Exception:
                pass
        if hasattr(request, 'data'):
            body = json.dumps(request.data, ensure_ascii=False, default=str)
            if len(body) > MAX_RESPONSE_LENGTH:
                return body[:MAX_RESPONSE_LENGTH] + '...(truncated)'
            return body
        return ''

    def _log_response(self, request, response):
        try:
            content = self._get_response_content(response)
            if content:
                logger.info(f"Response: {request.method} {request.path} Status: {response.status_code} Body: {content}")
        except Exception:
            logger.info(f"Response: {request.method} {request.path} Status: {response.status_code}")

    def _get_response_content(self, response):
        if hasattr(response, 'content'):
            content = response.content
            if isinstance(content, bytes):
                try:
                    content = content.decode('utf-8')
                except UnicodeDecodeError:
                    return None
            if len(content) <= MAX_RESPONSE_LENGTH:
                return content
            return None
        return None
