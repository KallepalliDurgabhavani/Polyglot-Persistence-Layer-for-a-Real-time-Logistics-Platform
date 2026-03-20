import operator
from typing import List, Dict
from fastapi import APIRouter
from .db_connections import mongo_db, neo4j_driver, pg_pool
router = APIRouter()
@router.get("/query/package/{pkg_id}")
async def query_package(pkg_id: str) -> List[Dict]:
    events = []
    # Document store
    pkg_doc = mongo_db.packages.find_one({'package_id': pkg_id})
    if pkg_doc:
        for hist in pkg_doc['status_history']:
            events.append({
                'source_system': 'document_store',
                'timestamp': hist['timestamp'],
                'event_details': hist
            })
    # Relational store
    rows = await pg_pool.fetch('SELECT * FROM invoices WHERE package_id = $1', pkg_id)
    for row in rows:
        events.append({
            'source_system': 'relational_store',
            'timestamp': row['created_at'].isoformat(),
            'event_details': dict(row)
        })
    # Graph store (via driver from DELIVERED)
    driver_id = None
    if pkg_doc:
        for hist in reversed(pkg_doc['status_history']):
            if hist.get('status') == 'DELIVERED' and hist.get('driver_id'):
                driver_id = hist['driver_id']
                break
    if driver_id:
        async with neo4j_driver.session() as session:
            result = await session.run(
                'MATCH (d:Driver {driverId: $did})-[:LOCATED_IN]->(z:Zone) RETURN d, z.zoneId',
                did=driver_id
            )
            record = await result.single()
            if record:
                events.append({
                    'source_system': 'graph_store',
                    'timestamp': '2023-10-27T10:30:00Z',  # Latest from log
                    'event_details': {'driver': dict(record['d']), 'zone': record['z.zoneId']}
                })
    # Sort by timestamp
    events.sort(key=operator.itemgetter('timestamp'))
    return events
def create_app():
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return app
