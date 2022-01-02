import inspect
import gzip

from abc import abstractmethod, ABC
from collections.abc import Iterator
from threading import Lock, Condition
from pathlib import Path
from typing import Union, Dict, TypeVar, Iterable, Optional, Callable, Generic

from coba.exceptions import CobaException

_K = TypeVar("_K")
_V = TypeVar("_V")

class Cacher(Generic[_K, _V], ABC):
    """The interface for a cacher."""
    
    @abstractmethod
    def __contains__(self, key: _K) -> bool:
        """Determine if key is in cache."""
        ...

    @abstractmethod
    def get(self, key: _K) -> _V:
        """Get a key from the cache.

        Args:
            key: The key to retreive from the cache.
        """
        ...

    @abstractmethod
    def put(self, key: _K, value: _V) -> None:
        """Put a key and its bytes into the cache. 

        In the case of a key collision nothing will be put.

        Args:
            key: The key to store in the cache.
            value: The value that should be cached for the key.
        """
        ...

    @abstractmethod
    def rmv(self, key: _K) -> None:
        """Remove a key from the cache.

        Args:
            key: The key to remove from the cache.
        """
        ...
    
    @abstractmethod
    def get_put(self, key: _K, getter: Callable[[], _V]) -> _V:
        """Get a key from the cache. 
        
        If the key is not in the cache put it first using getter.

        Args:
            key: The key to get from the cache.
            getter: A method for getting the value if necessary.
        """
        ...

class NullCacher(Cacher[_K, _V]):
    """A cacher which does not cache any data."""

    def __init__(self) -> None:
        """Instantiate a NullCacher."""
        pass

    def __contains__(self, key: _K) -> bool:
        return False

    def get(self, key: _K) -> _V:
        raise Exception("the key didn't exist in the cache")

    def put(self, key: _K, value: _V) -> None:
        pass

    def rmv(self, key: _K):
        pass
    
    def get_put(self, key: _K, getter: Callable[[], _V]) -> _V:
        return getter()

class MemoryCacher(Cacher[_K, _V]):
    """A cacher that caches in memory."""
    
    def __init__(self) -> None:
        """Instantiate a MemoryCacher."""
        self._cache: Dict[_K,_V] = {}

    def __contains__(self, key: _K) -> bool:
        return key in self._cache

    def get(self, key: _K) -> _V:
        return self._cache[key]

    def put(self, key: _K, value: _V) -> None:
        self._cache[key] = list(value) if inspect.isgenerator(value) else value  

    def rmv(self, key: _K) -> None:
        if key in self:
            del self._cache[key]
    
    def get_put(self, key: _K, getter: Callable[[], _V]) -> _V:
        if key not in self: 
            self.put(key,getter())
        return self.get(key)

class DiskCacher(Cacher[str, Iterable[bytes]]):
    """A cacher that writes to disk.

    The DiskCacher compresses all values before writing to conserve disk space.
    """

    def __init__(self, cache_dir: Union[str, Path] = None) -> None:
        """Instantiate a DiskCacher.

        Args:
            cache_dir: The directory path where all given keys will be cached as files
        """
        self.cache_directory = cache_dir

    @property
    def cache_directory(self) -> Optional[str]:
        """The directory where the cache will write to disk."""
        return str(self._cache_dir) if self._cache_dir is not None else None

    @cache_directory.setter
    def cache_directory(self,value:Union[Path,str,None]) -> None:
        self._cache_dir = value if isinstance(value, Path) else Path(value).expanduser() if value else None
        if self._cache_dir is not None: self._cache_dir.mkdir(parents=True, exist_ok=True)

    def __contains__(self, key: str) -> bool:
        return self._cache_dir is not None and self._cache_path(key).exists()

    def get(self, key: str) -> Iterable[bytes]:
        if key not in self: return []

        try:
            with gzip.open(self._cache_path(key), 'rb') as f:
                for line in f:
                    yield line.rstrip(b'\r\n')
        except:
            #do we want to clear the cache here if something goes wrong?
            #it seems reasonable since this would indicate the cache is corrupted...
            raise

    def put(self, key: str, value: Iterable[bytes]):

        if self._cache_dir is None: return

        try:
            if key in self: return

            if isinstance(value,bytes): value = [value]

            with gzip.open(self._cache_path(key), 'wb+', compresslevel=6) as f:
                for line in value:
                    f.write(line.rstrip(b'\r\n') + b'\r\n')
        except:
            if key in self: self.rmv(key)
            raise

    def rmv(self, key: str) -> None:


        if self._cache_path(key).exists(): self._cache_path(key).unlink()

    def get_put(self, key: str, getter: Callable[[], Iterable[bytes]]) -> Iterable[bytes]:


        if self._cache_dir is None:
            return getter()

        if key not in self: 
            self.put(key, getter())

        return self.get(key)

    def _cache_name(self, key: str) -> str:
        if not all(c.isalnum() or c in (' ','.','_') for c in key):
            raise CobaException(f"A key was given to DiskCacher which couldn't be made into a file, {key}")

        return f"{key}.gz"
        #return f"{md5(key.encode('utf-8')).hexdigest()}.gz"

    def _cache_path(self, key: str) -> Path:
        return self._cache_dir/self._cache_name(key)

