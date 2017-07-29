import json
import asyncio
from aiohttp import web
from aiohttp.web_request import Request


# noinspection PyUnusedLocal
async def home(request: Request):
    return web.Response(text='Home')


async def request_info(request: Request):
    bundle = {
        'cookies': dict(request.cookies.items()),
        'headers': dict(request.headers.items()),
        'query': dict(request.query.items()),
        'query_string': request.query_string,
        'charset': request.charset,
        'method': request.method
    }
    b_content = await request.read()
    try:
        encoding = request.charset or 'utf-8'
        t_content = b_content.decode(encoding)
    except:
        t_content = None

    if t_content is None:
        content = 'binary'
    else:
        try:
            content = json.loads(t_content)
        except:
            content = t_content

    bundle['content'] = content
    return web.json_response(bundle)


async def sleep_time(request: Request):
    st = float(request.match_info['sleep'])
    print('sleeping', st)
    await asyncio.sleep(st)
    return web.json_response({'slept': st})


# noinspection PyUnusedLocal
async def view502(request: Request):
    message = 'GTFO. Gateway Took Fantastic Outing.'
    print(message)
    return web.Response(text=message, status=502)


if __name__ == '__main__':
    app = web.Application()
    app.router.add_get('/', home)
    app.router.add_route('*', '/request-info', request_info)
    app.router.add_route('*', '/502', view502)

    sleep_time_resource = app.router.add_resource('/sleep/{sleep:\d+}')
    sleep_time_resource.add_route('*', sleep_time)

    web.run_app(app, port=21571)
