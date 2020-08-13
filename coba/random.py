"""A custom implementation of random number generation.

This module follows the pattern of the standard library's random module by creating
by instantiation an internal, global Random class and then referencing that in all
the public methods in order to maintain state.

Remarks:
    This implementation has been made to guarantee the reproducibility of benchmark tests
    according to integer seeds across all versions of Python. The standard implementation 
    of random within Python has had a few variations in implementation in the past and 
    could always change in the future, making randomization by seed potentially non-fixed.

TODO: Add unit tests for randint
TODO: Add unit tests for random
TODO: Add unit tests for choice
"""

import math
import random as std_random

from typing import Optional, Sequence, Any, List

class Random:
    """A random number generator via a linear congruential generator."""

    def __init__(self, seed: Optional[int] = None) -> None:
        """Instantiate a Random class.

        Args:
            seed: the seed to start random number generation.

        Remarks:
            The values for a,c,m below are taken from L’ecuyer (1999). In this paper he notes that
            these values for LCG should have an overall period of m though the period of lower bits 
            will be much shorter. A solution he offers to this problem is to use much larger m (e.g., 
            2**128) and then only use the the top n most significant digits. For now, we aren't doing that.
        
        References:
            L’ecuyer, Pierre. "Tables of linear congruential generators of different sizes 
            and good lattice structure." Mathematics of Computation 68.225 (1999): 249-260.
        """

        self._m = 2**30
        self._a = 116646453
        self._c = 9

        self._m_is_power_of_2 = math.log2(self._m).is_integer()
        self._m_minus_1       = self._m-1

        self._seed: int = std_random.randint(0,self._m_minus_1) if seed is None else seed

    def randoms(self, n:int=1) -> Sequence[float]:
        """Generate `n` random numbers in [0,1].

        Args:
            n: How many random numbers should be generated.

        Returns:
            The `n` generated random numbers in [0,1].
        """

        return [number/self._m_minus_1 for number in self._next(n)]

    def shuffle(self, sequence: Sequence[Any]) -> Sequence[Any]:
        """Shuffle the order of items in a sequence.

        Args:
            sequence: The sequence of items that are to be shuffled.

        Returns:
            A new sequence with the order of items shuffled.
        """

        n = len(sequence)
        r = self.randoms(n)
        l = list(sequence)

        for i in range(n):
            j = min(int(i + (r[i] * (n-i))), n-1) #min() handles the edge case of r[i]==1
            
            l[i], l[j] = l[j], l[i]

        return l

    def _next(self, n: int) -> Sequence[int]:
        """Generate `n` uniform random numbers in [0,m-1]

        Random numbers are generated using a linear congruential generator

        Args:
            n: The number of random numbers to generate.

        Returns:
            The `n` generated random numbers in [0,m-1].
        """
        
        if n <= 0 or not isinstance(n, int):
            raise ValueError("n must be an integer greater than 0")

        numbers: List[int] = []

        for _ in range(n):

            if self._m_is_power_of_2:
                self._seed = int((self._a * self._seed + self._c) & (self._m_minus_1))
            else:
                self._seed = int((self._a * self._seed + self._c) % self._m)

            numbers.append(self._seed)

        return numbers

_random = Random()

def seed(seed: Optional[int]) -> None:
    """Set the seed for generating random numbers in this module.
    
    Args:
        seed: The seed for generating random numbers.

    Remarks:
        Note, this seed does not affect random numbers generated by the standard library
    """

    global _random

    _random = Random(seed)

def random() -> float:
    """Generate a uniform random number in [0,1]."""

    return randoms(1)[0]

def randoms(n: int) -> Sequence[float]:
    """Generate `n` uniform random numbers in [0,1].

    Args:
        n: How many random numbers should be generated.

    Returns:
        The `n` generated random numbers in [0,1].
    """

    return _random.randoms(n)

def randint(a:int, b:int) -> int:
    """Generate a uniform random integer in [a, b].
    
    Args:
        a: The inclusive lower bound for the random integer.
        b: The inclusive upper bound for the random integer.
    """
    
    return (min(int( (b-a+1) * random()), b-1) + a)

def choice(seq: Sequence[Any]) -> Any:
    """Choose a random item from the given sequence.
    
    Args:
        seq: The sequence to pick randomly from.
    """
    
    return seq[randint(0, len(seq)-1)]

def shuffle(array_like: Sequence[Any]) -> Sequence[Any]:
    """Shuffle the order of items in a sequence.

    Args:
        sequence: The sequence of items that are to be shuffled.

    Returns:
        A new sequence with the order of items shuffled.
    """

    return _random.shuffle(array_like)