import aiohttp
import ssl
import typing as t

bytes_or_str = t.Union[str, bytes]


class TCPConnectorMixIn:

    def get_tcp_connector(self) -> aiohttp.TCPConnector:
        if self._connector_owner:
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

        return self._tcp_connector

    def __del__(self):
        """
        Properly close owned connector on exit
        :return:
        """
        if self._connector_owner:
            connector = self.get_tcp_connector()
            not connector.closed and connector.close()

