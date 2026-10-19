import logging
from app.services.cleanup import cleanup_expired_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cleanup_worker")

if __name__ == "__main__":
    logger.info("Executing scheduled cleanup of expired listings and needs...")
    cleanup_expired_data()
    logger.info("Cleanup process finished.")
