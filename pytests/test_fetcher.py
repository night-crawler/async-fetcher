import os
import time
import pytest

from async_fetcher.exceptions import AsyncFetchNetworkError
from async_fetcher.fetch import AsyncFetch, FetchResult

TEST_SERVER_URL = 'http://127.0.0.1:21571'


def build_url(*path_parts: str) -> str:
    return os.path.join(TEST_SERVER_URL, *path_parts)


# noinspection PyMethodMayBeStatic,PyShadowingNames
class FetcherTest:
    def test_mk_task(self):
        # request_info view in server.py
        url = build_url('request-info')
        tm = AsyncFetch.mk_task(url)

        assert tm == {
            'url': url, 'method': 'get', 'response_type': 'json', 'data': {},
            'timeout': None, 'do_not_wait': False, 'headers': {},
            'num_retries': -1, 'fail_silently': False
        }

        tm = AsyncFetch.mk_task(url, data={'test': 1}, method='post', headers={'X-LOL': 1})
        assert tm == {
            'url': url, 'data': '{"test": 1}', 'headers': {'X-LOL': 1, 'content-type': 'application/json'},
            'timeout': None, 'response_type': 'json', 'do_not_wait': False, 'method': 'post',
            'num_retries': -1, 'fail_silently': False
        }

    def test_fetch(self):
        url = build_url('request-info')
        task_bundle = AsyncFetch.mk_task(url, data='lol')
        af = AsyncFetch({})

        with af.get_client_session() as session:
            task = af.fetch(session, task_bundle)
            response = af.loop.run_until_complete(task)

            assert type(response) == FetchResult
            assert response.status == 200
            assert response.result['content'] == 'lol'

    def test_go(self):
        af = AsyncFetch({
            'first': AsyncFetch.mk_task(build_url('request-info')),
            'second': AsyncFetch.mk_task(build_url('request-info')),
            'fail': AsyncFetch.mk_task(build_url('404'))
        })
        responses = af.go()
        assert responses['fail'].status == 404
        assert responses['first'].status == 200
        assert responses['second'].status == 200

    def test_external_tcp_connector_alive(self):
        # check `AsyncFetch._connector_owner` flag set properly
        af0 = AsyncFetch({})
        tcp_connector = af0.get_tcp_connector()

        def af1__del__isolator():
            af1 = AsyncFetch({
                '1': AsyncFetch.mk_task(build_url('request-info')),
                '2': AsyncFetch.mk_task(build_url('request-info')),
            }, tcp_connector=tcp_connector)
            responses = af1.go()
            assert responses['1'].status == 200

        af1__del__isolator()
        assert tcp_connector.closed is False

    def test_tcp_connector_closed_on__del__(self):
        af0 = AsyncFetch({})
        tcp_connector = af0.get_tcp_connector()
        af0.__del__()
        assert tcp_connector.closed is True

    def test_connection_error(self):
        url = 'http://unknown'
        af = AsyncFetch({'0': AsyncFetch.mk_task(url)})

        with pytest.raises(AsyncFetchNetworkError):
            af.go()

    def test_502(self):
        url = build_url('502')
        af = AsyncFetch({i: AsyncFetch.mk_task(url) for i in range(10)}, num_retries=2, retry_timeout=0.1)

        with pytest.raises(AsyncFetchNetworkError):
            af.go()

    def test_really_async(self):
        task_map = {}

        def f():
            time1 = time.time()
            for i in range(10):
                task_map[len(task_map)] = AsyncFetch.mk_task(build_url('sleep', '0'))
                task_map[len(task_map)] = AsyncFetch.mk_task(build_url('sleep', '1'))

            af = AsyncFetch(task_map, num_retries=10, retry_timeout=0.1)
            af.go()
            time2 = time.time()
            return time2 - time1

        execution_time = f()
        assert execution_time < 2

    def test_fetch_timeout_errors(self):
        url = build_url('502')
        task_bundle = AsyncFetch.mk_task(url)
        af = AsyncFetch({}, num_retries=2, timeout=1, retry_timeout=1)

        with pytest.raises(AsyncFetchNetworkError):
            with af.get_client_session() as session:
                task = af.fetch(session, task_bundle)
                af.loop.run_until_complete(task)

    def test_retry_only_one_url(self):
        task_map = {
            0: AsyncFetch.mk_task(build_url('sleep', '1')),
            1: AsyncFetch.mk_task(build_url('502'), fail_silently=True)
        }
        af = AsyncFetch(task_map, num_retries=10, retry_timeout=0.2)
        res = af.go()
        assert res[1] == FetchResult(None, None, 0)
