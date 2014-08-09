#!/usr/bin/env python3
# coding: utf-8

"Wot Ideas Unit Tests."

import bson
import motor
import pytest
import requests
import tornado.gen
import tornado.ioloop

import wotideas


# Simple tests.
# ------------------------------------------------------------------------------

def test_encode_object_id():
    "Tests encode_object_id and decode_object_id."
    object_id = bson.objectid.ObjectId()
    assert wotideas.decode_object_id(wotideas.encode_object_id(object_id)) == object_id


# Web handlers.
# ------------------------------------------------------------------------------

@pytest.fixture(scope="session")
def session():
    "Gets web session."
    return requests.Session()


@pytest.fixture(scope="session")
def url():
    "Gets website URL."
    return "http://localhost:{}".format(wotideas.HTTP_PORT)


def test_home(session, url):
    session.get(url)
