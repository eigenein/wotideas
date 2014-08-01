#!/usr/bin/env python3
# coding: utf-8

"Wot Ideas Unit Tests."

import bson
import motor
import pytest
import tornado.gen
import tornado.ioloop

import wotideas


# Simple tests.
# ------------------------------------------------------------------------------

def test_encode_object_id():
    "Tests encode_object_id and decode_object_id."
    object_id = bson.objectid.ObjectId()
    assert wotideas.decode_object_id(wotideas.encode_object_id(object_id)) == object_id


# Async tests.
# ------------------------------------------------------------------------------

@pytest.fixture(scope="session")
def run_sync():
    "Gets a function to run another function synchronously."
    return tornado.ioloop.IOLoop.instance().run_sync


@pytest.fixture(scope="session")
def db():
    "Gets initialized database."
    return wotideas.initialize_database("test_wotideas")


@pytest.fixture
def ideas(run_sync, db):
    "Gets ideas collection."
    run_sync(db.ideas.remove)
    return db.ideas
