import logging


def setup_logging(log_file="handbrake_batch.log", level=logging.INFO):
    logging.basicConfig(
        filename=log_file,
        level=level,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
