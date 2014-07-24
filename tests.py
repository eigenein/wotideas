#!/usr/bin/env python3
# coding: utf-8

"Wot Ideas Unit Tests."

import motor
import pytest
import tornado.gen
import tornado.ioloop

import wotideas


@pytest.fixture(scope="session")
def db():
    return wotideas.initialize_database("test_wotideas")


@pytest.fixture
def ideas(db):
    yield db.ideas
    run_sync(db.ideas.remove)


def run_sync(func, *args, **kwargs):
    @tornado.gen.coroutine
    def run():
        yield func(*args, **kwargs)
    tornado.ioloop.IOLoop.instance().run_sync(run)


def test_abc():
    raise Exception()
    assert 0
