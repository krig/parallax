# -*- Mode: python -*-

# Copyright (c) 2009-2012, Andrew McNabb

"""Implementation of SSH_ASKPASS to get a password to ssh from parallax.

The password is read from the socket specified by the environment variable
PARALLAX_ASKPASS_SOCKET.  The other end of this socket is parallax.

The ssh man page discusses SSH_ASKPASS as follows:
    If ssh needs a passphrase, it will read the passphrase from the current
    terminal if it was run from a terminal.  If ssh does not have a terminal
    associated with it but DISPLAY and SSH_ASKPASS are set, it will execute
    the program specified by SSH_ASKPASS and open an X11 window to read the
    passphrase.  This is particularly useful when calling ssh from a .xsession
    or related script.  (Note that on some machines it may be necessary to
    redirect the input from /dev/null to make this work.)
"""

import os
import socket
import sys
import textwrap

bin_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
askpass_bin_path = os.path.join(bin_dir, 'parallax-askpass')
ASKPASS_PATHS = (askpass_bin_path,
        '/usr/bin/parallax-askpass',
        '/usr/libexec/parallax/parallax-askpass',
        '/usr/local/libexec/parallax/parallax-askpass',
        '/usr/lib/parallax/parallax-askpass',
        '/usr/local/lib/parallax/parallax-askpass')

_executable_path = None

def executable_path():
    """Determines the value to use for SSH_ASKPASS.

    The value is cached since this may be called many times.
    """
    global _executable_path
    if _executable_path is None:
        for path in ASKPASS_PATHS:
            if os.access(path, os.X_OK):
                _executable_path = path
                break
        else:
            _executable_path = ''
            sys.stderr.write(textwrap.fill("Warning: could not find an"
                    " executable path for askpass because Parallax SSH was not"
                    " installed correctly.  Password prompts will not work."))
            sys.stderr.write('\n')
    return _executable_path

def askpass_main():
    """Connects to parallax over the socket specified at PARALLAX_ASKPASS_SOCKET."""

    verbose = os.getenv('PARALLAX_ASKPASS_VERBOSE')

    # It's not documented anywhere, as far as I can tell, but ssh may prompt
    # for a password or ask a yes/no question.  The command-line argument
    # specifies what is needed.
    if len(sys.argv) > 1:
        prompt = sys.argv[1]
        if verbose:
            sys.stderr.write('parallax-askpass received prompt: "%s"\n' % prompt)
        if not prompt.strip().lower().endswith('password:'):
            sys.stderr.write(prompt)
            sys.stderr.write('\n')
            sys.exit(1)
    else:
        sys.stderr.write('Error: parallax-askpass called without a prompt.\n')
        sys.exit(1)

    address = os.getenv('PARALLAX_ASKPASS_SOCKET')
    if not address:
        sys.stderr.write(textwrap.fill("parallax error: SSH requested a password."
                " Please create SSH keys or use the -A option to provide a"
                " password."))
        sys.stderr.write('\n')
        sys.exit(1)

    sock = socket.socket(socket.AF_UNIX)
    try:
        sock.connect(address)
    except socket.error:
        _, e, _ = sys.exc_info()
        message = e.args[1]
        sys.stderr.write("Couldn't bind to %s: %s.\n" % (address, message))
        sys.exit(2)

    try:
        password = sock.makefile().read()
    except socket.error:
        sys.stderr.write("Socket error.\n")
        sys.exit(3)

    print(password)


if __name__ == '__main__':
    askpass_main()
