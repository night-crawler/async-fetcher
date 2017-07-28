import asyncio
import aiohttp
import json
import time

import typing as t

from aiohttp.client_exceptions import ClientOSError, TimeoutError
from furl import furl
from collections import OrderedDict, namedtuple

from rest_framework.exceptions import APIException
from rest_framework.renderers import JSONRenderer
from django.conf import settings
from django.utils import translation
from django.utils.translation import ugettext_lazy as _


FetchResult = namedtuple('FetchResult', ['headers', 'result', 'status'])


def get_or_create_event_loop():  # -> asyncio.BaseEventLoop:
    """
    Возвращает уже существующий, либо создаёт и возвращает новый объект цикла событий asyncio.
    :return: event_loop object.
    """
    try:
        loop = asyncio.get_event_loop()
        return loop
    except (RuntimeError, AssertionError):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


class AsyncFetch:
    """
    Класс инкапсулирующий работу по асинхронному выполнению HTTP запросов.
    """

    def __init__(self,
                 task_map: dict, timeout: int=10, num_retries: int=0,
                 retry_timeout: float=1,
                 service_name: str=None):
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

    @staticmethod
    def mk_task(url: str, api_key: str=None, data=None, method: str=None,
                headers: dict=None, response_type: str='json', language: str=None, timeout: float=None,
                include_log_data: bool=True, query_params: dict=None, do_not_wait: bool=False) -> dict:
        """
        Создаёт и возвращает задачу для выполнения как словарь.
        :param url: str, url адрес
        :param api_key: str, ключ апи для получения досупа к ресурсу
        :param data: dict, данные для передачи
        :param method: str, метод запроса HTTP
        :param headers: dict, заголовки HTTP
        :param response_type: str, тип ответа HTTP
        :param language: str, значение для accept-language
        :param timeout: float, сколько секунд ждать ответ перед TimeoutError
        :param include_log_data: bool, писать ли в заголовках request.uuid и request.sequence
        :param query_params: dict, словарь GET-аргументов для url
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
        if query_params:
            url = furl(url).set(query_params).url

        language = language or translation.get_language()
        headers = headers or {}
        if 'content-type' not in headers:  # присваиваем значение только если `content-type` не был определён
            if isinstance(data, dict):
                headers['content-type'] = 'application/json'
                data = json.dumps(data, cls=JSONRenderer.encoder_class)
            elif isinstance(data, str):
                headers['content-type'] = 'text/html'

        if api_key:
            headers['api-key'] = api_key

        if language:
            headers['accept-language'] = language

        if include_log_data:
            r = get_current_request()
            if hasattr(r, 'uuid'):
                headers['log-uuid'] = str(r.uuid)
            if hasattr(r, 'sequence'):
                headers['log-sequence'] = r.increment_sequence()

        bundle = {
            'method': method or 'get',
            'url': url,
            'data': data or {},
            'headers': headers,
            'response_type': response_type,
            'timeout': timeout,
            'do_not_wait': do_not_wait,
        }
        return bundle

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
            with aiohttp.ClientSession(loop=self.loop) as session:
                tasks = [self.fetch(session, bundle) for bundle in self.task_map.values()]
                res = self.loop.run_until_complete(asyncio.gather(*tasks))
                return OrderedDict(zip(self.task_map.keys(), res))
        except (ClientOSError, TimeoutError) as e:
            # если есть лимит попыток в релизе, пробуем запустить ещё раз
            if self.num_retries > 0 and not settings.DEBUG:
                self.num_retries -= 1
                time.sleep(self.retry_timeout)
                return self.go()
            else:
                raise APIException(_('Failed to connect %s service.' % self.service_name or 'api'))
        except ValueError as e:
            raise APIException(_('Failed to receive data from %s service.' % self.service_name or 'api'))
