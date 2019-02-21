from robot.config import constants
from robot.tools.rabbitmq import MQ
import json
if __name__ == '__main__':
    mq = MQ(host=constants.QUEUE_ACCOUNT_HOSTNAMES[0], port=constants.QUEUE_ACCOUNT_PORT,
            user=constants.QUEUE_ACCOUNT_USERNAME,
            passwd=constants.QUEUE_ACCOUNT_PASSWORD)
    flag = False
    for host in constants.QUEUE_ACCOUNT_HOSTNAMES:
        try:
            mq = MQ(host=host, port=constants.QUEUE_ACCOUNT_PORT, user=constants.QUEUE_ACCOUNT_USERNAME,
                             passwd=constants.QUEUE_ACCOUNT_PASSWORD)
            flag = True
            break
        except Exception as e:
            continue
    if not flag:
        contents = constants.IMCC_MESSAGE_BY_HUMAN_FLAG
    else:
        try:
            nlu_str = \
                {
                    'text':'你好,请发我一份网址',
                    'output':'',
                    'sender_id':'victor',
                    'input_channel':'',
                    'message_id':'',
                    'parse_data':{
                    "entities": [
                        {
                            "end": 10,
                            "entity": "links",
                            "extractor": "ner_mitie",
                            "start": 8,
                            "value": "网址"
                        }
                    ],
                    "intent": {
                        "confidence": 0.9397186422631861,
                        "name": "ask_links"
                    },
                    "intent_ranking": [
                        {
                            "confidence": 0.9397186422631861,
                            "name": "ask_links"
                        },
                        {
                            "confidence": 0.16206323981749196,
                            "name": "restaurant_search"
                        },
                        {
                            "confidence": 0.1212448457737397,
                            "name": "affirm"
                        },
                        {
                            "confidence": 0.10333600028547868,
                            "name": "goodbye"
                        }
                    ],
                    "text": "你好,请发我一份网址"
                    }
                }

            message = json.dumps(nlu_str)
            mq.send_message(constants.QUEUE_COMMON_NAME, message, True, constants.QUEUE_COMMON_ARGUMENTS)
            print("发送成功")
            mq.close_connection()

        except Exception as e:
            contents = constants.IMCC_MESSAGE_BY_HUMAN_FLAG