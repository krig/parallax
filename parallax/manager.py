# Copyright (c) 2009-2012, Andrew McNabb
# Copyright (c) 2013, Kristoffer Gronlund

from errno import EINTR
import os
import select
import sys
import threading
import copy
import fcntl

try:
    import queue
except ImportError:
    import Queue as queue

from parallax.askpass_server import PasswordServer
from parallax import psshutil
from parallax import DEFAULT_PARALLELISM, DEFAULT_TIMEOUT
from parallax.callbacks import DefaultCallbacks

READ_SIZE = 1 << 16


class FatalError(RuntimeError):
    """A fatal error in the Parallax SSH Manager."""
    pass


class Manager(object):
    """Executes tasks concurrently.

    Tasks are added with add_task() and executed in parallel with run().
    Returns a list of the exit statuses of the processes.

    Arguments:
        limit: Maximum number of commands running at once.
        timeout: Maximum allowed execution time in seconds.
    """
    def __init__(self,
                 limit=DEFAULT_PARALLELISM,
                 timeout=DEFAULT_TIMEOUT,
                 askpass=False,
                 outdir=None,
                 errdir=None,
                 warn_message=True,
                 callbacks=DefaultCallbacks()):
        # Backwards compatibility with old __init__
        # format: Only argument is an options dict
        if not isinstance(limit, int):
            if hasattr(limit, 'limit'):
                self.limit = limit.limit
            elif hasattr(limit, 'par'):
                self.limit = limit.par
            else:
                self.limit = DEFAULT_PARALLELISM
            if hasattr(limit, 'timeout'):
                self.timeout = limit.timeout
            else:
                self.timeout = DEFAULT_TIMEOUT
            if hasattr(limit, 'askpass'):
                self.askpass = limit.askpass
            else:
                self.askpass = False
            if hasattr(limit, 'outdir'):
                self.outdir = limit.outdir
            else:
                self.outdir = None
            if hasattr(limit, 'errdir'):
                self.errdir = limit.errdir
            else:
                self.errdir = None
        else:
            self.limit = limit
            self.timeout = timeout
            self.askpass = askpass
            self.outdir = outdir
            self.errdir = errdir
        self.iomap = make_iomap()
        self.callbacks = callbacks

        self.taskcount = 0
        self.tasks = []
        self.save_tasks = []
        self.running = []
        self.done = []

        self.askpass_socket = None
        self.warn_message = warn_message

    def run(self):
        """Processes tasks previously added with add_task."""
        self.save_tasks = copy.copy(self.tasks)
        if self.outdir or self.errdir:
            writer = Writer(self.outdir, self.errdir)
            writer.start()
        else:
            writer = None

        try:
            if self.askpass:
                pass_server = PasswordServer()
                pass_server.start(self.iomap, self.limit, warn=self.warn_message)
                self.askpass_socket = pass_server.address

            try:
                self.update_tasks(writer)
                wait = None
                while self.running or self.tasks:
                    # Opt for efficiency over subsecond timeout accuracy.
                    if wait is None or wait < 1:
                        wait = 1
                    self.iomap.poll(wait)
                    self.update_tasks(writer)
                    wait = self.check_timeout()
                return self.callbacks.result(self)
            except KeyboardInterrupt:
                # This exception handler tries to clean things up and prints
                # out a nice status message for each interrupted host.
                self.interrupted()
                raise
        finally:
            if writer:
                writer.signal_quit()
                writer.join()


    def add_task(self, task):
        """Adds a Task to be processed with run()."""
        self.tasks.append(task)

    def update_tasks(self, writer):
        """Reaps tasks and starts as many new ones as allowed."""
        keep_running = True
        while keep_running:
            self._start_tasks_once(writer)
            keep_running = self.reap_tasks()

    def _start_tasks_once(self, writer):
        """Starts tasks once."""
        while self.tasks and len(self.running) < self.limit:
            task = self.tasks.pop(0)
            self.running.append(task)
            task.start(self.taskcount, self.iomap, writer, self.askpass_socket)
            self.taskcount += 1

    def reap_tasks(self):
        """Checks to see if any tasks have terminated.

        After cleaning up, returns the number of tasks that finished.
        """
        still_running = []
        finished_count = 0
        for task in self.running:
            if task.running():
                still_running.append(task)
            else:
                self.finished(task)
                finished_count += 1
        self.running = still_running
        return finished_count

    def check_timeout(self):
        """Kills timed-out processes and returns the lowest time left."""
        if self.timeout <= 0:
            return None

        min_timeleft = None
        for task in self.running:
            timeleft = self.timeout - task.elapsed()
            if timeleft <= 0:
                task.timedout()
                continue
            if min_timeleft is None or timeleft < min_timeleft:
                min_timeleft = timeleft

        if min_timeleft is None:
            return 0
        return max(0, min_timeleft)

    def interrupted(self):
        """Cleans up after a keyboard interrupt."""
        for task in self.running:
            task.interrupted()
            self.finished(task)

        for task in self.tasks:
            task.cancel()
            self.finished(task)

    def finished(self, task):
        """Marks a task as complete and reports its status as finished."""
        self.done.append(task)
        n = len(self.done)
        self.callbacks.finished(task, n)


