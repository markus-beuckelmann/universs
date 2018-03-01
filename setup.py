#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from setuptools import setup

with open('requirements.txt', 'r') as f:

    lines = f.readlines()
    requirements = [line.strip() for line in lines]

setup(
    name = 'universs',
    packages = ['universs'],
    include_package_data = True,
    install_requires = requirements
)
