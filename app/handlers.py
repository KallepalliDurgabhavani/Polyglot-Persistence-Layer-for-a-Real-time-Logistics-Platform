import json
import logging
from .db_connections import mongo_db, neo4j_driver, pg_pool
logger = logging.getLogger(__name__)
async def handle_driver_location(event):
    driver_id = event['payload']['driver_id']
    lat = event['payload']['location']['lat']
    lon = event['payload']['location']['lon']
    zone_id = event['payload']['zone_id']
    async with neo4j_driver.session() as session:
        await session.run('''
            MERGE (d:Driver {driverId: $driver_id})
            SET d.latitude = $lat, d.longitude = $lon
            MERGE (z:Zone {zoneId: $zone_id})
            MERGE (d)-[:LOCATED_IN]->(z)
        ''', driver_id=driver_id, lat=lat, lon=lon, zone_id=zone_id)
    logger.info(f"Graph updated for driver {driver_id}")
async def handle_package_status(event):
    pkg_id = event['payload']['package_id']
    status_entry = {
        'status': event['payload']['status'],
        'timestamp': event['timestamp'],
        **{k: v for k, v in event['payload'].items() if k != 'status'}
    }
    mongo_db.packages.update_one(
        {'package_id': pkg_id},
        {'$push': {'status_history': status_entry}},
        upsert=True
    )
    logger.info(f"Document updated for package {pkg_id}")
async def handle_billing(event):
    pkg_id = event['payload']['package_id']
    # Check if DELIVERED
    pkg_doc = mongo_db.packages.find_one({'package_id': pkg_id})
    if not pkg_doc or pkg_doc.get('status_history', [])[-1].get('status') != 'DELIVERED':
        with open('/app/retry_queue.json', 'a') as f:
            f.write(json.dumps(event) + '\n')
        logger.info(f"Billing {event['payload']['invoice_id']} queued for {pkg_id}")
        return
    # Insert
    try:
        await pg_pool.execute('''
            INSERT INTO invoices (invoice_id, package_id, customer_id, amount)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (invoice_id) DO NOTHING
        ''', event['payload']['invoice_id'], pkg_id, event['payload']['customer_id'], event['payload']['amount'])
        logger.info(f"Billing inserted for {pkg_id}")
    except Exception as e:
        logger.error(f"Billing duplicate/error for {event['payload']['invoice_id']}: {e}")
