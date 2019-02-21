import logging

class Config(object):
    # 全局配置文件

    # log配置
    LOGGER_LEVEL = logging.INFO
    LOGGER_FORMAT = '%(asctime)s-%(levelname)s-%(filename)s-%(lineno)s: %(message)s'
    LOGGER_FILE = 'logs/'
    LOGGER_CHARSET = 'utf8'
    LOGGER_SUFFIX = '%Y-%m-%d.log'
    LOGGER_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

    #rasa统一配置
    RASA_CONFIG_ENDPOINTS_ACTION_PACKAGE_NAME = 'robot.actions.action'
    RASA_CONFIG_ENDPOINTS_FILE = 'robot/config/endpoints.yml'
    RASA_CONFIG_NLU_TRAIN_PACKAGE_NAME = 'robot/models/current/nlu'
    RASA_CONFIG_CORE_DIALOGUE_PACKAGE_NAME = 'robot/models/dialogue'
    RASA_CONFIG_RUN_CHANNEL_NAME = 'rest'

class ProdConfig(Config):
    """Production configuration."""
    ENV = 'prod'
    DEBUG = False


class DevConfig(Config):
    """Development configuration."""
    ENV = 'dev'
    DEBUG = True

class TestConfig(Config):
    """Test configuration."""
    ENV = 'test'
    TESTING = True
    DEBUG = True