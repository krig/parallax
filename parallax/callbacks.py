# Copyright (c) 2009-2012, Andrew McNabb
# Copyright (c) 2013, Kristoffer Gronlund

import sys
import time

from parallax import color


class DefaultCallbacks(object):
    """
    Passed to the Manager and called when events occur.
    """
    def finished(self, task, n):
        """Pretty prints a status report after the Task completes.
        task: a Task object
        n: Index in sequence of completed tasks.
        """
        error = ', '.join(task.failures)
        tstamp = time.asctime().split()[3]  # Current time
        if color.has_colors(sys.stdout):
            progress = color.c("[%s]" % color.B(n))
            success = color.g("[%s]" % color.B("SUCCESS"))
            failure = color.r("[%s]" % color.B("FAILURE"))
            stderr = color.r("Stderr: ")
            error = color.r(color.B(error))
        else:
            progress = "[%s]" % n
            success = "[SUCCESS]"
            failure = "[FAILURE]"
            stderr = "Stderr: "
        host = task.pretty_host
        if not task.quiet:
            if task.failures:
                print(' '.join((progress, tstamp, failure, host, error)))
            else:
                print(' '.join((progress, tstamp, success, host)))
        # NOTE: The extra flushes are to ensure that the data is output in
        # the correct order with the C implementation of io.
        if task.outputbuffer:
            sys.stdout.flush()
            try:
                sys.stdout.buffer.write(task.outputbuffer)
                sys.stdout.flush()
            except AttributeError:
                sys.stdout.write(task.outputbuffer)
        if task.errorbuffer:
            sys.stdout.write(stderr)
            # Flush the TextIOWrapper before writing to the binary buffer.
            sys.stdout.flush()
            try:
                sys.stdout.buffer.write(task.errorbuffer)
            except AttributeError:
                sys.stdout.write(task.errorbuffer)

    def result(self, manager):
        """
        When all Tasks are completed, generate a result to return.
        """
        return [task.exitstatus for task in manager.save_tasks if task in manager.done]