class ConcurrentCacher(Cacher[_K, _V]):
    """A cacher that is multi-process safe."""

    def __init__(self, cache:Cacher[_K, _V], dict:Dict[_K,int], lock: Lock, cond: Condition):
        """Instantiate a ConcurrentCacher.
        
        Args:
            cache: The base cacher that we wish to make multi-process safe.
            dict: This must be a multiprocessing dict capable of communicating across processes.
            lock: A lock that can be marshalled to other processes.
            cond: A condition that can be marshaled to other processes.
        """
        #With more thought the 3 concurrency objects could probably be reduced to just 1 or 2.

        self._cache = cache
        self._lock  = lock
        self._dict  = dict
        self._cond  = cond

        self.read_waits  = 0
        self.write_waits = 0

    def __contains__(self, key: _K) -> bool:
        return key in self._cache

    def _acquired_read_lock(self, key: _K) -> bool:
        with self._lock:
            if key not in self._dict or self._dict[key]>=0:
                self._dict[key] = self._dict.get(key,0)+1
                return True
            return False
    
    def _acquire_read_lock(self, key: _K):
        self.read_waits += 1
        while not self._acquired_read_lock(key):
            with self._cond:
                self._cond.wait()
        self.read_waits -= 1

    def _release_read_lock(self, key: _K):
        with self._lock:
            self._dict[key] -= 1
        
        with self._cond:
            self._cond.notify_all()

    def _acquired_write_lock(self, key: _K) -> bool:
        with self._lock:
            if key not in self._dict or self._dict[key] == 0:
                self._dict[key] = -1
                return True
            return False

    def _acquire_write_lock(self, key: _K):
        self.write_waits += 1
        while not self._acquired_write_lock(key):
            with self._cond:
                self._cond.wait()
        self.write_waits -= 1

    def _switch_write_to_read_lock(self, key: _K):
        with self._lock:
            self._dict[key] = 1

    def _release_write_lock(self, key: _K):
        with self._lock:
            self._dict[key] = 0
        
        with self._cond:
            self._cond.notify_all()

    def _generator_release(self, value: _V, release: Callable[[],None]):
        for v in value:
            yield v

        release()

    def get(self, key:_K) -> _V:    
        
        self._acquire_read_lock(key)
        value = self._cache.get(key)

        if inspect.isgenerator(value) or isinstance(value,Iterator):
            return self._generator_release(value,lambda:self._release_read_lock(key))
        else:
            self._release_read_lock(key)
            return value

    def put(self, key: _K, value: _V):

        self._acquire_write_lock(key)
        self._cache.put(key, value)
        self._release_write_lock(key)        

    def rmv(self,key: _K):

        self._acquire_write_lock(key)
        self._cache.rmv(key)
        self._release_write_lock(key)

    def get_put(self, key: _K, getter: Callable[[],_V]):

        ### I'm pretty sure there is still a potential race-condition here.
        ### We need to get a read-lock probably before the first get check
        ### Otherwise it is possible for an item to be removed from the cache
        ### after the contains check and before the get. Given how I use
        ### the cache currently though this is very unlikely to happen so 
        ### I'm not going to fix it at this time. 
        if key in self._cache:
            return self.get(key)
        else:
            self._acquire_write_lock(key)
            if key not in self:
                
                value = self._cache.get_put(key, getter)
                self._switch_write_to_read_lock(key)
                
                if inspect.isgenerator(value) or isinstance(value,Iterator):
                    return self._generator_release(value,lambda:self._release_read_lock(key))
                else:
                    self._release_read_lock(key)
                    return value
                    
            self._switch_write_to_read_lock(key)
            value = self.get(key)

            self._release_read_lock(key)
            return value
