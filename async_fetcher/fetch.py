import asyncio
import json
import os
import typing as t
import aiohttp

from collections import OrderedDict
from furl import furl

from aiohttp.client_exceptions import ClientOSError

from asyncio import TimeoutError

from aiohttp.formdata import FormData

from async_fetcher.exceptions import AsyncFetchReceiveError, AsyncFetchNetworkError
from async_fetcher.fetch_result import FetchResult
from async_fetcher.utils import TCPConnectorMixIn, get_or_create_event_loop, IMPORT_EXCEPTION_NAMES

# try to use drf encoder first
try:
    from rest_framework.utils.encoders import JSONEncoder
except Exception as _e:  # ImportError, django.core.exceptions.ImproperlyConfigured
    if _e.__class__.__name__ in IMPORT_EXCEPTION_NAMES:
        from json import JSONEncoder
    else:
        raise

try:
    from django.conf import settings

    DEV_SKIP_RETRIES = settings.DEBUG
except Exception as _e:  # ImportError, django.core.exceptions.ImproperlyConfigured
    if _e.__class__.__name__ in IMPORT_EXCEPTION_NAMES:
        DEV_SKIP_RETRIES = bool(int(os.environ.get('DEV_SKIP_RETRIES', '0')) or 0)
    else:
        raise

dict_or_none = t.Union[t.Dict, None]
str_or_none = t.Union[str, None]
float_or_none = t.Union[float, None]

receive_error_class_type = t.Union[t.Type[AsyncFetchReceiveError], t.Type[Exception]]
network_error_class_type = t.Union[t.Type[AsyncFetchNetworkError], t.Type[Exception]]


