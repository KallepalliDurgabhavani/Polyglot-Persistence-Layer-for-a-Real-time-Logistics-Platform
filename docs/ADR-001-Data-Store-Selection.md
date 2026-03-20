# ADR-001: Data Store Selection
## Context
Handle graph relationships (drivers/zones), document histories (packages), relational transactions (billing) efficiently.
## Decision
- Graph: Neo4j for traversals/relationships [web:11].
- Document: MongoDB for schema-flexible append-only histories with upsert [web:16].
- Relational: Postgres for ACID invoices with unique constraints.
## Consequences
Graph excels at queries like "drivers in zone" but poor for transactions. Document scales histories without joins. Relational ensures no dupes/integrity. Overall: Better perf per pattern, but added complexity in federation/eventual consistency via queue [web:19].
