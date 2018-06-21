from setuptools import setup, find_packages
from async_fetcher import __version__

with open('README.rst', 'r') as f:
    long_description = f.read()

setup(
    name='async-fetcher',
    version=__version__,
    packages=find_packages(),
    url='https://github.com/night-crawler/async-fetcher',
    license='MIT',
    author='night-crawler',
    author_email='lilo.panic@gmail.com',
    description='Tiny aiohttp wrapper for http request gathering in sync mode',
    long_description=long_description,
    classifiers=[
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'License :: OSI Approved :: MIT License',
    ],
    python_requires='>=3.6',
    install_requires=['aiohttp>=3.3.2', 'furl']
)
