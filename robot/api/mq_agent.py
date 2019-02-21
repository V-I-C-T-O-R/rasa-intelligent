from rasa_core.channels import UserMessage, CollectingOutputChannel

from robot import logger
from robot.config import constants
from robot.handle.custom_rasa_core import RasaCore
from robot.tools.rabbitmq import MQ
import json

def start_mq_receiver():
    mq = MQ(host=constants.QUEUE_ACCOUNT_HOSTNAMES[0], port=constants.QUEUE_ACCOUNT_PORT,
            user=constants.QUEUE_ACCOUNT_USERNAME,
            passwd=constants.QUEUE_ACCOUNT_PASSWORD)
    channel = mq.connection.channel()
    channel.queue_declare(queue=constants.QUEUE_COMMON_NAME, durable=True, arguments=constants.QUEUE_COMMON_ARGUMENTS)
    rasa = RasaCore()
    for method_frame, properties, body in channel.consume(constants.QUEUE_COMMON_NAME, no_ack=False):
        try:
            body = body.decode('utf-8', 'ignore')
        except Exception as e:
            logger.error('消息转换异常')
            mq.send_message(message_info[0], constants.IMCC_MESSAGE_BY_HUMAN_FLAG, False)
            continue

        message_info = body.split(constants.MQ_MESSAGE_SPLIT_SIGN)
        logger.info('消息内容:' + message_info[1])
        message = UserMessage(message_info[1],
                              CollectingOutputChannel(),
                              message_info[0])
        parse_data = json.loads(message_info[2])
        strs = rasa.receive_nlu_message(message,parse_data)
        contents = ''
        for s in strs:
            content = s.get('text')
            contents = contents + str(content) + '\n'
        # 显示消息部分并确认消息
        print('机器人回复:'+contents)
        channel.basic_ack(method_frame.delivery_tag)
        continue
        mq.send_message(message_info[0], contents, False)

    channel.cancel()
    channel.close()
    mq.close_connection()

def start_agent():
    import threading
    consumer = threading.Thread(target=start_mq_receiver)
    consumer.start()
    return consumer
