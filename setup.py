
from setuptools import setup, find_packages
from saa_collector.core.version import get_version

VERSION = get_version()

f = open('README.md', 'r')
LONG_DESCRIPTION = f.read()
f.close()

setup(
    name='saa_collector',
    version=VERSION,
    description='Collect SAA related data like stock basic data, financial data, etc.',
    long_description=LONG_DESCRIPTION,
    long_description_content_type='text/markdown',
    author='Gao Rui',
    author_email='gaoruinan@163.com',
    url='https://github.com/sinall/saa-collector/',
    license='unlicensed',
    packages=find_packages(exclude=['ez_setup', 'tests*']),
    package_data={'saa_collector': ['templates/*']},
    include_package_data=True,
    entry_points="""
        [console_scripts]
        saa_collector = saa_collector.main:main
    """,
)
