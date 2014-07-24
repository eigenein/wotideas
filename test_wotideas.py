#!/usr/bin/env python3
# coding: utf-8

"Wot Ideas Unit Tests."

import sys; sys.dont_write_bytecode = True

import functools

import motor
import pytest
import tornado.gen
import tornado.ioloop


def ioloop(func):
    "Runs function on Tornado I/O loop."
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        def run():
            func(*args, **kwargs)
        tornado.ioloop.IOLoop.instance().run_sync(run)
    return wrapper


#@ioloop
#@tornado.gen.coroutine
def test_a():
    assert 1
