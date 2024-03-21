from setuptools import setup, find_packages

setup(
    name='backporter',
    version='0.1.0',
    py_modules=['backport'],
    install_requires=[
        'Click',
    ],
    packages=find_packages(),
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'backporter = src.commands.main:cli',
        ],
    },
)