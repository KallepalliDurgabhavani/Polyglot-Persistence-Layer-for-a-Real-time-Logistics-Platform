import os
import asyncpg
from neo4j import AsyncGraphDatabase
from pymongo import MongoClient
import logging
logger = logging.getLogger(__name__)
mongo_client = None
neo4j_driver = None
pg_pool = None
mongo_db = None
async def init_db():
    global mongo_client, neo4j_driver, pg_pool, mongo_db
    # Mongo
    mongo_uri = f"mongodb://{os.getenv('MONGO_USER')}:{os.getenv('MONGO_PASSWORD')}@mongo:27017/"
    mongo_client = MongoClient(mongo_uri)
    mongo_db = mongo_client['logistics']
    mongo_db.packages.create_index('package_id')
    # Neo4j
    neo4j_uri = f"bolt://{os.getenv('NEO4J_USER')}:{os.getenv('NEO4J_PASSWORD')}@neo4j:7687"
    neo4j_driver = AsyncGraphDatabase.driver(neo4j_uri)
    # Postgres
    pg_dsn = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@postgres:5432/{os.getenv('POSTGRES_DB')}"
    pg_pool = await asyncpg.create_pool(dsn=pg_dsn, min_size=1, max_size=10)
    # Init tables
    await pg_pool.execute('''
        CREATE TABLE IF NOT EXISTS invoices (
            invoice_id VARCHAR PRIMARY KEY,
            package_id VARCHAR,
            customer_id VARCHAR,
            amount DECIMAL,
            status VARCHAR DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    logger.info("DBs ready")
