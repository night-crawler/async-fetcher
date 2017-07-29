import asyncio
import os
import aiohttp
import json
import time

import typing as t

from aiohttp.client_exceptions import ClientOSError, TimeoutError
from furl import furl
from collections import OrderedDict, namedtuple

from async_fetcher.exceptions import AsyncFetchReceiveError, AsyncFetchNetworkError

# try to use drf encoder first
try:
    from rest_framework.utils.encoders import JSONEncoder
except (ImportError, Exception):  # django.core.exceptions.ImproperlyConfigured
    from json import JSONEncoder

try:
    from django.conf import settings
    DEV_SKIP_RETRIES = settings.DEBUG
except (ImportError, Exception):  # django.core.exceptions.ImproperlyConfigured
    DEV_SKIP_RETRIES = bool(int(os.environ.get('DEV_SKIP_RETRIES', '0')) or 0)


from async_fetcher.utils import TCPConnectorMixIn

FetchResult = namedtuple('FetchResult', ['headers', 'result', 'status'])


dict_or_none = t.Union[t.Dict, None]
str_or_none = t.Union[str, None]
float_or_none = t.Union[float, None]


def get_or_create_event_loop() -> t.Union[asyncio.BaseEventLoop, asyncio.AbstractEventLoop]:
    try:
        loop = asyncio.get_event_loop()
        return loop
    except (RuntimeError, AssertionError):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


