#!/usr/bin/env python3
# coding: utf-8

"WoT Ideas Application."

import sys; sys.dont_write_bytecode = True

import argparse
import base64
import collections
import datetime
import enum
import http.client
import logging
import operator
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


# Application entry point.
# ------------------------------------------------------------------------------

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


# Initialization.
# ------------------------------------------------------------------------------

def check_environment():
    "Checks for prerequisites."
    if not pathlib.Path("static").exists():
        raise ValueError("not found: static")
    if not pathlib.Path("templates").exists():
        raise ValueError("not found: templates")


def initialize_database(name):
    "Initializes database."
    db = motor.MotorClient()[name]
    db.ideas.ensure_index("close_date", pymongo.DESCENDING)
    db.ideas.ensure_index("freeze_date", pymongo.DESCENDING)
    db.ideas.ensure_index("resolved", pymongo.ASCENDING)
    db.ideas.ensure_index("bets", pymongo.ASCENDING)
    db.events.ensure_index("type", pymongo.ASCENDING)
    db.events.ensure_index("kwargs.account_id", pymongo.ASCENDING, sparse=True)
    return db


def initialize_web_application(db):
    "Initializes application handlers."
    return tornado.web.Application(
        [
            (r"/(all|closed|unresolved)?", IndexRequestHandler),
            (r"/login", LogInRequestHandler),
            (r"/logout", LogOutRequestHandler),
            (r"/new", NewRequestHandler),
            (r"/i/([a-zA-Z0-9_\-\=]+)", IdeaRequestHandler),
            (r"/i/([a-zA-Z0-9_\-\=]+)/bet", BetRequestHandler),
            (r"/balance", BalanceRequestHandler),
        ],
        cookie_secret=config.COOKIE_SECRET,
        db=db,
        static_path="static",
        template_path="templates",
        xsrf_cookies=True,
    )


# Shared objects.
# ------------------------------------------------------------------------------

User = collections.namedtuple("User", ["account_id", "nickname"])


class SystemEventType(enum.Enum):
    "System event type. Do not change these constants."

    LOGGED_IN = 1
    SET_INITIAL_BALANCE = 2
    MADE_BET = 3


# Base request handler.
# ------------------------------------------------------------------------------

def encode_object_id(object_id):
    "Encodes object ID into an URL-safe ID."
    return base64.urlsafe_b64encode(object_id.binary).decode("ascii")


def decode_object_id(urlsafe_id):
    "Decodes URL-safe ID into an object ID."
    try:
        return bson.objectid.ObjectId(base64.urlsafe_b64decode(urlsafe_id.encode("ascii")))
    except bson.errors.InvalidId as exception:
        raise ValueError("invalid ID") from exception


def is_idea_frozen(idea):
    "Gets whether the idea is frozen."
    return datetime.datetime.utcnow() >= idea["freeze_date"]


def is_idea_closed(idea):
    "Gets whether the idea is closed."
    return datetime.datetime.utcnow() >= idea["close_date"]


def format_date(date):
    "Formats date and time."
    return "{date.day}.{date.month:02}.{date.year:04} {date.hour}:{date.minute:02} UTC".format(date=date)


class RequestHandler(tornado.web.RequestHandler):
    "Base request handler."
    
    @tornado.gen.coroutine
    def prepare(self):
        self.db = self.settings["db"]
        # Shared template context.
        self.balance = (yield self.get_balance()) if (self.current_user is not None) else None
        self.now = datetime.datetime.utcnow()
        # Admin stuff.
        self.is_admin = (self.current_user is not None) and (self.current_user.account_id in config.ADMIN_ID)

    def get_current_user(self):
        "Gets current user."
        cookie = self.get_secure_cookie("user")
        return pickle.loads(cookie) if (cookie is not None) else None

    def get_template_namespace(self):
        "Gets default template namespace."
        return {
            "application_id": config.APPLICATION_ID,  # header
            "balance": self.balance,  # header
            "current_user": self.current_user,  # header
            "encode_object_id": encode_object_id,  # index
            "format_date": format_date,
            "is_admin": self.is_admin,
            "is_idea_closed": is_idea_closed,
            "is_idea_frozen": is_idea_frozen,
            "SystemEventType": SystemEventType,
        }

    @tornado.gen.coroutine
    def get_balance(self):
        "Gets current user balance string."
        account = yield self.db.accounts.find_one({"_id": self.current_user.account_id}, {"coins": True})
        return int(account["coins"])

    @tornado.gen.coroutine
    def get_unresolved_idea_count(self):
        "Gets unresolved idea count for the header link."
        return (yield self.db.ideas.find({
            "resolved": False,
            "close_date": {"$lt": self.now}
        }).count())

    @tornado.gen.coroutine
    def log_event(self, event_type, **kwargs):
        "Logs system event."
        yield self.db.events.insert({"type": event_type.value, "kwargs": kwargs})

    def handle_bad_request(self):
        logging.exception("Invalid request.")
        self.send_error(http.client.BAD_REQUEST)


# Index handler.
# ------------------------------------------------------------------------------

class IndexRequestHandler(RequestHandler):
    "Home page handler."

    PAGE_SIZE = 10  # idea page size

    @tornado.gen.coroutine
    def get(self, status=None):
        try:
            page = self.parse_arguments()
        except ValueError:
            self.handle_bad_request()
            return
        spec = {}
        if status == "unresolved":
            sort_by, direction = "close_date", pymongo.ASCENDING
            spec["resolved"] = False
            spec["close_date"] = {"$lt": self.now}
        elif status == "closed":
            sort_by, direction = "close_date", pymongo.DESCENDING
            spec["resolved"] = True
            spec["close_date"] = {"$lt": self.now}
        elif status == "all":
            sort_by, direction = "freeze_date", pymongo.DESCENDING
        else:
            sort_by, direction = "freeze_date", pymongo.ASCENDING
            spec["freeze_date"] = {"$gt": self.now}
            if self.current_user:
                spec["bets.account_id"] = {"$ne": self.current_user.account_id}
        ideas = yield self.db.ideas.find(spec).\
            sort(sort_by, direction).\
            skip((page - 1) * self.PAGE_SIZE).\
            limit(self.PAGE_SIZE).\
            to_list(self.PAGE_SIZE)
        self.render("index.html", ideas=ideas, page=page, path=self.request.path, status=status)

    def parse_arguments(self):
        page = int(self.get_query_argument("page", 1))
        if page < 1:
            raise ValueError("invalid page")
        return page


# Log in handler.
# ------------------------------------------------------------------------------

class LogInRequestHandler(RequestHandler):
    "Log in handler."

    def get_template_namespace(self):
        "Gets default template namespace."
        return {}

    @tornado.gen.coroutine
    def prepare(self):
        self.db = self.settings["db"]  # override default

    @tornado.gen.coroutine
    def get(self):
        if self.get_query_argument("status") == "ok":
            account_id = int(self.get_query_argument("account_id"))
            self.set_secure_cookie("user", pickle.dumps(User(account_id, self.get_query_argument("nickname"))))
            yield self.create_account(account_id)
            yield self.log_event(SystemEventType.LOGGED_IN, account_id=account_id)
        self.redirect(self.get_query_argument("next", "/"))

    @tornado.gen.coroutine
    def create_account(self, account_id):
        "Creates a new account with initial balance."
        try:
            yield self.db.accounts.insert({"_id": account_id, "coins": 100.0})
            yield self.log_event(SystemEventType.SET_INITIAL_BALANCE, account_id=account_id, coins=100.0)
        except pymongo.errors.DuplicateKeyError:
            pass


# New idea handler.
# ------------------------------------------------------------------------------

