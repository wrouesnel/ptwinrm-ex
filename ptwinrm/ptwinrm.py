# -*- coding: utf-8 -*-
#
# This file is part of the ptwinrm project
#
# Copyright (c) 2017 Tiago Coutinho
# Distributed under the MIT license. See LICENSE for more info.

"""WinRM console

Usage:
  winrm [--user=<user>]
        [--password=<password>]
        [--transport=<transport>]
        [--encoding=<encoding>]
        [--run=<cmd>] <host>

Options:
  -h --help                show this
  --user=<user>            user name
  --password=<password>    password on the command line
  --transport=<transport>  [default: ntlm]. Valid: 'kerberos', 'ntlm'
  --encoding=<encoding>    specify console encoding (defaults to stdout encoding)
  --run=<cmd>              command to execute (if not given, a console starts)
"""

from __future__ import unicode_literals
from __future__ import print_function

import keyring
import sys
from functools import partial

import winrm
import winrm.exceptions
import requests.exceptions
from docopt import docopt
from prompt_toolkit import prompt
from prompt_toolkit.keys import Keys
from prompt_toolkit.token import Token
from prompt_toolkit.filters import Always, Never
from prompt_toolkit.styles import style_from_dict
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.key_binding.manager import KeyBindingManager

SERVICE_TMPL = "winrm:{host}"
DEFAULT_USER_KEY = "__default_08723efe-242f-11e9-8143-7ff2638e4f3e"

class WinRMConsole(object):
    """WinRM Console"""

    def __init__(self, session, encoding):
        self.session = session
        self.encoding = encoding
        self.multiline = False

    @property
    def username(self):
        return self.session.protocol.username

    @property
    def url(self):
        return self.session.url

    def run_cmd_line(self, cmd_line):
        try:
            return self.__run_cmd_line(cmd_line)
        except (winrm.exceptions.InvalidCredentialsError,
                requests.exceptions.ConnectionError) as error:
            print('ERROR:', error)

    def __run_cmd_line(self, cmd_line):
        if not cmd_line.strip():
            return
        if '\n' in cmd_line:
            return self.session.run_ps(cmd_line)
        else:
            cmd = cmd_line.split()
            return self.session.run_cmd(cmd[0], cmd[1:])

    def handle_cmd_result(self, result):
        if result is None:
            return
        if result.status_code:
            print('ERROR ({0}): {1}'.format(result.status_code, result.std_err.decode(self.encoding)))
        else:
            print(result.std_out.decode(self.encoding))
            if result.std_err:
                print('ERROR: {0}'.format(result.std_err.decode(self.encoding)))
        return result

    def toggle_multiline(self):
        self.multiline = not self.multiline
        return self.multiline

    def get_prompt(self):
        r = self.run_cmd_line('cd')
        return r.std_out.strip().decode(self.encoding) + ">"

    def rep(self, cmd_line):
        result = self.run_cmd_line(cmd_line)
        return self.handle_cmd_result(result)

    def repl(self):
        history = InMemoryHistory()
        auto_suggest = AutoSuggestFromHistory()
        manager = KeyBindingManager.for_prompt()

        @manager.registry.add_binding(Keys.ControlT)
        def _(event):
            def update_multiline():
                multiline = self.toggle_multiline()

                if multiline:
                    event.cli.current_buffer.is_multiline = Always()
                else:
                    event.cli.current_buffer.is_multiline = Never()
                print('Set multiline', multiline and 'ON' or 'off')
            event.cli.run_in_terminal(update_multiline)

        def get_bottom_toolbar_tokens(cli):
            msg = ' Connected as {0} to {1}'.format(self.username, self.url)
            ml = ' Multiline is {0}'.format(self.multiline and 'ON' or 'off')
            return [(Token.Toolbar.Connection, msg),
                    (Token.Toolbar.Multiline, ml)]

        style = style_from_dict({
            Token.Toolbar.Connection: '#ffffff bg:#009900',
            Token.Toolbar.Multiline: '#ffffff bg:#ee0000',
        })

        ppt = partial(prompt, history=history, auto_suggest=auto_suggest,
                      get_bottom_toolbar_tokens=get_bottom_toolbar_tokens,
                      key_bindings_registry=manager.registry,
                      style=style)

        try:
            prompt_msg = self.get_prompt()
        except Exception as e:
            print("ERROR: {}".format(e))
            return
        while True:
            try:
                cmd_line = ppt(prompt_msg, multiline=self.multiline)
                self.rep(cmd_line)
            except (EOFError, KeyboardInterrupt):
                print('\nCtrl-C pressed. Bailing out!')
                break
            except:
                sys.excepthook(*sys.exc_info())


def main():
    opt = docopt(__doc__, help=True)
    host = opt['<host>']
    user = opt['--user']
    password = opt['--password']
    transport = opt['--transport']
    encoding = opt["--encoding"] or sys.stdout.encoding

    service_name = SERVICE_TMPL.format(host=host)

    if user is None:
        user = keyring.get_password(service_name, DEFAULT_USER_KEY)
        if not user:
            user = prompt("user: ")
            keyring.set_password(service_name, DEFAULT_USER_KEY, user)
            print("Saved new default user {} for host {}".format(user, host))
        print("User from keyring: {}".format(user))

    if password is None:
        password = keyring.get_password(service_name, user)
        if not password:
            password = prompt('password: ', is_password=True)
            keyring.set_password(service_name, user, password)
            print("Saved new password for user {} for host {}".format(user, host))
        print("Password for user from keyring")

    session = winrm.Session(host, (user, password), transport=transport)
    console = WinRMConsole(session,encoding=encoding)

    if opt['--run']:
        cmd_result = console.rep(opt['--run'])
        code = cmd_result.status_code if cmd_result else 1
        sys.exit(code)

    console.repl()


if __name__ == '__main__':
    main()
