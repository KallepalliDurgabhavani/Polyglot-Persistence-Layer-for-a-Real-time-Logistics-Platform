import json
import logging
from .handlers import handle_driver_location, handle_package_status, handle_billing
logger = logging.getLogger(__name__)
handlers = {
    'DRIVER_LOCATION_UPDATE': handle_driver_location,
    'PACKAGE_STATUS_CHANGE': handle_package_status,
    'BILLING_EVENT': handle_billing
}
async def process_events():
    with open('/app/events.log', 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                handler = handlers.get(event.get('type'))
                if handler:
                    await handler(event)
                else:
                    logger.warning(f"Unknown type {event.get('type')} at line {line_num}")
            except json.JSONDecodeError:
                logger.error(f"Malformed JSON at line {line_num}")
