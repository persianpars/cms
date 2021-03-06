#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2012 Bernard Blackham <bernard@largestprime.net>
# Copyright © 2010-2012 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2016 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import codecs
import datetime
import io
import os
import sys
import time
import traceback
import urllib

from mechanize import HTMLForm, HTTPError

utf8_decoder = codecs.getdecoder('utf-8')

debug = False


def browser_do_request(browser, url, data=None, files=None):
    """Open an URL in a mechanize browser, optionally passing the
    specified data and files as POST arguments.

    browser (mechanize.Browser): the browser to use.
    url (string): the URL to open.
    data (dict): a dictionary of parameters to pass as POST arguments.
    files (list): a list of files to pass as POST arguments. Each
                  entry is a tuple containing two strings: the field
                  name and the file name to send.

    """
    if files is None:
        if data is None:
            response = browser.open(url)
        else:
            response = browser.open(url, urllib.urlencode(data))
    else:
        browser.form = HTMLForm(url,
                                method='POST',
                                enctype='multipart/form-data')
        for key in sorted(data.keys()):
            # If the passed value is a list, we assume it is a list of
            # names of checkboxes that are checked.
            if isinstance(data[key], list):
                for value in data[key]:
                    browser.form.new_control(
                        'checkbox', key, {'value': value, 'checked': True})
            else:
                browser.form.new_control('hidden', key, {'value': data[key]})

        for field_name, file_path in files:
            browser.form.new_control('file', field_name, {'id': field_name})
            filename = os.path.basename(file_path)
            browser.form.add_file(io.open(file_path, 'rb'), 'text/plain',
                                  filename, id=field_name)

        browser.form.set_all_readonly(False)
        browser.form.fixup()
        response = browser.open(browser.form.click())
    return response