class AsyncFetch(TCPConnectorMixIn):

    def __init__(self,
                 task_map: dict, timeout: int=10, num_retries: int=0,
                 retry_timeout: float=1.0,
                 service_name: str='api',
                 cafile: str=None,
                 loop: t.Union[asyncio.BaseEventLoop, asyncio.AbstractEventLoop, None] = None,
                 tcp_connector: t.Union[aiohttp.TCPConnector, None]=None,
                 keepalive_timeout: int=60):
        """
        :param task_map: dict, task bundle mapping like {'task_name': <task_bundle>}
        :param timeout: int, request timeout
        :param num_retries: int, max retry count before exception rising
        :param retry_timeout: float, wait before retry
        :param service_name: str, service name label for verbose logging
        :param keepalive_timeout: int, keepalive timeout for TCPConnector created __internally__
        """
        self.task_map = OrderedDict(task_map.items())
        self.loop = get_or_create_event_loop()
        self.timeout = timeout
        self.num_retries = num_retries
        self.max_retries = num_retries
        self.retry_timeout = retry_timeout
        self.service_name = service_name

        self.cafile = cafile
        self.loop = loop or get_or_create_event_loop()
        self._tcp_connector = tcp_connector
        self._connector_owner = not bool(tcp_connector)

        # keepalive_timeout for __internally__ created connector
        self.keepalive_timeout = keepalive_timeout

    @staticmethod
    def mk_task(url: str,
                method: str = 'get',
                data: t.Any = None,  # JSON serializable value
                headers: dict_or_none = None,
                api_key: str_or_none= '',

                response_type: str = 'json',
                language_code: str_or_none = None,
                timeout: float_or_none = None,
                query: dict_or_none = None,
                do_not_wait: bool = False,
                json_encoder: JSONEncoder = JSONEncoder,
                num_retries: int=-1,
                autodetect_content_type: bool = True) -> dict:
        """
        Creates task bundle dict with all request-specific necessary information.
        :param num_retries: int, *optional*, default is -1; -1 - no retries; 0 - use AsyncFetch.num_retries
        :param autodetect_content_type: if no `content-type` header was specified, set `content-type` as
            `application/json` for dict, and `text/html` otherwise; default is True
        :param json_encoder: JSONEncoder, *optional*, JSON encoder for data serialization
            tries to use DRF's encoder, or default JSONEncoder from json package; default is JSONEncoder
        :param url: str, *required*, url address
        :param api_key: str, optional API key passed into HEADERS dict
        :param data: dict, *optional*, request data. Default is None,
        :param method: str, *optional*, HTTP request method. Default is True.
        :param headers: dict, *optional*, optional HTTP headers
        :param response_type: str, *optional*, HTTP response type
            (in fact it's just aiohttp's method name, i.e. text, or json); default is 'json'
        :param language_code: str, set `accept-language` header
        :param timeout: float, *optional*, time to wait for response in seconds before TimeoutError
        :param query: dict, *optional*, url get arguments
        :param do_not_wait: bool, *optional*, fail silently with no retries and empty resultset

        :return: dict, task bundle

        AsyncFetch.mk_task('http://cas/msa/cas/v1/users/user/', api_key='key', data={},  method='get',
                           headers={'content-type': 'application/json'}, response_type='json') ->
        {
            'method': 'get'
            'url': 'http://cas/msa/cas/v1/users/user/?api_key=key',
            'data': {},
            'headers': {'content-type': 'application/json'},
            'response_type': 'json'
        }
        """
        if query:
            url = furl(url).set(query).url

        headers = headers or {}

        # if no content-type specified and autodetect flag was set
        if autodetect_content_type and 'content-type' not in headers:
            if isinstance(data, dict):
                headers['content-type'] = 'application/json'
            elif isinstance(data, str):
                headers['content-type'] = 'text/html'

        if data and not isinstance(data, (bytes, str)):
            data = json.dumps(data, cls=json_encoder)

        if api_key:
            headers['api-key'] = api_key

        if language_code:
            headers['accept-language'] = language_code

        bundle = {
            'method': method,
            'url': url,
            'data': data or {},
            'headers': headers,
            'response_type': response_type,
            'timeout': timeout,
            'do_not_wait': do_not_wait,
            'num_retries': num_retries
        }
        return bundle

    def get_client_session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(
            connector=self.get_tcp_connector(),
            connector_owner=self._connector_owner
        )

    @asyncio.coroutine
    def fetch(self, session: aiohttp.ClientSession, bundle: dict) -> FetchResult:
        """
        Runs HTTP request asynchronously. Coroutine task.
        :param session: instance of aiohttp.ClientSession
        :param bundle: dict, `AsyncFetch.mk_task()` return dict
        :return: FetchResult, resulting namedtuple with response headers, content and status.
        """
        aio_bundle = bundle.copy()
        method, url = aio_bundle.pop('method', 'get'), aio_bundle.pop('url')
        response_type = aio_bundle.pop('response_type')
        timeout = aio_bundle.pop('timeout') or self.timeout
        do_not_wait = aio_bundle.pop('do_not_wait')

        # use num_retries from task bundle or AsyncFetcher.max_retries by default
        num_retries = aio_bundle.pop('num_retries', self.max_retries)
        if num_retries <= 1:  # whe have to perform request once at least
            num_retries = 1

        max_retries = num_retries
        # save last exception for verbose logging
        last_exception = None

        while num_retries > 0:
            num_retries -= 1

            try:  # catch TimeoutError and AsyncFetchNetworkError
                with aiohttp.Timeout(timeout):
                    response = yield from session.request(method, url, **aio_bundle)
                    if do_not_wait:  # satisfied with any emptiness
                        yield from response.release()
                        return FetchResult(result=None, headers=None, status=0)

                    # catch all network timeout status codes and retry
                    if response.status in [524, 504, 502, 408]:
                        yield from response.release()
                        raise AsyncFetchNetworkError(
                            service_name=self.service_name, url=url,
                            response_code=response.status, code=response.status,
                            retries_left=num_retries, max_retries=max_retries
                        )

                    # TODO: in case of wrong content-type specified workaround
                    if response_type == 'json' and response_type not in response.content_type.lower():
                        gen = getattr(response, 'text')()
                    else:
                        gen = getattr(response, response_type)()

                    res = yield from gen
                    return FetchResult(result=res, headers=response.headers, status=response.status)

            except (TimeoutError, AsyncFetchNetworkError, ClientOSError) as e:
                last_exception = e
                if not isinstance(last_exception, AsyncFetchNetworkError):
                    last_exception = AsyncFetchNetworkError(
                        service_name=self.service_name, url=url, original_exception=e,
                        retries_left=num_retries, max_retries=max_retries,
                        response_code=0  # no response code for TimeoutError or ClientOSError
                    )
                yield from asyncio.sleep(self.retry_timeout)

        # reraise last exception (timeout or network error)
        raise last_exception

    def go(self) -> OrderedDict:
        """
        Executes stored task_map asynchronously.
        :return: HTTP Response OrderedDict
            af_obj.go() -> OrderedDict([('profile', {'status': 200, 'result': {some data}}), ...])
        """
        try:
            with self.get_client_session() as session:
                tasks = [self.fetch(session, bundle) for bundle in self.task_map.values()]
                res = self.loop.run_until_complete(asyncio.gather(*tasks))
                return OrderedDict(zip(self.task_map.keys(), res))
        except ValueError as e:
            raise AsyncFetchReceiveError(service_name=self.service_name, original_exception=e)
