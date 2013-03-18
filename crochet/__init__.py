"""
Crochet!
"""

import threading
import atexit
try:
    from queue import Queue, Empty
except ImportError:
    from Queue import Queue, Empty
from functools import wraps

from twisted.python.failure import Failure
from twisted.internet import reactor
from twisted.internet.threads import blockingCallFromThread
from twisted.internet.defer import maybeDeferred


__all__ = ["setup", "in_event_loop", "DeferredResult", "TimeoutError"]


class TimeoutError(Exception):
    """
    A timeout has been hit.
    """


class DeferredResult(object):
    """
    A blocking interface to Deferred results.
    """

    def __init__(self, deferred):
        self._deferred = deferred
        self._queue = Queue()
        self._deferred.addBoth(self._queue.put)

    def cancel(self):
        """
        Try to cancel the operation by cancelling the underlying Defered.

        Cancellation of the operation may or may not happen depending on
        underlying cancellation support and whether the operation has already
        finished. In any case, however, the underlying Deferred will be fired.

        Multiple calls will have no additional effect.
        """

    def result(self, timeout=None):
        """
        Return the result, or throw an exception if result is a failure.

        It may take an unknown amount of time to return the result, so a
        timeout option is provided. If the given number of seconds pass with
        no result, a TimeoutError will be thrown.

        If a previous call timed out, additional calls to this function will
        still wait for a result and return it if available. If a result was
        returned or raised on the first call, additional calls will
        return/raise the same result.
        """
        try:
            result = self._queue.get(timeout=timeout)
        except Empty:
            raise TimeoutError()
        self._queue.put(result) # allow next result() call to get a value out
        if isinstance(result, Failure):
            raise result.value
        return result


class _Crochet(object):
    """
    Initialization infrastructure for running a reactor in a thread.
    """
    def __init__(self, reactor, atexit_register):
        self._reactor = reactor
        self._atexit_register = atexit_register
        self._started = False
        self._lock = threading.Lock()

    def setup(self):
        """
        Initialize the crochet library.

        This must be called at least once before the library can be used, and
        can be called multiple times.
        """
        with self._lock:
            if self._started:
                return
            self._started = True
            t = threading.Thread(
                target=lambda: self._reactor.run(installSignalHandlers=False))
            t.start()
            self._atexit_register(self._reactor.callFromThread,
                                  self._reactor.stop)


    def in_event_loop(self, function):
        """
        A decorator that ensures the wrapped function runs in the reactor thread.

        The wrapped function will get the reactor passed in as a first
        argument, in addition to any arguments it is called with.

        When the wrapped function is called, a DeferredResult is returned.
        """
        def runs_in_reactor(args, kwargs):
            d = maybeDeferred(function, self._reactor, *args, **kwargs)
            return DeferredResult(d)

        @wraps(function)
        def wrapper(*args, **kwargs):
            return blockingCallFromThread(self._reactor, runs_in_reactor, args,
                                          kwargs)
        return wrapper


_main = _Crochet(reactor, atexit.register)
setup = _main.setup
in_event_loop = _main.in_event_loop