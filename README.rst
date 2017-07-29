Installation
------------
.. code:: bash
    pip install async-fetcher


Sample
------

.. code:: python
    af = AsyncFetch({
        'first': AsyncFetch.mk_task(build_url('request-info')),
        'second': AsyncFetch.mk_task(build_url('request-info')),
        'fail': AsyncFetch.mk_task(build_url('404'))
    })
    responses = af.go()
