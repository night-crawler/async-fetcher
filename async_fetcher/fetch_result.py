import typing as t

from rest_framework import status as drf_status


class FetchResult:
    """
    It replaces this:
        FetchResult = namedtuple('FetchResult', ['headers', 'result', 'status'])
    """
    def __init__(self, 
                 headers: t.Optional[dict]=None, 
                 result: t.Optional[t.Any]=None,
                 status: t.Optional[int]=None):
        self.headers = headers
        self._status = status
        self._result = result or {}

    def __repr__(self):
        return '<FetchResult: status={0.status}, headers={0.headers}, result={0.result}>'.format(self)

    def __bool__(self):
        return self.is_success()

    __nonzero__ = __bool__

    def __eq__(self, other: 'FetchResult'):
        return self.status == other.status and \
               self.headers == self.headers and \
               self.result == self.result

    def is_jsonrpc(self):
        return isinstance(self._result, dict) and \
               'jsonrpc' in self._result

    def is_success(self):
        return drf_status.is_success(self.status)

    def is_client_error(self):
        return drf_status.is_client_error(self.status)

    def is_informational(self):
        return drf_status.is_informational(self.status)

    def is_redirect(self):
        return drf_status.is_redirect(self.status)

    def is_server_error(self):
        return drf_status.is_server_error(self.status)

    @property
    def status(self):
        if self.is_jsonrpc() and 'error' in self._result:
            return self._result['error']['code']
        return self._status

    @property
    def result(self):
        return self._result
