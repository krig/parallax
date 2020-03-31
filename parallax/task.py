# Copyright (c) 2009-2012, Andrew McNabb
# Copyright (c) 2013, Kristoffer Gronlund

from errno import EINTR
from subprocess import Popen, PIPE
import os
import signal
import sys
import time
import traceback

from parallax import askpass_client

BUFFER_SIZE = 1 << 16

try:
    bytes
except NameError:
    bytes = str


PY2 = sys.version[0] == '2'


class Task(object):
    """Starts a process and manages its input and output.

    Upon completion, the `exitstatus` attribute is set to the exit status
    of the process.
    """
    def __init__(self,
                 host,
                 port,
                 user,
                 cmd,
                 verbose=False,
                 quiet=False,
                 stdin=None,
                 print_out=False,
                 inline=False,
                 inline_stdout=False,
                 default_user=None):

        # Backwards compatibility:
        if not isinstance(verbose, bool):
            opts = verbose
            verbose = opts.verbose
            quiet = opts.quiet
            try:
                print_out = bool(opts.print_out)
            except AttributeError:
                print_out = False
            try:
                inline = bool(opts.inline)
            except AttributeError:
                inline = False
            try:
                inline_stdout = bool(opts.inline_stdout)
            except AttributeError:
                inline_stdout = False
            default_user = opts.user

        self.exitstatus = None

        self.host = host
        self.pretty_host = host
        self.port = port
        self.cmd = cmd

        if user and user != default_user:
            self.pretty_host = '@'.join((user, self.pretty_host))
        if port:
            self.pretty_host = ':'.join((self.pretty_host, port))

        self.proc = None
        self.writer = None
        self.timestamp = None
        self.failures = []
        self.killed = False
        self.inputbuffer = stdin
        self.byteswritten = 0
        self.outputbuffer = bytes()
        self.errorbuffer = bytes()

        self.stdin = None
        self.stdout = None
        self.stderr = None
        self.outfile = None
        self.errfile = None

        # Set options.
        self.verbose = verbose
        self.quiet = quiet
        self.print_out = print_out
        self.inline = inline
        self.inline_stdout = inline or inline_stdout

    def start(self, nodenum, iomap, writer, askpass_socket=None):
        """Starts the process and registers files with the IOMap."""
        self.writer = writer

        if writer:
            self.outfile, self.errfile = writer.open_files(self.pretty_host)

        # Set up the environment.
        environ = dict(os.environ)
        environ['PARALLAX_NODENUM'] = str(nodenum)
        environ['PARALLAX_HOST'] = self.host
        # Disable the GNOME pop-up password dialog and allow ssh to use
        # askpass.py to get a provided password.  If the module file is
        # askpass.pyc, we replace the extension.
        environ['SSH_ASKPASS'] = askpass_client.executable_path()
        if askpass_socket:
            environ['PARALLAX_ASKPASS_SOCKET'] = askpass_socket
        if self.verbose:
            environ['PARALLAX_ASKPASS_VERBOSE'] = '1'
        # Work around a mis-feature in ssh where it won't call SSH_ASKPASS
        # if DISPLAY is unset.
        if 'DISPLAY' not in environ:
            environ['DISPLAY'] = 'parallax-gibberish'

        # Create the subprocess.  Since we carefully call set_cloexec() on
        # all open files, we specify close_fds=False.
        if PY2:
            self.proc = Popen(self.cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, 
                    close_fds=False, preexec_fn=os.setsid, env=environ)
        else:
            self.proc = Popen(self.cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE,
                    close_fds=False, start_new_session=True, env=environ)

        self.timestamp = time.time()
        if self.inputbuffer:
            self.stdin = self.proc.stdin
            iomap.register_write(self.stdin.fileno(), self.handle_stdin)
        else:
            self.proc.stdin.close()
        self.stdout = self.proc.stdout
        iomap.register_read(self.stdout.fileno(), self.handle_stdout)
        self.stderr = self.proc.stderr
        iomap.register_read(self.stderr.fileno(), self.handle_stderr)

    def _kill(self):
        """Signals the process to terminate."""
        if self.proc:
            try:
                os.kill(-self.proc.pid, signal.SIGKILL)
            except OSError:
                # If the kill fails, then just assume the process is dead.
                pass
            self.killed = True

    def timedout(self):
        """Kills the process and registers a timeout error."""
        if not self.killed:
            self._kill()
            self.failures.append('Timed out')

    def interrupted(self):
        """Kills the process and registers an keyboard interrupt error."""
        if not self.killed:
            self._kill()
            self.failures.append('Interrupted')

    def cancel(self):
        """Stops a task that has not started."""
        self.failures.append('Cancelled')

    def elapsed(self):
        """Finds the time in seconds since the process was started."""
        return time.time() - self.timestamp

    def running(self):
        """Finds if the process has terminated and saves the return code."""
        if self.stdin or self.stdout or self.stderr:
            return True
        if self.proc:
            self.exitstatus = self.proc.poll()
            if self.exitstatus is None:
                if self.killed:
                    # Set the exitstatus to what it would be if we waited.
                    self.exitstatus = -signal.SIGKILL
                    return False
                return True
            else:
                if self.exitstatus < 0:
                    message = 'Killed by signal %s' % (-self.exitstatus)
                    self.failures.append(message)
                elif self.exitstatus > 0:
                    message = 'Exited with error code %s' % self.exitstatus
                    self.failures.append(message)
                self.proc = None
                return False

    def handle_stdin(self, fd, iomap):
        """Called when the process's standard input is ready for writing."""
        try:
            start = self.byteswritten
            if start < len(self.inputbuffer):
                chunk = self.inputbuffer[start:start+BUFFER_SIZE]
                self.byteswritten = start + os.write(fd, chunk)
            else:
                self.close_stdin(iomap)
        except (OSError, IOError):
            _, e, _ = sys.exc_info()
            if e.errno != EINTR:
                self.close_stdin(iomap)
                self.log_exception(e)

    def close_stdin(self, iomap):
        if self.stdin:
            iomap.unregister(self.stdin.fileno())
            self.stdin.close()
            self.stdin = None

    def handle_stdout(self, fd, iomap):
        """Called when the process's standard output is ready for reading."""
        try:
            buf = os.read(fd, BUFFER_SIZE)
            if buf:
                if self.inline_stdout:
                    if self.quiet:
                        self.outputbuffer += "%s: %s" % (self.host, buf)
                    else:
                        self.outputbuffer += buf
                if self.outfile:
                    self.writer.write(self.outfile, buf)
                if self.print_out:
                    for l in buf.split('\n'):
                        sys.stdout.write('%s: %s\n' % (self.host, l))
            else:
                self.close_stdout(iomap)
        except (OSError, IOError):
            _, e, _ = sys.exc_info()
            if e.errno != EINTR:
                self.close_stdout(iomap)
                self.log_exception(e)

    def close_stdout(self, iomap):
        if self.stdout:
            iomap.unregister(self.stdout.fileno())
            self.stdout.close()
            self.stdout = None
        if self.outfile:
            self.writer.close(self.outfile)
            self.outfile = None

    def handle_stderr(self, fd, iomap):
        """Called when the process's standard error is ready for reading."""
        try:
            buf = os.read(fd, BUFFER_SIZE)
            if buf:
                if self.inline:
                    self.errorbuffer += buf
                if self.errfile:
                    self.writer.write(self.errfile, buf)
            else:
                self.close_stderr(iomap)
        except (OSError, IOError):
            _, e, _ = sys.exc_info()
            if e.errno != EINTR:
                self.close_stderr(iomap)
                self.log_exception(e)

    def close_stderr(self, iomap):
        if self.stderr:
            iomap.unregister(self.stderr.fileno())
            self.stderr.close()
            self.stderr = None
        if self.errfile:
            self.writer.close(self.errfile)
            self.errfile = None

    def log_exception(self, e):
        """Saves a record of the most recent exception for error reporting."""
        if self.verbose:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            exc = ("Exception: %s, %s, %s" %
                   (exc_type, exc_value, traceback.format_tb(exc_traceback)))
        else:
            exc = str(e)
        self.failures.append(exc)

# vim:ts=4:sw=4:et:
