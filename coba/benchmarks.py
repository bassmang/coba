"""The benchmarks module contains core benchmark functionality and protocols.

This module contains the abstract interface expected for Benchmark implementations. This 
module also contains several Benchmark implementations and Result data transfer class.

TODO Finish adding docstrings to Result
"""

import json
import collections

from abc import ABC, abstractmethod
from typing import Union, Sequence, List, Callable, Generic, TypeVar, Dict, Any, overload, cast
from itertools import count, repeat, groupby
from statistics import median

from coba.simulations import Interaction, LazySimulation, Simulation, Context, Action
from coba.learners import Learner
from coba.execution import ExecutionContext
from coba.statistics import SummaryStats

_C = TypeVar('_C', bound=Context)
_A = TypeVar('_A', bound=Action)

class Result:

    def __init__(self,
        learner_name:str,
        simulation_index:int,
        batch_index: int,
        interaction_count: int,
        median_feature_count: int,
        median_action_count: int,
        stats: SummaryStats) -> None:

        self._learner_name         = learner_name
        self._simulation_index     = simulation_index
        self._batch_index          = batch_index
        self._median_feature_count = median_feature_count
        self._median_action_count  = median_action_count
        self._interaction_count    = interaction_count
        self._stats                = stats

    @property
    def learner_name(self) -> str:
        return self._learner_name

    @property
    def simulation_index(self) -> int:
        return self._simulation_index

    @property
    def batch_index(self) -> int:
        return self._batch_index

    @property
    def interaction_count(self) -> int:
        return self._interaction_count

    @property
    def median_feature_count(self) -> int:
        return self._median_feature_count

    @property
    def median_action_count(self) -> int:
        return self._median_action_count

    @property
    def stats(self) -> SummaryStats:
        return self._stats

    def to_dict(self) -> Dict[str, Any]:
        return {
            "learner_name"        : self._learner_name,
            "simulation_index"    : self._simulation_index,
            "batch_index"         : self._batch_index,
            "interaction_count"   : self._interaction_count,
            "median_feature_count": self._median_feature_count,
            "median_action_count" : self._median_action_count,
            "stats"               : self._stats
        }

class Benchmark(Generic[_C,_A], ABC):
    """The interface for Benchmark implementations."""

    @abstractmethod
    def evaluate(self, learner_factories: Sequence[Callable[[],Learner[_C,_A]]]) -> Sequence[Result]:
        """Calculate the performance for a provided bandit Learner.

        Args:
            learner_factories: A sequence of functions to create Learner instances. Each function 
                should always create the same Learner in order to get an unbiased performance 
                Result. This method can be as simple as `lambda: MyLearner(...)`.

        Returns:
            The resulting performance statistics for each given learner to evaluate.

        Remarks:
            The learner factory is necessary because a Result can be calculated using
            observed performance over several simulations. In these cases the easiest 
            way to reset a learner's learned policy is to create a new learner.
        """
        ...