class GenericRequest(object):
    """Request to a server.

    """

    OUTCOME_SUCCESS = 'success'
    OUTCOME_FAILURE = 'failure'
    OUTCOME_UNDECIDED = 'undecided'
    OUTCOME_ERROR = 'error'

    MINIMUM_LENGTH = 100

    def __init__(self, browser, base_url=None):
        if base_url is None:
            base_url = 'http://localhost:8888/'
        self.browser = browser
        self.base_url = base_url
        self.outcome = None

        self.start_time = None
        self.stop_time = None
        self.duration = None
        self.status_code = None
        self.exception_data = None

        self.url = None
        self.data = None
        self.files = None

        self.status_code = None
        self.response = None
        self.res_data = None
        self.redirected_to = None

    def execute(self):
        """Main entry point to execute the test"""
        self._prepare()
        self._execute()

    def _prepare(self):
        """Optional convenience hook called just after creating the Request"""
        pass

    def _execute(self):
        """Execute the test"""
        description = self.describe()
        self.start_time = time.time()
        try:
            # TODO - We here clear the history, otherwise the memory
            # consumption would explode; maybe it would be better to use a
            # custom History object that just discards the history; on the
            # other hand the History interface is still unstable
            self.browser.clear_history()
            try:
                self.response = browser_do_request(self.browser,
                                                   self.url,
                                                   self.data,
                                                   self.files)
                self.res_data = self.response.read()
                self.status_code = 200

            except HTTPError as http_error:
                self.status_code = http_error.code
                if http_error.code != 302:
                    raise
                for k, v in self.browser.response()._headers.items():
                    if k == "location":
                        self.redirected_to = v

        # Catch possible exceptions
        except Exception as exc:
            self.exception_data = traceback.format_exc()
            self.outcome = GenericRequest.OUTCOME_ERROR

        else:
            self.outcome = None

        finally:
            self.stop_time = time.time()
            self.duration = self.stop_time - self.start_time

        success = None
        try:
            success = self.test_success()
        except Exception as exc:
            self.exception_data = traceback.format_exc()
            self.outcome = GenericRequest.OUTCOME_ERROR

        # If no exceptions were casted, decode the test evaluation
        if self.outcome is None:

            # Could not decide on the evaluation
            if success is None:
                if debug:
                    print("Could not determine status for request '%s'" %
                          (description), file=sys.stderr)
                self.outcome = GenericRequest.OUTCOME_UNDECIDED

            # Success
            elif success:
                if debug:
                    print("Request '%s' successfully completed in %.3fs" %
                          (description, self.duration), file=sys.stderr)
                self.outcome = GenericRequest.OUTCOME_SUCCESS

            # Failure
            elif not success:
                if debug:
                    print("Request '%s' failed" % (description),
                          file=sys.stderr)
                    if self.exception_data is not None:
                        print(self.exception_data, file=sys.stderr)
                self.outcome = GenericRequest.OUTCOME_FAILURE

        # Otherwise report the exception
        else:
            print("Request '%s' terminated with an exception: %s\n%s" %
                  (description, repr(exc), self.exception_data),
                  file=sys.stderr)

    def test_success(self):
        if self.status_code not in [200, 302]:
            return False
        if self.status_code == 200 and self.res_data is None:
            return False
        if self.status_code == 200 and \
                len(self.res_data) < GenericRequest.MINIMUM_LENGTH:
            return False
        return True

    def specific_info(self):
        res = "URL: %s\n" % (unicode(self.url))
        if self.browser.request is not None:
            res += "\nREQUEST HEADERS\n"
            for (key, value) in self.browser.request.header_items():
                res += "%s: %s\n" % (key, value)
            if self.browser.request.get_data() is not None:
                res += "\nREQUEST DATA\n%s\n" % \
                    (self.browser.request.get_data())
            else:
                res += "\nNO REQUEST DATA\n"
        else:
            res += "\nNO REQUEST INFORMATION AVAILABLE\n"
        if self.res_data is not None:
            headers = self.browser.response()._headers.items()
            res += "\nRESPONSE HEADERS\n%s" % (
                "".join(["%s: %s\n" % (unicode(header[0]),
                                       unicode(header[1]))
                         for header in headers]))
            res += "\nRESPONSE DATA\n%s\n" % (utf8_decoder(self.res_data)[0])
        else:
            res += "\nNO RESPONSE INFORMATION AVAILABLE\n"
        return res

    def describe(self):
        raise NotImplementedError("Please subclass this class "
                                  "and actually implement some request")

    def store_to_file(self, fd):
        print("Test type: %s" % (self.__class__.__name__), file=fd)
        print("Execution start time: %s" %
              (datetime.datetime.fromtimestamp(self.start_time).
               strftime("%d/%m/%Y %H:%M:%S.%f")), file=fd)
        print("Execution stop time: %s" %
              (datetime.datetime.fromtimestamp(self.stop_time).
               strftime("%d/%m/%Y %H:%M:%S.%f")), file=fd)
        print("Duration: %f seconds" % (self.duration), file=fd)
        print("Outcome: %s" % (self.outcome), file=fd)
        fd.write(self.specific_info())
        if self.exception_data is not None:
            print("", file=fd)
            print("EXCEPTION CASTED", file=fd)
            fd.write(unicode(self.exception_data))


class LoginRequest(GenericRequest):
    """Try to login to CWS or AWS with the given credentials.

    """
    def __init__(self, browser, username, password, base_url=None):
        GenericRequest.__init__(self, browser, base_url)
        self.username = username
        self.password = password
        self.url = '%slogin' % self.base_url
        self.data = {'username': self.username,
                     'password': self.password,
                     'next': '/'}

    def describe(self):
        return "try to login"

    def test_success(self):
        if not GenericRequest.test_success(self):
            return False
        # Additional checks needs to be done from the subclasses.
        return True

    def specific_info(self):
        return 'Username: %s\nPassword: %s\n' % \
               (self.username, self.password) + \
            GenericRequest.specific_info(self)