class IOMap(object):
    """A manager for file descriptors and their associated handlers.

    The poll method dispatches events to the appropriate handlers.
    """
    def __init__(self):
        self.readmap = {}
        self.writemap = {}

    def register_read(self, fd, handler):
        """Registers an IO handler for a file descriptor for reading."""
        self.readmap[fd] = handler

    def register_write(self, fd, handler):
        """Registers an IO handler for a file descriptor for writing."""
        self.writemap[fd] = handler

    def unregister(self, fd):
        """Unregisters the given file descriptor."""
        if fd in self.readmap:
            del self.readmap[fd]
        if fd in self.writemap:
            del self.writemap[fd]

    def poll(self, timeout=None):
        """Performs a poll and dispatches the resulting events."""
        if not self.readmap and not self.writemap:
            return
        rlist = list(self.readmap)
        wlist = list(self.writemap)
        try:
            rlist, wlist, _ = select.select(rlist, wlist, [], timeout)
        except select.error:
            _, e, _ = sys.exc_info()
            errno = e.args[0]
            if errno == EINTR:
                return
            else:
                raise
        for fd in rlist:
            handler = self.readmap[fd]
            handler(fd, self)
        for fd in wlist:
            handler = self.writemap[fd]
            handler(fd, self)


class PollIOMap(IOMap):
    """A manager for file descriptors and their associated handlers.

    The poll method dispatches events to the appropriate handlers.
    Note that `select.poll` is not available on all operating systems.
    """
    def __init__(self):
        self._poller = select.poll()
        super(PollIOMap, self).__init__()

    def register_read(self, fd, handler):
        """Registers an IO handler for a file descriptor for reading."""
        super(PollIOMap, self).register_read(fd, handler)
        self._poller.register(fd, select.POLLIN)

    def register_write(self, fd, handler):
        """Registers an IO handler for a file descriptor for writing."""
        super(PollIOMap, self).register_write(fd, handler)
        self._poller.register(fd, select.POLLOUT)

    def unregister(self, fd):
        """Unregisters the given file descriptor."""
        super(PollIOMap, self).unregister(fd)
        self._poller.unregister(fd)

    def poll(self, timeout=None):
        """Performs a poll and dispatches the resulting events."""
        if not self.readmap and not self.writemap:
            return
        try:
            event_list = self._poller.poll(timeout)
        except select.error:
            _, e, _ = sys.exc_info()
            errno = e.args[0]
            if errno == EINTR:
                return
            else:
                raise
        for fd, event in event_list:
            if event & (select.POLLIN | select.POLLHUP):
                handler = self.readmap[fd]
                handler(fd, self)
            if event & (select.POLLOUT | select.POLLERR):
                handler = self.writemap[fd]
                handler(fd, self)


def make_iomap():
    """Return a new IOMap or PollIOMap as appropriate.

    Since `select.poll` is not implemented on all platforms, this ensures that
    the most appropriate implementation is used.
    """
    if hasattr(select, 'poll'):
        return PollIOMap()
    return IOMap()


class Writer(threading.Thread):
    """Thread that writes to files by processing requests from a Queue.

    Until AIO becomes widely available, it is impossible to make a nonblocking
    write to an ordinary file.  The Writer thread processes all writing to
    ordinary files so that the main thread can work without blocking.
    """
    OPEN = object()
    EOF = object()
    ABORT = object()

    def __init__(self, outdir, errdir):
        threading.Thread.__init__(self)
        # A daemon thread automatically dies if the program is terminated.
        self.setDaemon(True)
        self.queue = queue.Queue()
        self.outdir = outdir
        self.errdir = errdir

        self.host_counts = {}
        self.files = {}

    def run(self):
        while True:
            filename, data = self.queue.get()
            if filename == self.ABORT:
                return

            if data == self.OPEN:
                self.files[filename] = open(filename, 'wb', buffering=1)
                psshutil.set_cloexec(self.files[filename])
            else:
                dest = self.files[filename]
                if data == self.EOF:
                    dest.close()
                else:
                    dest.write(data)
                    dest.flush()

    def open_files(self, host):
        """Called from another thread to create files for stdout and stderr.

        Returns a pair of filenames (outfile, errfile).  These filenames are
        used as handles for future operations.  Either or both may be None if
        outdir or errdir or not set.
        """
        outfile = errfile = None
        if self.outdir or self.errdir:
            count = self.host_counts.get(host, 0)
            self.host_counts[host] = count + 1
            if count:
                filename = "%s.%s" % (host, count)
            else:
                filename = host
            if self.outdir:
                outfile = os.path.join(self.outdir, filename)
                self.queue.put((outfile, self.OPEN))
            if self.errdir:
                errfile = os.path.join(self.errdir, filename)
                self.queue.put((errfile, self.OPEN))
        return outfile, errfile

    def write(self, filename, data):
        """Called from another thread to enqueue a write."""
        self.queue.put((filename, data))

    def close(self, filename):
        """Called from another thread to close the given file."""
        self.queue.put((filename, self.EOF))

    def signal_quit(self):
        """Called from another thread to request the Writer to quit."""
        self.queue.put((self.ABORT, None))
