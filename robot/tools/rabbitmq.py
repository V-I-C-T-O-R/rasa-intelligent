import pika
from robot.config import constants
from robot import logger
class MQ(object):
    def __init__(self, host, port, fix_str='/', user=None, passwd=None):
        self.credentials = pika.PlainCredentials(user, passwd)
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host, port, fix_str, self.credentials))

    def send_message(self, queue_name, body, is_durable, arguments=None):
        channel = self.connection.channel()
        channel.queue_declare(queue=queue_name, durable=is_durable, arguments=arguments)
        channel.basic_publish(exchange='', routing_key=queue_name, body=body)
        channel.close()

    '''
        提供超时限制接收消息的方法
        no_ack参数坑爹,true表示服务自动删除,false表示手动ack,并不是字面上的意思
    '''
    def receive_message(self, queue_name, timeout,is_durable=False, arguments=None):
        channel = self.connection.channel()
        channel.queue_declare(queue=queue_name, durable=is_durable, arguments=arguments)

        for method_frame, properties, body in channel.consume(queue_name, no_ack=False, inactivity_timeout=timeout):
            # 显示消息部分并确认消息
            if method_frame is None or body is None:
                logger.info('获取消息超时或失败,准备转人工')
                return False, None
            else:
                body = body.decode('utf-8', 'ignore')
                logger.info('消息内容为:' + body)
                channel.basic_ack(method_frame.delivery_tag)
                return True, body
            break

        channel.cancel()
        channel.close()

    '''
    通用接收消息的方法
    '''
    def receive_message_no_time(self, queue_name):
        channel = self.connection.channel()
        def callback(ch, method, properties, body):
            message_info = body.split(constants.MQ_MESSAGE_SPLIT_SIGN)
            ch.basic_ack(delivery_tag=method.delivery_tag)  # 发送ack消息
            ch.close()
            self.send_message(message_info[0], message_info[1], False)

        channel.basic_consume(callback, queue=queue_name, no_ack=True)
        channel.start_consuming()

    def close_connection(self):
        self.connection.close()


if __name__ == '__main__':
    mq = MQ(host=constants.QUEUE_ACCOUNT_HOSTNAMES[0], port=constants.QUEUE_ACCOUNT_PORT,
            user=constants.QUEUE_ACCOUNT_USERNAME,
            passwd=constants.QUEUE_ACCOUNT_PASSWORD)
    channel = mq.connection.channel()
    channel.queue_declare(queue=constants.QUEUE_COMMON_NAME, durable=True,arguments=constants.QUEUE_COMMON_ARGUMENTS)
    import time
    for method_frame, properties, body in channel.consume(constants.QUEUE_COMMON_NAME, no_ack=False):
        try:
            body = body.decode('utf-8', 'ignore')
        except Exception as e:
            logger.error('消息转换异常')
        # 显示消息部分并确认消息
        message_info = body.split(constants.MQ_MESSAGE_SPLIT_SIGN)

        if method_frame is None or body is None:
            logger.info('获取消息超时或失败,准备转人工')
        else:
            # app.logger.info('消息内容:' + message_info[1])
            channel.basic_ack(method_frame.delivery_tag)
            # time.sleep(10)
            mq.send_message(message_info[0], message_info[1], False)

    channel.cancel()
    channel.close()
    mq.close_connection()
