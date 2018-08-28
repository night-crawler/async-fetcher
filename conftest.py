import pytest

import subprocess
from time import sleep


@pytest.fixture(scope="session", autouse=True)
def start_server(request):
    proc = subprocess.Popen(['python', './tests/server.py'])
    sleep(1)
    request.addfinalizer(proc.kill)
