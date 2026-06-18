# ASTRA Production Architecture

ASTRA is organized as an event-driven research platform. Generated strategies remain sandboxed and paper-only. Research state is persisted through SQLAlchemy models, while Redis is used for cross-worker event publication.

## Runtime Services

- `backend`: FastAPI API, WebSocket bridge, planner/build/deployment orchestration.
- `postgres`: canonical event, experiment, memory, validation, lineage, and deployment store.
- `redis`: low-latency event fanout for workers and UI streaming.
- `research workers`: consume events for validation, memory extraction, evolution, and monitoring.

## Persistence

SQLAlchemy models live in `src/astra/db/models.py`.

Primary entities:

- `events`
- `hypotheses`
- `strategies`
- `datasets`
- `experiments`
- `validation_runs`
- `memory_items`
- `paper_deployments`

SQLite remains available for local legacy session storage. Production deployments should set:

```bash
ASTRA_DATABASE_URL=postgresql+asyncpg://astra:astra@postgres:5432/astra
ASTRA_REDIS_URL=redis://redis:6379/0
ASTRA_ENABLE_PRODUCTION_PERSISTENCE=1
ASTRA_ENABLE_DURABLE_EVENTS=1
ASTRA_ENABLE_REDIS_EVENTS=1
```

Run migrations:

```bash
alembic upgrade head
```

## Event Flow

`AstraEvent` records are append-only:

```text
HypothesisCreated
 → StrategyBuilt
 → ValidationRunCompleted
 → MemoryUpdated
 → EvolutionGenerationCreated
 → PaperDeploymentCreated
 → DeploymentSuspended
```

The event bus persists events to Postgres and publishes them to Redis. Handlers can subscribe by exact event type or wildcard.

## Safety

- No live trading integration is added.
- Broker deployment path remains paper-only.
- Direct manual paper orders are disabled unless `ASTRA_ENABLE_MANUAL_PAPER_ORDERS=1`.
- API-key auth activates when `ASTRA_API_KEY` is configured.
- Rotate any key that was printed, pasted, logged, or shared outside local machine.
- Strategy deployments are reversible via stop/suspend events.
- Risk engine blocks exposure, concentration, drawdown, short exposure, and intraday VaR breaches.
- All generated strategies include lineage hashes and metadata artifacts.

## API

Production research endpoints are mounted under `/api/v1`:

- `POST /api/v1/db/init`
- `POST /api/v1/events`
- `POST /api/v1/memory`
- `POST /api/v1/memory/search`
- `POST /api/v1/evolution/evolve`
- `POST /api/v1/validation/decide`

These APIs are intentionally evidence-oriented. They store and score research process artifacts, not trading recommendations.
