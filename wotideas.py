#!/usr/bin/env python3
# coding: utf-8

"WoT Ideas Application."

import argparse
import logging
import os
import pathlib
import sys

import tornado.ioloop
import tornado.web


def main(args):
    "Entry point."
    logging.info("Checking environment…")
    check_environment()
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


def initialize_web_application():
    "Initializes application handlers."
    return tornado.web.Application(
        [
            (r"/", IndexHandler),
        ],
        static_path="static",
        template_path="templates",
    )


class IndexHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html")


# Script entry point.
if __name__ == "__main__":
    args = get_argument_parser().parse_args()
    configure_logging(args)
    try:
        sys.exit(main(args) or os.EX_OK)
    except KeyboardInterrupt:
        pass