class NewRequestHandler(RequestHandler):
    "New idea handler."

    @tornado.gen.coroutine
    def prepare(self):
        yield super().prepare()
        if not self.is_admin:
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
            self.redirect("/i/{}".format(encode_object_id(document_id)))

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
            "resolved": False,
            "bets": [],
        }

    def parse_datetime(self, date, time):
        "Parses date and time strings."
        return datetime.datetime.strptime("{} {}".format(date, time), "%Y-%m-%d %H:%M")


# Idea handler.
# ------------------------------------------------------------------------------


class IdeaRequestHandler(RequestHandler):
    "Idea handler."

    @tornado.gen.coroutine
    def get(self, urlsafe_id):
        try:
            _id = decode_object_id(urlsafe_id)
        except ValueError:
            self.handle_bad_request()
            return
        idea = yield self.db.ideas.find_one({"_id": _id})
        if idea:
            budget = int(sum(map(operator.itemgetter("coins"), idea["bets"])))
            self.render("idea.html", idea=idea, budget=budget, _xsrf=self.xsrf_form_html())
        else:
            self.send_error(http.client.NOT_FOUND)


# Bet handler.
# ------------------------------------------------------------------------------

class BetRequestHandler(RequestHandler):
    "Bet handler."

    @tornado.gen.coroutine
    def post(self, urlsafe_id):
        try:
            if self.current_user is None:
                raise ValueError("no user logged in")
            user = self.current_user
            idea_id = decode_object_id(urlsafe_id)
            bet, coins = self.parse_arguments()
            yield self.make_bet(user, idea_id, bet, coins)
        except (ValueError, tornado.web.MissingArgumentError):
            self.handle_bad_request()
            return
        else:
            self.redirect("/i/{}".format(urlsafe_id))

    def parse_arguments(self):
        bet = bool(int(self.get_argument("bet")))
        coins = float(self.get_argument("coins"))
        if coins <= 0:
            raise ValueError("invalid coins value: %s" % coins)
        return bet, coins

    @tornado.gen.coroutine
    def make_bet(self, user, idea_id, bet, coins):
        "Makes a bet."
        account = yield self.db.accounts.find_and_modify(
            {
                "_id": user.account_id,
                "coins": {"$gte": coins},
            },
            {"$inc": {"coins": -coins}},
            new=True,
        )
        if not account:
            raise ValueError("not enough coins")
        yield self.db.ideas.update(
            {"_id": idea_id},
            {"$push": {"bets": {"account_id": user.account_id, "nickname": user.nickname, "coins": coins, "bet": bet}}},
        )
        yield self.log_event(SystemEventType.MADE_BET, account_id=user.account_id, idea_id=idea_id, bet=bet, coins=coins, coins_left=account["coins"])


# Balance handler.
# ------------------------------------------------------------------------------

class BalanceRequestHandler(RequestHandler):
    "User balance handler."

    @tornado.gen.coroutine
    def get(self):
        if not self.current_user:
            self.redirect("/")
        spec = {
            "kwargs.account_id": self.current_user.account_id,
            "type": {"$in": [SystemEventType.SET_INITIAL_BALANCE.value, SystemEventType.MADE_BET.value]}
        }
        events = yield self.db.events.find(spec).sort("_id", pymongo.DESCENDING).to_list(100)
        self.render("balance.html", events=events)


# Log out handler.
# ------------------------------------------------------------------------------

class LogOutRequestHandler(RequestHandler):
    "Log out handler."

    def get_template_namespace(self):
        "Gets default template namespace."
        return {}

    @tornado.gen.coroutine
    def prepare(self):
        pass  # override default

    def get(self):
        self.clear_cookie("user")
        self.redirect("/")


# Script entry point.
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    args = get_argument_parser().parse_args()
    configure_logging(args)
    try:
        sys.exit(main(args) or os.EX_OK)
    except KeyboardInterrupt:
        pass
