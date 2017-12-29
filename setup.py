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
    description='aiohttp wrapper to handle multiple api calls at a time',
    long_description=long_description,
    classifiers=[
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'License :: OSI Approved :: MIT License',
    ],
    requires=['aiohttp', 'furl']
)
