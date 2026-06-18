"""Evolution service wired to memory and validation evidence."""

from astra.evolution.engine import EvolutionEngine, Genome, SelectionResult
from astra.memory.engine import MemoryEngine, MemoryQuery


class EvolutionService:
    def __init__(self, memory: MemoryEngine, seed: int = 0):
        self._memory = memory
        self._engine = EvolutionEngine(seed=seed)

    async def evolve_with_memory(
        self,
        population: list[Genome],
        parameter_bounds: dict[str, tuple[float, float]],
        strategy_type: str,
    ) -> SelectionResult:
        memories = await self._memory.retrieve(
            MemoryQuery(text=strategy_type, tags=[strategy_type], limit=20)
        )
        banned_topics = {
            row.topic
            for row in memories
            if row.status in {"active", "disputed"} and row.contradiction_count == 0 and "failure" in row.claim.lower()
        }
        filtered = [
            genome for genome in population
            if not any(topic in str(genome.parameters).lower() for topic in banned_topics)
        ]
        return self._engine.evolve(
            population=filtered or population,
            parameter_bounds=parameter_bounds,
        )
