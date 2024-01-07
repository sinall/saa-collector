import os

try:
    from pip._internal.req import parse_requirements
except ImportError:
    from pip.req import parse_requirements

from setuptools import setup, find_packages

version = {}
with open(os.path.join(os.path.dirname(__file__), "saa_collector", "version.py")) as fp:
    exec(fp.read(), version)

f = open('README.md', 'r')
LONG_DESCRIPTION = f.read()
f.close()

install_reqs = parse_requirements('requirements.txt', session='hack')
reqs = [str(ir.requirement) for ir in install_reqs]

setup(
    name='saa_collector',
    version=version['__version__'],
    description='Collect SAA related data like stock basic data, financial data, etc.',
    long_description=LONG_DESCRIPTION,
    long_description_content_type='text/markdown',
    author='Gao Rui',
    author_email='gaoruinan@163.com',
    url='https://github.com/sinall/saa-collector/',
    license='unlicensed',
    packages=find_packages(exclude=['ez_setup', 'tests*']),
    package_data={'saa_collector': ['templates/*', 'config/*']},
    include_package_data=True,
    install_requires=reqs,
    entry_points={
        'console_scripts': [
            'saa_collector = saa_collector.main:main',
            'saa_collector_scheduler = saa_collector.scheduler:main',
        ],
    },
    data_files=[
        (os.path.join(os.path.expanduser('~'), '.saa_collector', 'config'), [
            'config/saa_collector.yml.example',
            'config/logging.conf.example',
        ]),
    ],
)