class AsyncFetch(TCPConnectorMixIn):
    def __init__(self,
                 task_map: dict,
                 timeout: int = 10,
                 num_retries: int = 0,
                 retry_timeout: float = 1.0,
                 service_name: str = 'api',
                 cafile: str = None,
                 loop: t.Optional[asyncio.AbstractEventLoop] = None,
                 tcp_connector: t.Union[aiohttp.TCPConnector, None] = None,
                 keepalive_timeout: int = 60,
                 receive_error_class: receive_error_class_type = AsyncFetchReceiveError,
                 network_error_class: network_error_class_type = AsyncFetchNetworkError):
        """
        :param task_map: dict, task bundle mapping like {'task_name': <task_bundle>}
        :param timeout: int, request timeout
        :param num_retries: int, max retry count before exception rising
        :param retry_timeout: float, wait before retry
        :param service_name: str, service name label for verbose logging
        :param cafile: certificate
        :param loop: asyncio.AbstractEventLoop
        :param tcp_connector: aiohttp.TCPConnector
        :param keepalive_timeout: int, keepalive timeout for TCPConnector created __internally__
        :param receive_error_class: Error class for receive exception handling, default is AsyncFetchReceiveError
        :param network_error_class: Error class for network exception handling, default is AsyncFetchReceiveError
        """
        self.task_map = OrderedDict(task_map.items())
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

        self.receive_error_class = receive_error_class
        self.network_error_class = network_error_class

    @staticmethod
    def mk_task(url: str,
                method: str = 'get',
                data: t.Any = None,  # JSON serializable value
                headers: dict_or_none = None,
                api_key: str_or_none = '',

                response_type: str = 'json',
                language_code: str_or_none = None,
                timeout: float_or_none = None,
                query: dict_or_none = None,
                do_not_wait: bool = False,
                json_encoder: JSONEncoder = JSONEncoder,
                num_retries: int = -1,
                fail_silently: bool = False,
                autodetect_content_type: bool = True) -> dict:
        """
        Creates task bundle dict with all request-specific necessary information.
        :param fail_silently: bool, do not raise exceptions, default is False;
            for test purpose, do not use in production
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

        # Do not serialize FormData instances
        if data and not isinstance(data, (bytes, str, FormData)):
            data = json.dumps(data, cls=json_encoder)

        if api_key:
            headers['api-key'] = api_key

        if language_code:
            headers['accept-language'] = language_code

        bundle = {
            'method': method.lower(),
            'url': url,
            'data': data or {},
            'headers': headers,
            'response_type': response_type.lower(),
            'timeout': timeout,
            'do_not_wait': do_not_wait,
            'num_retries': num_retries,
            'fail_silently': fail_silently,
        }
        return bundle

    def get_client_session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(
            connector=self.get_tcp_connector(),
            connector_owner=self._connector_owner
        )

    async def fetch(self, session: aiohttp.ClientSession, bundle: dict) -> FetchResult:
        """
        Runs HTTP request asynchronously.
        :param session: instance of aiohttp.ClientSession
        :param bundle: dict, `AsyncFetch.mk_task()` return dict
        :return: FetchResult, resulting namedtuple with response headers, content and status.
        """
        aio_bundle = bundle.copy()
        method, url = aio_bundle.pop('method', 'get'), aio_bundle.pop('url')
        response_type = aio_bundle.pop('response_type')
        timeout = aiohttp.ClientTimeout(total=aio_bundle.pop('timeout') or self.timeout)
        do_not_wait = aio_bundle.pop('do_not_wait')
        fail_silently = aio_bundle.pop('fail_silently')

        # use num_retries from task bundle or AsyncFetcher.max_retries by default
        num_retries = aio_bundle.pop('num_retries')
        if num_retries < 0:
            num_retries = self.max_retries

        if num_retries <= 1:  # whe have to perform request once at least
            num_retries = 1

        max_retries = num_retries
        # save last exception for verbose logging
        last_exception = None

        while num_retries > 0:
            num_retries -= 1

            try:  # catch TimeoutError and AsyncFetchNetworkError
                response = await session.request(method, url, timeout=timeout, **aio_bundle)
                if do_not_wait:  # satisfied with any emptiness
                    await response.release()
                    return FetchResult(result=None, headers=None, status=0)

                # catch all network timeout status codes and retry
                if response.status in [524, 504, 502, 408]:
                    await response.release()
                    raise self.network_error_class(
                        service_name=self.service_name, url=url,
                        response_code=response.status, code=response.status,
                        retries_left=num_retries, max_retries=max_retries
                    )

                # TODO: in case of wrong content-type specified workaround
                if response_type == 'json' and response_type not in response.content_type.lower():
                    gen = getattr(response, 'text')()
                else:
                    gen = getattr(response, response_type)()

                res = await gen
                return FetchResult(result=res, headers=response.headers, status=response.status)

            except (TimeoutError, self.network_error_class, ClientOSError) as e:
                last_exception = e
                if not isinstance(last_exception, self.network_error_class):
                    last_exception = self.network_error_class(
                        service_name=self.service_name, url=url, original_exception=e,
                        retries_left=num_retries, max_retries=max_retries,
                        response_code=0  # no response code for TimeoutError or ClientOSError
                    )
                await asyncio.sleep(self.retry_timeout)

        # reraise last exception (timeout or network error)
        if fail_silently:
            return FetchResult(result=None, headers=None, status=0)

        raise last_exception

    async def _go(self) -> OrderedDict:
        """
        Executes stored task_map asynchronously.
        :return: HTTP Response OrderedDict
            af_obj.go() -> OrderedDict([('profile', {'status': 200, 'result': {some data}}), ...])
        """
        try:
            async with self.get_client_session() as session:
                tasks = [self.fetch(session, bundle) for bundle in self.task_map.values()]
                res = await asyncio.gather(*tasks)
                return OrderedDict(zip(self.task_map.keys(), res))
        except ValueError as e:
            raise self.receive_error_class(service_name=self.service_name, original_exception=e)

    def go(self):
        return self.loop.run_until_complete(self._go())
