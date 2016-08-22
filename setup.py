import os

from setuptools import setup, find_packages


def read(*paths):
    """Build a file path from *paths* and return the contents."""
    with open(os.path.join(*paths), 'r') as f:
        return f.read()

setup(

    name='docker-build-tool',
    version='0.5.1',

    description='Build tool for creating Docker Images',

    url='https://github.com/brian-bason/docker-build-tool',
    author='Brian Bason',
    author_email='brianbason@gmail.com',
    classifiers=[],

    packages=find_packages(exclude=['test*']),
    include_package_data=True,

    # List run-time dependencies here.  These will be installed by pip when
    # your project is installed. For an analysis of "install_requires" vs pip's
    # requirements files see:
    # https://packaging.python.org/en/latest/requirements.html
    install_requires=[
        'docker-py>=1.8,<2.0',
        'pyYAML>=3.11,<4.0',
        'enum34>=1.1.6'
    ],

    # List additional groups of dependencies here (e.g. development
    # dependencies). You can install these using the following syntax,
    # for example:
    # $ pip install -e .[dev,test]
    extras_require={
        'test': [
            'coverage==4.0.1',
            'mock==1.3.0',
            'nose==1.3.7',
            'testfixtures==4.3.3'
        ]
    },

    # To provide executable scripts, use entry points in preference to the
    # "scripts" keyword. Entry points provide cross-platform support and allow
    # pip to create the appropriate form of executable for the target platform.
    entry_points={
        'console_scripts': [
            'docker-build=docker_build.__main__:main'
        ]
    }

)
