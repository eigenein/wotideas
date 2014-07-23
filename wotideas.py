#!/usr/bin/env python3
# coding: utf-8

"WoT Ideas Application."

import sys; sys.dont_write_bytecode = True

import argparse
import collections
import http.client
import logging
import os
import pathlib
import pickle

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
    initialize_database()
    logging.info("Initializing application…")
    initialize_web_application().listen(8080)
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


def initialize_database():
    "Initializes database."
    db = motor.MotorClient().wotideas
    db.ideas.ensure_index("freeze_date", pymongo.DESCENDING)
    db.accounts.ensure_index("account_id", pymongo.ASCENDING, unique=True)


def initialize_web_application():
    "Initializes application handlers."
    return tornado.web.Application(
        [
            (r"/", IndexHandler),
            (r"/login", LogInHandler),
            (r"/logout", LogOutHandler),
            (r"/new", NewHandler),
        ],
        cookie_secret=config.COOKIE_SECRET,
        db=motor.MotorClient().wotideas,
        static_path="static",
        template_path="templates",
        xsrf_cookies=True,
    )


User = collections.namedtuple("User", ["account_id", "nickname"])


class RequestHandler(tornado.web.RequestHandler):
    "Base request handler."
    
    @tornado.gen.coroutine
    def prepare(self):
        self.db = self.settings["db"]
        self.balance = yield self.get_balance() if (self.current_user is not None) else None

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
        }

    @tornado.gen.coroutine
    def get_balance(self):
        "Gets current user balance string."
        account = yield self.db.accounts.find_one({"account_id": self.current_user.account_id}, {"cents": True})
        return "{:.2f}".format(account["cents"] / 100.0)

    def is_admin(self):
        return (self.current_user is not None) and (self.current_user.account_id in config.ADMIN_ID)


class IndexHandler(RequestHandler):
    def get(self):
        self.render("index.html")


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
        self.render("new.html", _xsrf=self.xsrf_form_html())

    def post(self):
        self.redirect("/")


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
