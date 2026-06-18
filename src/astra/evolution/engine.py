"""Deterministic evolutionary strategy selection."""

import random
import uuid
from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class Genome:
    strategy_id: str
    strategy_type: str
    parameters: dict[str, float]
    indicators: list[str] = field(default_factory=list)
    allowed_regimes: dict[str, list[str]] = field(default_factory=dict)
    generation: int = 0
    parent_ids: list[str] = field(default_factory=list)
    validation_scores: dict[str, float] = field(default_factory=dict)
    complexity: float = 1.0
    turnover: float = 0.0
    max_drawdown: float = 0.0


@dataclass
class SelectionResult:
    elites: list[Genome]
    children: list[Genome]
    rejected: list[Genome]


class EvolutionEngine:
    def __init__(self, seed: int = 0):
        self._rng = random.Random(seed)

    def fitness(self, genome: Genome) -> float:
        scores = genome.validation_scores
        return (
            0.25 * scores.get("oos_stability", 0.0)
            + 0.20 * scores.get("parameter_robustness", 0.0)
            + 0.15 * scores.get("regime_adaptability", 0.0)
            + 0.15 * max(0.0, 1.0 - genome.max_drawdown)
            + 0.10 * max(0.0, 1.0 - genome.turnover)
            + 0.10 * max(0.0, 1.0 - genome.complexity / 10.0)
            + 0.05 * scores.get("data_quality", 0.0)
            - 0.20 * scores.get("overfit_penalty", 0.0)
        )

    def evolve(
        self,
        population: list[Genome],
        parameter_bounds: dict[str, tuple[float, float]],
        elite_count: int = 2,
        child_count: int = 4,
        tournament_size: int = 3,
    ) -> SelectionResult:
        ranked = sorted(population, key=self.fitness, reverse=True)
        elites = ranked[:elite_count]
        rejected = ranked[elite_count:]
        children: list[Genome] = []
        while len(children) < child_count and ranked:
            parent_a = self._tournament(ranked, tournament_size)
            parent_b = self._tournament(ranked, tournament_size)
            child = self.crossover(parent_a, parent_b)
            child = self.mutate(child, parameter_bounds)
            children.append(child)
        return SelectionResult(elites=elites, children=children, rejected=rejected)

    def mutate(
        self,
        genome: Genome,
        parameter_bounds: dict[str, tuple[float, float]],
        mutation_scale: float = 0.10,
    ) -> Genome:
        params = dict(genome.parameters)
        if params:
            key = self._rng.choice(sorted(params))
            low, high = parameter_bounds.get(key, (params[key] * 0.5, params[key] * 1.5))
            width = high - low
            params[key] = min(high, max(low, params[key] + self._rng.uniform(-width, width) * mutation_scale))
        return replace(
            genome,
            strategy_id=str(uuid.uuid4()),
            parameters=params,
            generation=genome.generation + 1,
            parent_ids=[genome.strategy_id],
            validation_scores={},
        )

    def crossover(self, parent_a: Genome, parent_b: Genome) -> Genome:
        params: dict[str, float] = {}
        for key in sorted(set(parent_a.parameters) | set(parent_b.parameters)):
            if key in parent_a.parameters and key in parent_b.parameters:
                params[key] = (parent_a.parameters[key] + parent_b.parameters[key]) / 2.0
            elif key in parent_a.parameters:
                params[key] = parent_a.parameters[key]
            else:
                params[key] = parent_b.parameters[key]
        return Genome(
            strategy_id=str(uuid.uuid4()),
            strategy_type=parent_a.strategy_type,
            parameters=params,
            indicators=sorted(set(parent_a.indicators) | set(parent_b.indicators)),
            allowed_regimes=parent_a.allowed_regimes or parent_b.allowed_regimes,
            generation=max(parent_a.generation, parent_b.generation) + 1,
            parent_ids=[parent_a.strategy_id, parent_b.strategy_id],
            complexity=(parent_a.complexity + parent_b.complexity) / 2.0,
            turnover=(parent_a.turnover + parent_b.turnover) / 2.0,
            max_drawdown=max(parent_a.max_drawdown, parent_b.max_drawdown),
        )

    def _tournament(self, population: list[Genome], size: int) -> Genome:
        sample = self._rng.sample(population, k=min(size, len(population)))
        return max(sample, key=self.fitness)


def genome_from_manifest(strategy_id: str, manifest: dict[str, Any]) -> Genome:
    return Genome(
        strategy_id=strategy_id,
        strategy_type=str(manifest.get("strategy_type", "")),
        parameters={k: float(v) for k, v in manifest.get("parameters", {}).items() if isinstance(v, (int, float))},
        indicators=list(manifest.get("indicator_dependencies", [])),
        allowed_regimes=dict(manifest.get("regime_contract", {}).get("allowed_regimes", {})),
        generation=int(manifest.get("lineage", {}).get("generation_number", 0)),
    )
