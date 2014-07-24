#!/usr/bin/env python3
# coding: utf-8

"WoT Ideas Application."

import sys; sys.dont_write_bytecode = True

import argparse
import base64
import collections
import datetime
import http.client
import logging
import os
import pathlib
import pickle

import bson
import motor
import pymongo
import tornado.gen
import tornado.ioloop
import tornado.web

import config


def main(args):
    "Entry point."
    logging.info("Checking environment…")
    check_environment()
    logging.info("Initializing database…")
    db = initialize_database("wotideas")
    logging.info("Initializing application…")
    initialize_web_application(db).listen(8080)
    logging.info("I/O loop is being started.")
    tornado.ioloop.IOLoop.current().start()


def get_argument_parser():
    "Initializes argument parser."
    parser = argparse.ArgumentParser(description=globals()["__doc__"])
    parser.add_argument("--log-file", default=sys.stderr, help="log file", metavar="<file>", type=argparse.FileType("wt"))
    return parser


def configure_logging(args):
    logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO, stream=args.log_file)


def check_environment():
    "Checks for prerequisites."
    if not pathlib.Path("static").exists():
        raise ValueError("not found: static")
    if not pathlib.Path("templates").exists():
        raise ValueError("not found: templates")


def initialize_database(name):
    "Initializes database."
    db = motor.MotorClient()[name]
    db.ideas.ensure_index("freeze_date", pymongo.DESCENDING)
    db.ideas.ensure_index("close_date", pymongo.DESCENDING)
    db.accounts.ensure_index("account_id", pymongo.ASCENDING, unique=True)
    return db


def initialize_web_application(db):
    "Initializes application handlers."
    return tornado.web.Application(
        [
            (r"/(all|closed)?", IndexHandler),
            (r"/login", LogInHandler),
            (r"/logout", LogOutHandler),
            (r"/new", NewHandler),
        ],
        cookie_secret=config.COOKIE_SECRET,
        db=db,
        static_path="static",
        template_path="templates",
        xsrf_cookies=True,
    )


User = collections.namedtuple("User", ["account_id", "nickname"])


class IdEncoder:
    "Encodes an object ID into an URL-safe ID and decodes from it."

    def encode_id(self, object_id):
        "Encodes object ID into an URL-safe ID."
        return base64.urlsafe_b64encode(object_id.binary).decode("ascii")

    def decode_id(self, urlsafe_id):
        "Decodes URL-safe ID into an object ID."
        return bson.objectid.ObjectId(base64.urlsafe_b64decode(urlsafe_id.encode("ascii")))


class RequestHandler(tornado.web.RequestHandler, IdEncoder):
    "Base request handler."
    
    @tornado.gen.coroutine
    def prepare(self):
        self.db = self.settings["db"]
        self.balance = (yield self.get_balance()) if (self.current_user is not None) else None

    def get_current_user(self):
        "Gets current user."
        cookie = self.get_secure_cookie("user")
        return pickle.loads(cookie) if (cookie is not None) else None

    def get_template_namespace(self):
        "Gets default template namespace."
        return {
            "application_id": config.APPLICATION_ID,
            "current_user": self.current_user,
            "is_admin": self.is_admin(),
            "balance": self.balance,
            "encode_id": self.encode_id,
        }

    @tornado.gen.coroutine
    def get_balance(self):
        "Gets current user balance string."
        account = yield self.db.accounts.find_one({"account_id": self.current_user.account_id}, {"cents": True})
        return "{:.2f}".format(account["cents"] / 100.0)

    def is_admin(self):
        "Gets whether the current user is an admin."
        return (self.current_user is not None) and (self.current_user.account_id in config.ADMIN_ID)

    def handle_bad_request(self):
        logging.exception("Invalid request.")
        self.send_error(http.client.BAD_REQUEST)


class IndexHandler(RequestHandler):
    "Home page handler."

    PAGE_SIZE = 10  # idea page size

    @tornado.gen.coroutine
    def get(self, status=None):
        try:
            page = self.parse_arguments(status)
        except ValueError:
            self.handle_bad_request()
        else:
            ideas = yield self.db.ideas.find().\
                sort("freeze_date", pymongo.DESCENDING).\
                skip((page - 1) * self.PAGE_SIZE).\
                limit(self.PAGE_SIZE).\
                to_list(self.PAGE_SIZE)
            self.render("index.html", ideas=ideas, page=page, path=self.request.path)

    def parse_arguments(self, status):
        page = int(self.get_query_argument("page", 1))
        if page < 1:
            raise ValueError("invalid page")
        return page


class LogInHandler(RequestHandler):
    "Log in handler."

    @tornado.gen.coroutine
    def get(self):
        if self.get_query_argument("status") == "ok":
            account_id = int(self.get_query_argument("account_id"))
            self.set_secure_cookie("user", pickle.dumps(User(account_id, self.get_query_argument("nickname"))))
            yield self.create_account(account_id)
        self.redirect(self.get_query_argument("next", "/"))

    @tornado.gen.coroutine
    def create_account(self, account_id):
        "Creates a new account with initial balance."
        try:
            yield self.db.accounts.insert({"account_id": account_id, "cents": 10000})
        except pymongo.errors.DuplicateKeyError:
            pass


class NewHandler(RequestHandler):
    "New idea handler."

    @tornado.gen.coroutine
    def prepare(self):
        yield super().prepare()
        if not self.is_admin():
            self.send_error(http.client.UNAUTHORIZED)

    def get(self):
        "Get the form for a new idea."
        self.render("new.html", _xsrf=self.xsrf_form_html())

    @tornado.gen.coroutine
    def post(self):
        "Posts a new idea."
        try:
            document = self.parse_arguments()
        except (ValueError, tornado.web.MissingArgumentError):
            self.handle_bad_request()
        else:
            document_id = yield self.db.ideas.insert(document)
            self.redirect("/i/{}".format(self.encode_id(document_id)))

    def parse_arguments(self):
        "Parses POST request arguments."
        title, description, freeze_date, freeze_time, close_date, close_time = map(
            self.get_argument, ["title", "description", "freeze-date", "freeze-time", "close-date", "close-time"])
        # Check title and description.
        if not title:
            raise ValueError("empty title")
        if not description:
            raise ValueError("empty description")
        # Split description into paragraphs.
        lines = description.replace("\r\n", "\n").split("\n")
        description = [line for line in lines if line]
        # Parse freeze datetime.
        freeze_datetime = self.parse_datetime(freeze_date, freeze_time)
        if freeze_datetime < datetime.datetime.utcnow():
            raise ValueError("freeze datetime is in past")
        # Parse close datetime.
        close_datetime = self.parse_datetime(close_date, close_time)
        if close_datetime < datetime.datetime.utcnow():
            raise ValueError("close datetime is in past")
        # Check freeze and close datetimes.
        if close_datetime < freeze_datetime:
            raise ValueError("close datetime is earlier than freeze datetime")
        # Build a document.
        return {
            "title": title,
            "description": description,
            "freeze_date": freeze_datetime,
            "close_date": close_datetime,
        }

    def parse_datetime(self, date, time):
        "Parses date and time strings."
        return datetime.datetime.strptime("{} {}".format(date, time), "%Y-%m-%d %H:%M")


class LogOutHandler(RequestHandler):
    "Log out handler."

    def get(self):
        self.clear_cookie("user")
        self.redirect("/")


# Script entry point.
if __name__ == "__main__":
    args = get_argument_parser().parse_args()
    configure_logging(args)
    try:
        sys.exit(main(args) or os.EX_OK)
    except KeyboardInterrupt:
        pass
