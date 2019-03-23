#!/usr/bin/env python
# encoding=utf-8
from setuptools import setup
import os, sys

setup(name='sdbot',
      version='1.0.0',
      author='Dan Michael O. Heggø',
      author_email='danmichaelo@gmail.com',
      url='https://github.com/danmichaelo/sdbot',
      license='MIT',
      packages=['sdbot'],
      entry_points={
        'console_scripts': [
            'sdbot = sdbot.sdbot:main',
        ],
      },
      classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
      ],
      install_requires=[
        'numpy',
        'flask',
        'flup',
        'mwtemplates',
        'mwclient',
        'rollbar',
        'requests',
        'python-dotenv',
      ]
      )
