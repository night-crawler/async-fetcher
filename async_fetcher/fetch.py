import asyncio
import os
import aiohttp
import json
import time

import typing as t

from aiohttp.client_exceptions import ClientOSError, TimeoutError
from furl import furl
from collections import OrderedDict, namedtuple

# try to use drf encoder first
try:
    from rest_framework.utils.encoders import JSONEncoder
except ImportError:
    from json import JSONEncoder

# suppose drf is installed
try:
    from rest_framework.exceptions import APIException
except ImportError:
    class APIException(Exception):
        pass

try:
    from django.utils.translation import ugettext_lazy as _
except ImportError:
    def _(raw_str: str):
        return raw_str

try:
    from django.conf import settings
    DEV_SKIP_RETRIES = settings.DEBUG
except ImportError:
    DEV_SKIP_RETRIES = bool(int(os.environ.get('DEV_SKIP_RETRIES', '0')) or 0)


from async_fetcher.utils import TCPConnectorMixIn

FetchResult = namedtuple('FetchResult', ['headers', 'result', 'status'])


dict_or_none = t.Union[t.Dict, None]


def get_or_create_event_loop() -> t.Union[asyncio.BaseEventLoop, asyncio.AbstractEventLoop]:
    try:
        loop = asyncio.get_event_loop()
        return loop
    except (RuntimeError, AssertionError):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


class AsyncFetch(TCPConnectorMixIn):
    CONNECTION_ERROR_TEMPLATE = _('Failed to connect `{0}` service. Original exception: `{1}`.')
    RECEIVE_ERROR_TEMPLATE = _('Failed to receive data from `{0}` service. Original exception: `{1}`.')

    def __init__(self,
                 task_map: dict, timeout: int=10, num_retries: int=0,
                 retry_timeout: float=1.0,
                 service_name: str='api',
                 cafile: str=None,
                 loop: t.Union[asyncio.BaseEventLoop, asyncio.AbstractEventLoop, None] = None,
                 tcp_connector: t.Union[aiohttp.TCPConnector, None]=None):
        """
        Инициализация экземпляра класса.
        :param task_map: dict, пул задач
        :param timeout: int, время ожидания
        :param num_retries: int, кол-во попыток сделать запрос к API после таймаута
        :param retry_timeout: float, число секунд перед попыткой отправить заново
        :param service_name: str, отображаемая метка сервиса в случае ошибки
        """
        self.task_map = OrderedDict(task_map.items())
        self.loop = get_or_create_event_loop()
        self.timeout = timeout
        self.num_retries = num_retries
        self.retry_timeout = retry_timeout
        self.service_name = service_name

        self.cafile = cafile
        self.loop = loop or get_or_create_event_loop()
        self._tcp_connector = tcp_connector
        self._connector_owner = not bool(tcp_connector)

    @staticmethod
    def mk_task(url: str,
                method: str = 'get',
                data=None,
                headers: dict_or_none = None,
                api_key: str= '',

                response_type: str='json',
                language_code: str=None,
                timeout: float=None,
                query: dict_or_none=None,
                do_not_wait: bool=False,
                json_encoder: JSONEncoder=JSONEncoder,
                autodetect_content_type: bool=True) -> dict:
        """
        Creates task bundle dict with all request-specific necessary information.
        :param autodetect_content_type:
        :param json_encoder:
        :param url: str, url address
        :param api_key: str, optional API key in HEADERS
        :param data: dict, optional data
        :param method: str, метод запроса HTTP
        :param headers: dict, optional HTTP headers
        :param response_type: str, тип ответа HTTP
        :param language_code: str, add accept-language header
        :param timeout: float, time to wait for response, or TimeoutError
        :param query: dict, url get arguments
        :param do_not_wait: bool, ожидать ответа или отдавать пустой результат после минимального таймаута
        :return: task as a dict, атрибуты задачи словарём

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

        # присваиваем значение только если `content-type` не был определён
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
        Асинхронно выполняет работу по выполнению HTTP запроса и возвращает его результат.
        Сoroutine task.
        :param session: obj of aiohttp.ClientSession, контекст (интерфейс) для работы с HTTP запросами
        :param bundle: dict, данные для выполнения запроса
        :return: FetchResult, namedtuple с результатом, заголовками и статусом запроса.
        """
        aio_bundle = bundle.copy()
        method, url = aio_bundle.pop('method', 'get'), aio_bundle.pop('url')
        response_type = aio_bundle.pop('response_type')
        timeout = aio_bundle.pop('timeout') or self.timeout
        do_not_wait = aio_bundle.pop('do_not_wait')

        with aiohttp.Timeout(timeout):
            response = yield from session.request(method, url, **aio_bundle)
            if do_not_wait:
                yield from response.release()
                return FetchResult(result=None, headers=None, status=0)

            if response.status == 502:
                yield from response.release()
                raise TimeoutError

            # if response_type == 'json' and response_type not in response.content_type:
            #     yield from response.release()
            #     res = None
            # else:
            gen = getattr(response, response_type)()
            res = yield from gen
            return FetchResult(result=res, headers=response.headers, status=response.status)

    def go(self) -> OrderedDict:
        """
        Асинхронно выполняет задачи из пула задач.
        :return: OrderedDict of HTTP Response,
        отсортированный словарь где ключи - названия задач и значения - результаты выполнения запросов.

        af_obj.go() -> OrderedDict([('profile', {'status': 200, 'result': {some data}}), ...])
        """
        try:
            with self.get_client_session() as session:
                tasks = [self.fetch(session, bundle) for bundle in self.task_map.values()]
                res = self.loop.run_until_complete(asyncio.gather(*tasks))
                return OrderedDict(zip(self.task_map.keys(), res))
        except (ClientOSError, TimeoutError) as e:
            # если есть лимит попыток в релизе, пробуем запустить ещё раз
            if self.num_retries > 0 and not DEV_SKIP_RETRIES:
                self.num_retries -= 1
                time.sleep(self.retry_timeout)
                return self.go()
            else:
                raise APIException(str(self.CONNECTION_ERROR_TEMPLATE).format(self.service_name, str(e)))
        except ValueError as e:
            raise APIException(str(self.RECEIVE_ERROR_TEMPLATE).format(self.service_name, str(e)))
