# Polyglot Persistence Logistics Pipeline

This project implements a small logistics-style data platform that uses **polyglot** persistence: three different databases (graph, document, relational) behind a single API. It ingests events from a log file, routes them into the right database, handles out-of-order billing via eventual consistency, and exposes a unified view of a package’s history.

---

## 1. Problem and goals

Modern logistics and e‑commerce systems have very different query patterns:

- “Which drivers are in this zone right now?” (graph-style relationships)
- “Show me the full status history of this package.” (document-style history)
- “Insert this invoice and never allow duplicates.” (relational transactions)

Trying to force all of this into a single database typically leads to complex schemas and poor performance. This project instead uses polyglot persistence: each database is used where it’s strongest.

**Goals:**

- Read events from `events.log` at startup.
- Route events by type to:
  - Graph DB (driver location / zones).
  - Document DB (package history).
  - Relational DB (billing).
- Implement eventual consistency for billing using a retry queue (`retry_queue.json`).
- Provide a single HTTP endpoint to query a package’s complete, sorted history across all three stores.

---

## 2. High-level architecture

### 2.1 Components

- **App / event-router/API**  
  A Python web service that:
  - On startup:
    - Connects to MongoDB, PostgreSQL, Neo4j.
    - Reads and processes `events.log`.
    - Runs reconciliation on `retry_queue.json`.
  - At runtime:
    - Provides `GET /query/package/{package_id}` to fetch combined history.

- **Relational database (PostgreSQL)**  
  - Holds billing data in an `invoices` table.
  - Enforces a UNIQUE/PRIMARY KEY on `invoice_id` to prevent duplicates.

- **Document database (MongoDB)**  
  - Holds package status histories in a `packages` collection.
  - Each document corresponds to a single package:
    ```json
    {
      "package_id": "string",
      "status_history": [
        {
          "status": "string",
          "timestamp": "string (ISO 8601)",
          "...": "other event fields"
        }
      ]
    }
    ```

- **Graph database (Neo4j)**  
  - Models drivers, zones, and their relationships:
    - `(:Driver {driverId, latitude, longitude})`
    - `(:Zone {zoneId})`
    - `(:Driver)-[:LOCATED_IN]->(:Zone)`

- **Retry queue (`retry_queue.json`)**  
  - File-based dead-letter queue storing deferred `BILLING_EVENT`s when their package is not yet `DELIVERED`.

### 2.2 Data flow

1. **Ingestion**  
   The app reads `events.log` line by line. Each line is one JSON object. Malformed JSON is logged and skipped; the app keeps going.

2. **Routing by type**  
   For each parsed event:
   - `DRIVER_LOCATION_UPDATE`  
     → Neo4j: MERGE `Driver` and `Zone` nodes and the `[:LOCATED_IN]` relationship. Store latest latitude/longitude on the `Driver` node.
   - `PACKAGE_STATUS_CHANGE`  
     → MongoDB: Upsert a document for `package_id` and append to its `status_history` array.
   - `BILLING_EVENT`  
     → Check MongoDB for the package’s latest status:
       - If latest status is `DELIVERED` → insert into Postgres `invoices` table.
       - Otherwise → append the full event JSON to `retry_queue.json`.

3. **Reconciliation (eventual consistency)**  
   After the main log is processed, a reconciliation step runs:
   - Reads each event from `retry_queue.json`.
   - Re-checks MongoDB:
     - If the package is now `DELIVERED`, inserts the billing record into `invoices`.
     - If not, keeps the event for later.
   - Rewrites `retry_queue.json` with only the remaining unprocessed events.

4. **Unified query API**  
   `GET /query/package/{package_id}`:
   - **Document store** (MongoDB):  
     Fetch the package document and its `status_history`.
   - **Relational store** (Postgres):  
     `SELECT * FROM invoices WHERE package_id = ?`.
   - **Graph store** (Neo4j):  
     Extract `driver_id` from the `DELIVERED` status in `status_history` (if present), then query Neo4j for that driver’s `LOCATED_IN` zone.
   - Normalize all into a common event shape:
     ```json
     {
       "source_system": "document_store | relational_store | graph_store",
       "timestamp": "string (ISO 8601)",
       "event_details": {}
     }
     ```
   - Sort this list by `timestamp` in ascending order and return it as JSON.

To the client, everything looks like a simple ordered history, even though it comes from three different databases.

---

## 3. Running the project

### 3.1 Prerequisites

- Docker and Docker Compose installed.
- Git, if you’re cloning from a repository.

No local Postgres/Mongo/Neo4j install is required; everything runs in containers.

### 3.2 Setup and startup

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd <your-project-directory>
cp .env.example .env
# Edit .env if you want custom DB credentials or names

docker-compose up --build
Docker Compose will:

Start PostgreSQL, MongoDB, and Neo4j.

Use health checks to wait until each DB is ready:

Postgres: pg_isready -U <user>

Mongo: mongosh --eval 'db.runCommand("ping")'

Neo4j: curl -f http://localhost:7474 || exit 1

Only then start the app service (using depends_on: condition: service_healthy).
docker-compose logs -f app


You should see logs for:

Database initialization.

Event log processing.

Malformed JSON being logged and skipped.

Reconciliation completion.

API server listening on port 8000.


4. Using the API
4.1 Unified history endpoint
Endpoint:
GET /query/package/{package_id}


Example:
curl "http://localhost:8000/query/package/pkg-abc-123"