class UniversalBenchmark(Benchmark[_C,_A]):
    """An on-policy Benchmark using samples drawn from simulations to estimate performance statistics."""

    @staticmethod
    def from_json(json_val:Union[str, Dict[str,Any]]) -> 'UniversalBenchmark':
        """Create a UniversalBenchmark from configuration IO.

        Args:
            json_val: Either a json string or the decoded json object.

        Returns:
            The UniversalBenchmark representation of the given JSON string or object.
        """

        if isinstance(json_val, str):
            config = cast(Dict[str,Any],json.loads(json_val))
        else:
            config = json_val

        config = ExecutionContext.TemplatingEngine.parse(config)

        is_singular = isinstance(config["simulations"], dict)
        sim_configs = config["simulations"] if not is_singular else [ config["simulations"] ]

        #by default load simulations lazily
        for sim_config in sim_configs:
            if "lazy" not in sim_config:
                sim_config["lazy"] = True

        simulations = [ Simulation.from_json(sim_config) for sim_config in sim_configs ]

        if "count" in config["batches"]:
            return UniversalBenchmark(simulations, batch_count=config["batches"]["count"])
        else:
            return UniversalBenchmark(simulations, batch_size=config["batches"]["size"])    

    @overload
    def __init__(self, 
        simulations: Sequence[Simulation[_C,_A]],
        *, 
        batch_count: int) -> None:
        ...

    @overload
    def __init__(self, 
        simulations: Sequence[Simulation[_C,_A]],
        *, 
        batch_size: Union[int, Sequence[int], Callable[[int],int]]) -> None:
        ...

    def __init__(self,
        simulations: Sequence[Simulation[_C,_A]], 
        batch_count: int = None, 
        batch_size : Union[int, Sequence[int], Callable[[int],int]] = None) -> None:
        """Instantiate a UniversalBenchmark.

        Args:
            simulations: A sequence of simulations to benchmark against.
            batch_count: How many interaction batches per simulation (batch_size will be spread evenly).
            batch_size: An indication of how large every batch should be. If batch_size is an integer
                then simulations will run until completion with batch sizes of the given int. If 
                batch_size is a sequence of integers then `sum(batch_size)` interactions will be 
                pulled from simulations and batched according to the sequence. If batch_size is a 
                function then simulation run until completion with batch_size determined by function.
        """

        self._simulations = simulations
        self._batch_count = batch_count
        self._batch_size  = batch_size

    def evaluate(self, learner_factories: Sequence[Callable[[],Learner[_C,_A]]]) -> Sequence[Result]:
        """Collect observations of a Learner playing the benchmark's simulations to calculate Results.

        Args:
            learner_factories: See the base class for more information.

        Returns:
            See the base class for more information.
        """

        def feature_count(i: Interaction) -> int:
            return len(i.context) if isinstance(i.context,tuple) else 0 if i.context is None else 1

        def action_count(i: Interaction) -> int:
            return len(i.actions)

        results: List[Result] = []

        for simulation_index, simulation in enumerate(self._simulations):
            try:

                if isinstance(simulation, LazySimulation):
                    simulation.load()

                interaction_count    = len(simulation.interactions)
                median_feature_count = cast(int,median([feature_count(i) for i in simulation.interactions]))
                median_action_count  = cast(int,median([action_count(i) for i in simulation.interactions]))

                batch_sizes   = self._batch_sizes(len(simulation.interactions))
                batch_indexes = iter(b for i, s in enumerate(batch_sizes) for b in repeat(i,s) )

                for learner_index, learner_factory in enumerate(learner_factories):

                    batched_indexed_interactions = zip(batch_indexes,simulation.interactions)

                    learner       = learner_factory()

                    for batch_group in groupby(batched_indexed_interactions, lambda t: t[0]):
                        
                        keys     = []
                        contexts = []
                        choices  = []
                        actions  = []

                        for _, i in batch_group[1]:

                            choice = learner.choose(i.key, i.context, i.actions)

                            keys    .append(i.key)
                            contexts.append(i.context)
                            choices .append(choice)
                            actions .append(i.actions[choice])

                        rewards = simulation.rewards(list(zip(keys, choices)))
                        stats   = SummaryStats.from_observations(rewards)
                        name    = self._safe_name(learner_index, learner) #type: ignore #pylance indicates an incorrect error here

                        for (key,context,action,reward) in zip(keys,contexts,actions,rewards):
                            learner.learn(key,context,action,reward)

                        results.append(Result(
                            name, 
                            simulation_index, 
                            batch_group[0], 
                            interaction_count, 
                            median_feature_count, 
                            median_action_count,
                            stats
                        ))

            except Exception as e:
                ExecutionContext.Logger.log(f"     * {e}")

            if isinstance(simulation, LazySimulation):
                simulation.unload()

        return results
    
    def _safe_name(self, learner_index:int, learner: Learner[_C,_A]) -> str:
        try:
            return learner.name
        except:
            return str(learner_index)

    def _batch_sizes(self, n_interactions: int) -> Sequence[int]:

        if self._batch_count is not None:
            
            batches   = [int(float(n_interactions)/(self._batch_count))] * self._batch_count
            remainder = n_interactions % self._batch_count
            
            if remainder > 0:
                spacing = float(self._batch_count)/remainder
                for i in range(remainder): batches[int(i*spacing)] += 1

            return batches
        
        if isinstance(self._batch_size, int): 
            return [self._batch_size] * int(float(n_interactions)/self._batch_size)

        if isinstance(self._batch_size, collections.Sequence): 
            return self._batch_size

        if callable(self._batch_size):
            batch_size_iter        = (self._batch_size(i) for i in count())
            next_batch_size        = next(batch_size_iter)
            remaining_interactions = n_interactions
            batch_sizes: List[int] = []

            while remaining_interactions > next_batch_size:
                batch_sizes.append(next_batch_size)
                remaining_interactions -= next_batch_size
                next_batch_size  = next(batch_size_iter)
            
            return batch_sizes
        
        raise Exception("We were unable to determine batch size from the supplied parameters")