#!/usr/bin/env python3
# coding: utf-8

"Wot Ideas Unit Tests."

import motor
import pytest
import tornado.gen
import tornado.ioloop

import wotideas


@pytest.fixture(scope="session")
def run_sync():
    return tornado.ioloop.IOLoop.instance().run_sync


@pytest.fixture(scope="session")
def db():
    return wotideas.initialize_database("test_wotideas")


@pytest.fixture
def ideas(run_sync, db):
    run_sync(db.ideas.remove)
    return db.ideas


def test_a(run_sync, ideas):
    @tornado.gen.coroutine
    def run():
        yield ideas.insert({})
        assert (yield ideas.count()) == 1
    run_sync(run)
