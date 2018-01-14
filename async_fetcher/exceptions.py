import typing as t
import os

from async_fetcher.utils import IMPORT_EXCEPTION_NAMES


def fake_ugettext_lazy(raw_str: str):
    return raw_str


# check if we have an active django environment (not just installed django package)
if os.getenv('DJANGO_SETTINGS_MODULE'):
    from django.utils.translation import ugettext_lazy as _
else:  # django package is not installed
    _ = fake_ugettext_lazy

try:
    from rest_framework.exceptions import APIException
except Exception as e:  # django.core.exceptions.ImproperlyConfigured
    if e.__class__.__name__ in IMPORT_EXCEPTION_NAMES:
        class APIException(Exception):
            default_detail = _('API error occurred.')
            default_code = 'error'

            # noinspection PyUnusedLocal
            def __init__(self, detail=None, code=None):
                self.detail = ''

            def __str__(self):
                return self.detail
    else:
        raise


class AsyncFetchError(APIException):
    def get_template(self):
        raise NotImplementedError()


class AsyncFetchReceiveError(AsyncFetchError):
    def __init__(self, detail=None, code=None,
                 service_name: str = '',
                 original_exception: t.Union[Exception, None] = None):
        self.original_exception = original_exception
        self.detail = str(self.get_template().format(service_name, str(original_exception)))

    def get_template(self):
        return _('Failed to receive data from `{0}` service. Original exception: `{1}`.')


class AsyncFetchNetworkError(AsyncFetchError):
    def __init__(self, detail=None, code=None,
                 service_name: str = '',
                 url: str = '',
                 original_exception: t.Union[Exception, None] = None,
                 retries_left: int = 0,
                 max_retries: int = 0,
                 response_code: int = 500):
        self.original_exception = original_exception
        self.code = code
        self.url = url
        self.retries_left = retries_left
        self.max_retries = max_retries
        self.response_code = response_code

        self.detail = str(self.get_template().format(
            str(service_name),
            str(url),
            str(retries_left),
            str(max_retries),
            str(response_code),
            str(original_exception) or type(original_exception)
        ))

    def get_template(self) -> str:
        return _('Network issue while requesting `{0}` service data from url `{1}` [{2} of {3} left]. '
                 'Last response code: {4}. Original exception: `{5}`.')
