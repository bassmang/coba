import time
import unittest

from multiprocessing import current_process
from typing          import Iterable, Any

from coba.config          import CobaConfig, IndentLogger, BasicLogger, NullLogger, NullCacher
from coba.pipes           import Filter, MemoryIO
from coba.multiprocessing import CobaMultiprocessFilter

class NotPicklableFilter(Filter):
    def __init__(self):
        self._a = lambda : None

    def filter(self, item):
        return 'a'

class SleepingFilter(Filter):
    def filter(self, seconds: Iterable[float]) -> Any:
        second = next(iter(seconds)) #type: ignore
        time.sleep(second)
        yield second

class ProcessNameFilter(Filter):
    def filter(self, items: Iterable[Any]) -> Iterable[Any]:
        process_name = f"pid-{current_process().pid}"
        CobaConfig.logger.log(process_name)
        yield process_name

class ExceptionFilter(Filter):
    def filter(self, items: Iterable[Any]) -> Iterable[Any]:
        raise Exception("Exception Filter")

#this is needed for testing purposes
if current_process().name == 'MainProcess':
    class Test:
        pass

class CobaMultiprocessFilter_Tests(unittest.TestCase):

    def setUp(self) -> None:
        CobaConfig.logger = NullLogger()

    def test_logging(self):
        
        logger_sink = MemoryIO()
        logger      = IndentLogger(logger_sink, with_stamp=True, with_name=True)

        CobaConfig.logger = logger
        CobaConfig.cacher = NullCacher()

        items = list(CobaMultiprocessFilter(ProcessNameFilter(), 2, 1).filter(range(4)))

        self.assertEqual(len(logger_sink.items), 4)
        self.assertCountEqual(items, [ l.split(' ')[ 3] for l in logger_sink.items ] )
        self.assertCountEqual(items, [ l.split(' ')[-1] for l in logger_sink.items ] )

    def test_exception_logging(self):
        CobaConfig.logger = BasicLogger(MemoryIO())
        CobaConfig.cacher = NullCacher()
        
        list(CobaMultiprocessFilter(ExceptionFilter(), 2, 1).filter(range(4)))

        for item in CobaConfig.logger.sink.items:
            self.assertIn("Unexpected exception:", item)

    def test_not_picklable_logging(self):
        logger_sink = MemoryIO()
        CobaConfig.logger = BasicLogger(logger_sink)
        CobaConfig.cacher = NullCacher()

        list(CobaMultiprocessFilter(ProcessNameFilter(), 2, 1).filter([lambda a:1]))

        self.assertEqual(1, len(logger_sink.items))
        self.assertIn("pickle", logger_sink.items[0])

if __name__ == '__main__':
    unittest.main()