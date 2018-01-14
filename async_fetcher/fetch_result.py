import typing as t


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

    def __repr__(self) -> str:
        return '<FetchResult: status={0.status}, headers={0.headers}, result={0.result}>'.format(self)

    def __bool__(self) -> bool:
        return self.is_success()

    __nonzero__ = __bool__

    def __eq__(self, other: 'FetchResult') -> bool:
        return self.status == other.status and \
               self.headers == self.headers and \
               self.result == self.result

    def is_jsonrpc(self) -> bool:
        return isinstance(self._result, dict) and \
               'jsonrpc' in self._result

    def is_success(self) -> bool:
        return 200 <= self.status <= 299

    def is_client_error(self) -> bool:
        return 400 <= self.status <= 499

    def is_informational(self) -> bool:
        return 100 <= self.status <= 199

    def is_redirect(self) -> bool:
        return 300 <= self.status <= 399

    def is_server_error(self) -> bool:
        return 500 <= self.status <= 599

    @property
    def status(self) -> int:
        if self.is_jsonrpc() and 'error' in self._result:
            return self._result['error']['code']
        return self._status

    @property
    def result(self):
        return self._result
