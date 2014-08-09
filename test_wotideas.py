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


# Web handler tests.
# ------------------------------------------------------------------------------

@pytest.fixture(scope="session")
def url():
    "Gets website URL."
    return "http://localhost:{}".format(wotideas.HTTP_PORT)

@pytest.fixture(scope="session")
def anonymous_session():
    "Gets anonymous user session."
    return requests.Session()


@pytest.fixture(scope="session")
def loggedin_session(url):
    "Gets logged in user session."
    session = requests.Session()
    session.get("{}/login?status=ok&account_id=1&nickname=py.test".format(url)).raise_for_status()
    return session


def test_anonymous_home(anonymous_session, url):
    anonymous_session.get(url).raise_for_status()


def test_loggedin_home(loggedin_session, url):
    loggedin_session.get(url).raise_for_status()
