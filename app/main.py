import asyncio
import json
import logging
from pathlib import Path
import uvicorn
from fastapi import FastAPI, HTTPException
from .db_connections import init_db, mongo_db, neo4j_driver, pg_pool
from .event_router import process_events
from .reconciler import reconcile
from .api import create_app
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = create_app()
@app.on_event("startup")
async def startup():
    await init_db()
    logger.info("DBs initialized")
    await process_events()
    await reconcile()
    logger.info("Event processing and reconciliation complete")
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
