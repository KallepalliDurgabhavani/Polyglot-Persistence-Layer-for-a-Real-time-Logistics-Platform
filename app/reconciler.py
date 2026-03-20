import json
import logging
from .db_connections import mongo_db, pg_pool
from .handlers import handle_billing  # Reuse logic but direct insert
logger = logging.getLogger(__name__)
async def reconcile():
    retry_events = []
    try:
        with open('/app/retry_queue.json', 'r') as f:
            for line in f:
                event = json.loads(line.strip())
                pkg_id = event['payload']['package_id']
                pkg_doc = mongo_db.packages.find_one({'package_id': pkg_id})
                if pkg_doc and pkg_doc.get('status_history', [])[-1].get('status') == 'DELIVERED':
                    # Process
                    await pg_pool.execute('''
                        INSERT INTO invoices (invoice_id, package_id, customer_id, amount)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (invoice_id) DO NOTHING
                    ''', event['payload']['invoice_id'], pkg_id, event['payload']['customer_id'], event['payload']['amount'])
                    logger.info(f"Reconciled billing {event['payload']['invoice_id']}")
                else:
                    retry_events.append(event)
    except FileNotFoundError:
        pass
    # Rewrite queue
    with open('/app/retry_queue.json', 'w') as f:
        for event in retry_events:
            f.write(json.dumps(event) + '\n')
    logger.info(f"Reconciliation complete. {len(retry_events)} remaining in queue")
