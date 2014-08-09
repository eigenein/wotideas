#!/usr/bin/env python3
# coding: utf-8

from email.utils import formataddr


ADMIN_ID = set([5589968])
APPLICATION_ID = "b97af3d8dd57785958ae5b8a62ba61d7"
COOKIE_SECRET = "you shall not pass"
EMAIL_CALLBACK_TIME = 10000
FROM = formataddr(("WoT Ideas", "no-reply@wotideas.ru"))
NO_REPLY_PASS = "qwe123!@#"
REPLY_TO = formataddr(("WoT Ideas", "inbox@wotideas.ru"))
