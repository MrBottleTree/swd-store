import logging
import threading
from user_agents import parse

logger = logging.getLogger('core.access')


class AccessLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Grab cheap session data synchronously before the thread
        user_data = request.session.get('user_data') or {}
        email = user_data.get('email', '')
        name = user_data.get('name', '')
        method = request.method
        path = request.get_full_path()
        ua_string = request.META.get('HTTP_USER_AGENT', '')
        ip = self._get_client_ip(request)
        status = response.status_code

        threading.Thread(
            target=self._log,
            args=(email, name, method, path, ua_string, ip, status),
            daemon=True,
        ).start()

        return response

    @staticmethod
    def _get_client_ip(request):
        return (
            request.META.get('HTTP_CF_CONNECTING_IP')
            or request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            or request.META.get('REMOTE_ADDR', '')
        )

    @staticmethod
    def _log(email, name, method, path, ua_string, ip, status):
        import django.db
        try:
            person_id = campus = None
            if email:
                from core.models import Person
                person = Person.objects.filter(email=email).values('id', 'campus').first()
                if person:
                    person_id = person['id']
                    campus = person['campus']

            ua = parse(ua_string)
            browser = f"{ua.browser.family} {ua.browser.version_string}".strip()
            os_info = f"{ua.os.family} {ua.os.version_string}".strip()
            device = ua.device.family

            logger.info(
                '%s %s %s | user="%s" <%s> id=%s campus=%s | %s | os=%s device=%s | ip=%s',
                status, method, path,
                name or '-', email or 'anonymous',
                person_id if person_id is not None else '-',
                campus or '-',
                browser, os_info, device,
                ip,
            )
        except Exception:
            pass
        finally:
            django.db.connection.close()
