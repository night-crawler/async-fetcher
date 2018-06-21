Installation
------------
.. code:: bash

    pip install async-fetcher
    # or
    pip install -e git+https://github.com/night-crawler/async-fetcher.git@#egg=async-fetcher


Sample
------

.. code:: python

    af = AsyncFetch({
        'first': AsyncFetch.mk_task(build_url('request-info')),
        'second': AsyncFetch.mk_task('http://example.com/'),
        'fail': AsyncFetch.mk_task(build_url('404'))
    })
    responses = af.go()

``mk_task`` static method can take this arguments:

.. code:: python

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


.. code:: python

    af0 = AsyncFetch({})
    tcp_connector = af0.get_tcp_connector()

    af1 = AsyncFetch({
        '1': AsyncFetch.mk_task(build_url('request-info')),
        '2': AsyncFetch.mk_task(build_url('request-info')),
    }, tcp_connector=tcp_connector)
    responses = af1.go()
