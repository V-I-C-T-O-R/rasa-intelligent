from robot import logger
from robot.api import mq_agent

if __name__ == '__main__':
    logger.info('rasa core service is starting...')
    service = mq_agent.start_agent()
    logger.info('rasa core service is running...')
    service.join()
    logger.info('rasa core service had shutdown')
