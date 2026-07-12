"""
Phoenix Core - legacy setup.py shim.

All packaging metadata (name, version, dependencies, optional
dependencies, entry points, classifiers, etc.) lives in pyproject.toml,
which is the single source of truth for packaging configuration.

This file exists only so that tools which still invoke `python setup.py`
directly (rather than a PEP 517 build frontend) continue to work.
"""
from setuptools import setup

setup()
