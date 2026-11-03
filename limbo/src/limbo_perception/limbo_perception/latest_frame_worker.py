"""Serial processing with one replaceable pending item, independent of ROS."""

import sys
import threading


class LatestFrameWorker:
    """Finish the active callback, then process only the latest pending tuple.

    submit() never runs the callback or waits for processing. A pending tuple is
    replaced as a unit, preserving RGB/depth/detection correspondence. Shutdown
    stops acceptance, discards pending work and joins the active callback. The
    caller keeps publishers/context alive until shutdown() returns and calls
    raise_if_failed() to propagate callback errors on its controlling thread.
    """

    def __init__(self, callback, *, name='latest-frame-worker'):
        self._callback = callback
        self._condition = threading.Condition()
        self._pending = None
        self._stopping = False
        self._active = False
        self._error = None
        self._traceback = None
        self._counts = dict(submitted=0, started=0, processed=0, overwritten=0,
                            shutdown_dropped=0, failure_dropped=0, failed=0,
                            rejected_after_stop=0)
        self._thread = threading.Thread(target=self._run, name=name, daemon=False)
        self._thread.start()

    def submit(self, *args):
        with self._condition:
            if self._stopping:
                self._counts['rejected_after_stop'] += 1
                return False
            self._counts['submitted'] += 1
            if self._pending is not None:
                self._counts['overwritten'] += 1
            self._pending = args
            self._condition.notify()
            return True

    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(
                    lambda: self._stopping or self._pending is not None)
                if self._stopping:
                    return
                args, self._pending = self._pending, None
                self._active = True
                self._counts['started'] += 1
            try:
                self._callback(*args)
            except BaseException as error:
                with self._condition:
                    self._error = error
                    self._traceback = sys.exc_info()[2]
                    self._counts['failed'] += 1
                    self._active = False
                    self._stopping = True
                    if self._pending is not None:
                        self._pending = None
                        self._counts['failure_dropped'] += 1
                    self._condition.notify_all()
                return
            else:
                with self._condition:
                    self._counts['processed'] += 1
                    self._active = False
                    self._condition.notify_all()

    def shutdown(self):
        if threading.current_thread() is self._thread:
            raise RuntimeError('LatestFrameWorker.shutdown must run outside its callback')
        with self._condition:
            self._stopping = True
            if self._pending is not None:
                self._pending = None
                self._counts['shutdown_dropped'] += 1
            self._condition.notify_all()
        self._thread.join()
        return self.statistics()

    def raise_if_failed(self):
        with self._condition:
            error, traceback = self._error, self._traceback
        if error is not None:
            raise error.with_traceback(traceback)

    def statistics(self):
        with self._condition:
            return {**self._counts, 'pending': int(self._pending is not None),
                    'active': int(self._active), 'stopping': self._stopping}
