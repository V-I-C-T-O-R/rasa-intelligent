import json
from robot import logger
import requests

class HttpFlumeSink:
    def __init__(self, host, port):
        self.host = host
        self.port = port

    def send_to_flume(self,from_who, body):
        url = 'http://' + self.host + ':' + str(self.port)
        data = [{'body': body}]
        headers = {"Content-Type": "application/json"}
        try:
            resp = requests.post(url, data=json.dumps(data), headers=headers, timeout=0.5)
            if resp is None or resp.status_code != requests.codes.ok:
                logger.info('%s[发送flume失败]:%s' % (from_who,body))
            else:
                logger.info('%s[发送flume成功]:%s' % (from_who,body))
        except Exception as e:
            logger.info('%s[发送flume失败]:%s' % (from_who,body))


if __name__ == '__main__':
    flume = HttpFlumeSink('192.172.1.250', 44443)
    flume.send_to_flume('你好，我来自你')
