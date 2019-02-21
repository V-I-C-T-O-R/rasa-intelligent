import logging
import os
from logging.handlers import TimedRotatingFileHandler

from robot.config import setting
__author__='victor'

def init_logger():

    # 日志系统配置
    config = setting.ProdConfig
    logging.basicConfig(level=config.LOGGER_LEVEL, format=config.LOGGER_FORMAT, datefmt=config.LOGGER_DATE_FORMAT)
    logger = logging.getLogger(__name__)
    logger.setLevel(config.LOGGER_LEVEL)
    handler = TimedRotatingFileHandler(filename=config.LOGGER_FILE+'info.log', when="D", interval=1, backupCount=7,encoding=config.LOGGER_CHARSET)

    formatter = logging.Formatter(config.LOGGER_FORMAT)
    handler.setFormatter(formatter)
    handler.setLevel(config.LOGGER_LEVEL)
    logger.handlers.clear()
    logger.addHandler(handler)
    return logger

logger = init_logger()