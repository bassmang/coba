import math

from itertools import count, repeat
from typing import Sequence, Dict, Tuple, Any

from coba.random import CobaRandom
from coba.encodings import InteractionsEncoder, OneHotEncoder

from coba.environments.primitives import Context, Action
from coba.environments.simulated.primitives import LambdaSimulation

class LinearSyntheticSimulation(LambdaSimulation):
    
    def __init__(self, 
        n_interactions: int = 500, 
        n_actions: int = 10, 
        n_context_feats:int = 10, 
        n_action_feats:int = 10, 
        r_noise_var:float = 1/1000,
        interactions: Sequence[str] = ["a","xa"],
        seed:int=1) -> None:

        self._n_actions          = n_actions
        self._n_context_features = n_context_feats
        self._n_action_features  = n_action_feats
        self._seed               = seed
        self._r_noise_var        = r_noise_var
        self._X                  = interactions

        rng = CobaRandom(seed)
        X_encoder = InteractionsEncoder(self._X)

        dummy_context = list(range(max(1,n_context_feats)))
        dummy_action  = list(range(n_action_feats)) if n_action_feats else list(range(n_actions))
        feature_count = len(X_encoder.encode(x=dummy_context,a=dummy_action))

        normalize = lambda X: [ rng.random()*x/sum(X) for x in X]
        identity  = lambda n: OneHotEncoder().fit_encode(range(n))

        weights = normalize(rng.randoms(feature_count)) # we normalize weights so that reward will be in [0,1]
        actions = ( [rng.randoms(n_action_feats) for _ in range(n_actions)] for _ in count()) if n_actions else repeat(identity(n_actions))
        A_ident = None if n_action_feats else identity(n_actions)

        def context(index:int, rng: CobaRandom) -> Context:
            return rng.randoms(n_context_feats) if n_context_feats else None

        def actions(index:int, context: Context, rng: CobaRandom) -> Sequence[Action]:
            return  [rng.randoms(n_action_feats) for _ in range(n_actions)] if n_action_feats else A_ident

        def reward(index:int, context:Context, action:Action, rng: CobaRandom) -> float:

            W = weights
            X = context or [1]
            A = action
            F = X_encoder.encode(x=X,a=A)

            r = sum([w*f for w,f in zip(W,F)])
            e = (rng.random()-1/2)*math.sqrt(12)*math.sqrt(self._r_noise_var)
            
            return min(1,max(0,r+e))

        super().__init__(n_interactions, context, actions, reward, seed)

    @property
    def params(self) -> Dict[str, Any]:
        """Paramaters describing the simulation."""

        return { 
            "n_A"    : self._n_actions,
            "n_C_phi": self._n_context_features,
            "n_A_phi": self._n_action_features,
            "r_noise": self._r_noise_var,
            "X"      : self._X,
            "seed"   : self._seed
        }

    def __str__(self) -> str:
        return f"LinearSynth(A={self._n_actions},c={self._n_context_features},a={self._n_action_features},X={self._X},seed={self._seed})"

class LocalSyntheticSimulation(LambdaSimulation):

    def __init__(self,
        n_interactions: int = 500,
        n_contexts: int = 200,
        n_context_features: int = 2,
        n_actions: int = 10,
        seed: int = 1) -> None:

        self._n_interactions     = n_interactions
        self._n_context_features = n_context_features
        self._n_contexts         = n_contexts
        self._n_actions          = n_actions
        self._seed               = seed

        rng = CobaRandom(self._seed)

        contexts = [ tuple(rng.randoms(n_context_features)) for _ in range(self._n_contexts) ]        
        actions  = OneHotEncoder().fit_encode(range(n_actions))
        rewards  = {}

        for context in contexts:
            for action in actions:
                rewards[(context,action)] = rng.random()

        def context_generator(index:int, rng: CobaRandom):
            return rng.choice(contexts)

        def action_generator(index:int, context:Tuple[float,...], rng: CobaRandom):
            return actions

        def reward_function(index:int, context:Tuple[float,...], action: Tuple[int,...], rng: CobaRandom):
            return rewards[(context,action)]

        return super().__init__(self._n_interactions, context_generator, action_generator, reward_function, seed)

    @property
    def params(self) -> Dict[str, Any]:
        """Paramaters describing the simulation."""

        return { 
            "n_A"    : self._n_actions,
            "n_C"    : self._n_contexts,
            "n_C_phi": self._n_context_features,
            "seed"   : self._seed
        }

    def __str__(self) -> str:
        return f"LocalSynth(A={self._n_actions},C={self._n_contexts},c={self._n_context_features},seed={self._seed})"