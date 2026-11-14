import logging
from app.services.cleanup import cleanup_expired_data
from app.services.maintenance import run_maintenance

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cleanup_worker")

if __name__ == "__main__":
    logger.info("Executing scheduled cleanup of expired listings and needs...")
    cleanup_expired_data()
    logger.info("Expiring stale enquiries and sending chat reminders...")
    run_maintenance()
    logger.info("Cleanup process finished.")