[
  {
    "source_system": "document_store",
    "timestamp": "2023-10-27T10:00:00Z",
    "event_details": {
      "status": "PICKED_UP",
      "timestamp": "2023-10-27T10:00:00Z",
      "package_id": "pkg-abc-123",
      "location": {
        "lat": 34.0522,
        "lon": -118.2437
      },
      "driver_id": "drv-xyz-789"
    }
  },
  {
    "source_system": "graph_store",
    "timestamp": "2023-10-27T10:00:05Z",
    "event_details": {
      "driver": {
        "driverId": "drv-xyz-789",
        "latitude": 34.053,
        "longitude": -118.2445
      },
      "zone": "zone-la-downtown"
    }
  },
  {
    "source_system": "relational_store",
    "timestamp": "2023-10-27T10:15:00Z",
    "event_details": {
      "invoice_id": "inv-001",
      "package_id": "pkg-abc-123",
      "customer_id": "cust-456",
      "amount": 15.99,
      "status": "pending",
      "created_at": "2023-10-27T10:15:00Z"
    }
  }
]


.
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI entrypoint + startup hooks
│   ├── db_connections.py    # Mongo, Postgres, Neo4j clients
│   ├── handlers.py          # Event handlers for each event.type
│   ├── event_router.py      # Reads events.log and routes events
│   ├── reconciler.py        # Processes retry_queue.json
│   └── api.py               # Defines GET /query/package/{id}
├── docs/
│   └── ADR-001-Data-Store-Selection.md
├── docker-compose.yml
├── Dockerfile
├── events.log
├── retry_queue.json
├── .env.example
├── requirements.txt
└── README.md

6. How this maps to the requirements
6.1 Docker & orchestration (Requirement 1)
docker-compose.yml is at the project root.

It defines at least four services:

app (event-router/API).

postgres (relational).

mongo (document).

neo4j (graph).

Each database service has a healthcheck block.

The app service has depends_on with condition: service_healthy for all three databases.

Running docker-compose up brings the stack up; all services reach a healthy state within a few minutes.

6.2 Automatic ingestion from events.log (Requirement 2)
The app expects events.log to be mounted in its working directory.

On startup it:

Opens events.log.

Reads each line.

Parses JSON (logging and skipping malformed lines instead of crashing).

Calls the correct handler function by event.type.

After startup, you can query the databases to see the persisted data.

6.3 Graph persistence for DRIVER_LOCATION_UPDATE (Requirement 3)
Ensures:

Nodes with labels Driver and Zone.

Driver nodes have driverId and location fields (e.g. latitude, longitude).

Zone nodes have zoneId.

LOCATED_IN relationship exists from Driver to Zone.

Example verification query in Neo4j:

MATCH (d:Driver {driverId: 'drv-test-123'})-[:LOCATED_IN]->(z:Zone)
RETURN d, z.zoneId;


6.4 Document persistence for PACKAGE_STATUS_CHANGE (Requirement 4)
Uses a packages collection in MongoDB.

Each PACKAGE_STATUS_CHANGE event:

Upserts a document by package_id.

Pushes a new entry into status_history with status, timestamp, and other fields from the event payload.

The history list for a package will contain as many entries as the number of PACKAGE_STATUS_CHANGE events processed for that package.

6.5 Billing persistence and uniqueness (Requirements 5 & 6)
invoices table in Postgres contains:

invoice_id (PRIMARY KEY, UNIQUE).

package_id.

customer_id.

amount.

status.

created_at.

When a valid BILLING_EVENT is processed (i.e. after DELIVERED):

A row is inserted into invoices.

If an event is processed again with the same invoice_id, the UNIQUE constraint prevents a duplicate; the app logs an error or conflict, but does not insert a second row.

6.6 Retry queue and reconciliation (Requirements 7 & 8)
If a BILLING_EVENT arrives before the package is DELIVERED:

It is not inserted into Postgres.

Instead, the event is appended to retry_queue.json (one JSON object per line).

The reconciliation process:

Reads retry_queue.json.

For each event, re-checks MongoDB to see if the package is now DELIVERED.

Inserts invoices when the precondition is met.

Rewrites retry_queue.json with only the remaining unprocessed events.

This demonstrates eventual consistency: when the required status eventually appears, the system catches up and becomes consistent.

6.7 Unified query API (Requirement 9)
The API endpoint GET /query/package/{package_id}:

Fetches package history from MongoDB.

Fetches invoices from Postgres.

Uses the driver_id from the package’s DELIVERED status to fetch the driver’s zone from Neo4j.

Normalizes all data into a common format with source_system, timestamp, and event_details.

Sorts the combined list by timestamp ascending.

Returns a JSON array.

6.8 Architecture Decision Record and environment variables (Requirements 10 & 11)
docs/ADR-001-Data-Store-Selection.md:

Explains the context (three query patterns).

States the decision (graph/doc/relational).

Discusses consequences (pros/cons, operational complexity, eventual consistency).

.env.example:

Lives at the project root.

Lists all environment variables needed for DB connections (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, MONGO_USER, MONGO_PASSWORD, NEO4J_USER, NEO4J_PASSWORD, etc.).

Uses placeholder values only (no real secrets).

7. Extending the project
Some ideas if you want to build on this:

Replace events.log with a real message broker (Kafka, RabbitMQ).

Add metrics and structured logging for each handler.

Run reconciliation periodically as a background job instead of only at startup.

Implement more complex business rules (e.g. partial refunds, cancellations).

Introduce a second API endpoint to query by driver, zone, or time range.

8. Summary
This project shows how to:

Use multiple specialized databases in a single application.

Handle real-world issues like out-of-order events using eventual consistency.

Build a clean, unified API on top of a polyglot data backend.

Despite the complexity behind the scenes, the client only needs to hit one endpoint to get a clear, chronological view of any package’s journey.

"# Polyglot-Persistence-Layer-for-a-Real-time-Logistics-Platform" 
