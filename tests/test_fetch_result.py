import pytest

from async_fetcher.fetch import FetchResult

pytestmark = pytest.mark.fetch_result

JSONRPC_RESULT_OK = {
    'id': 'some-unique-id',
    'jsonrpc': '2.0',
    'result': {'pong': 'ok'},
}
JSONRPC_RESULT_FAIL = {
    'id': 'some-unique-id',
    'jsonrpc': '2.0',
    'error': {
        'code': 500,
        'data': None,
        'message': 'OtherError: "some exception detail"',
        'name': 'OtherError'
    },
}


def test_init():
    fr = FetchResult(status=200, result={'res': 'res'}, headers={'headers': 'headers'})

    assert fr.status == 200
    assert fr.result == {'res': 'res'}
    assert fr.headers == {'headers': 'headers'}


def test_repr():
    fr = FetchResult(status=200, result='result', headers={'header': 'test'})
    assert fr.__repr__() == '<FetchResult: status=200, headers={\'header\': \'test\'}, result=result>'


def test_bool_expression():
    fr1 = FetchResult(status=200)
    assert fr1

    fr2 = FetchResult(status=500)
    assert not fr2

    fr3 = FetchResult(status=200, result=JSONRPC_RESULT_FAIL)
    assert not fr3

    fr3 = FetchResult(status=500, result=JSONRPC_RESULT_FAIL)
    assert not fr3


def test_is_jsonrpc():
    fr = FetchResult(status=200, result=JSONRPC_RESULT_OK)
    assert fr.is_jsonrpc()


def test_jsonrpc_fail_get_status_code():
    fr = FetchResult(status=200, result=JSONRPC_RESULT_FAIL)

    assert fr.is_jsonrpc()
    assert fr.status == 500


def test_result_is_not_iterable():
    fr = FetchResult(status=200, result=1)
    assert not fr.is_jsonrpc()

    # make it safer =)
    fr = FetchResult(status=200, result='')
    assert not fr.is_jsonrpc()

    fr = FetchResult(status=200, result=())
    assert not fr.is_jsonrpc()
