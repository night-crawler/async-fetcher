Installation
------------
.. code:: bash

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

.. code:: python

    af0 = AsyncFetch({})
    tcp_connector = af0.get_tcp_connector()

    af1 = AsyncFetch({
        '1': AsyncFetch.mk_task(build_url('request-info')),
        '2': AsyncFetch.mk_task(build_url('request-info')),
    }, tcp_connector=tcp_connector)
    responses = af1.go()
