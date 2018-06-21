import ssl
import aiohttp
import asyncio


# if sys.version_info >= (3, 5):
#     EventLoopType = t.Union[asyncio.BaseEventLoop, asyncio.AbstractEventLoop]
# else:
#     EventLoopType = asyncio.AbstractEventLoop


def get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    try:
        loop = asyncio.get_event_loop()
        return loop
    except (RuntimeError, AssertionError):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


# noinspection PyUnresolvedReferences
class TCPConnectorMixIn:

    # noinspection PyUnresolvedReferences
    def get_tcp_connector(self) -> aiohttp.TCPConnector:
        if not self._connector_owner:
            return self._tcp_connector

        # return valid connector
        if self._tcp_connector and not self._tcp_connector.closed:
            return self._tcp_connector
        # create ssl context if no valid connector is present
        ssl_context = ssl.create_default_context(cafile=self.cafile)

        # memoize tcp_connector for reuse
        # noinspection PyAttributeOutsideInit
        self._tcp_connector = aiohttp.TCPConnector(
            loop=self.loop,
            ssl_context=ssl_context,
            keepalive_timeout=self.keepalive_timeout,
        )
        return self._tcp_connector

    def __del__(self):
        """
        Properly close owned connector on exit
        :return:
        """
        if self._connector_owner:
            connector = self.get_tcp_connector()
            not connector.closed and connector.close()


IMPORT_EXCEPTION_NAMES = ['ImportError', 'ImproperlyConfigured', 'ModuleNotFoundError']
