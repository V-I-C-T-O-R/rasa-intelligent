import json
import re

import requests
from flask import make_response
from flask_restful import Resource, request

from robot import app
from robot.tools.xml import Xml


class ChatHandler(Resource):

    # @jwt_required()
    def post(self):
        data = request.get_data()
        if data is None:
            app.logger.error('post data is none')
            return None, 200
        if len(data) == 0:
            app.logger.error('post data is blank')
            return None, 404
        try:
            data = re.sub('gbk', 'utf-8', data.decode('utf-8')).encode('utf-8')
            params = Xml.resove_xml(data)
        except BaseException as e:
            app.logger.error('请求内容编码格式错误,%s' % str(e))
            return '请求内容编码格式错误', '500'

        _info = params.get('inputchoosecontent')
        user_id = str(params.get('imUserNumber'))
        # print(params.get('imUserNumber'), ': ', _info)

        app.logger.info('%s: %s', params.get('imUserNumber'), _info)
        data = {
            'query': _info
        }
        api_url = 'http://localhost:5001/conversations/' + user_id + '/respond'
        response = requests.post(api_url, data=json.dumps(data), headers={'content-type': "application/json"}).text

        strs = json.loads(response, encoding='utf8')
        contents = ''
        for s in strs:
            content = s.get('text')
            contents = contents + str(content) + '\n'

        app.logger.info('机器人: \n%s', contents)
        results = {}
        results['key'] = 'inputchooseresult'
        results['value'] = contents
        results['code'] = 0
        results['reason'] = '响应成功'
        try:
            data = Xml.generate_xml(results)
            result = data
        except BaseException as e:
            app.logger.error('编码转换异常,%s' % str(e))
            return "编码转换异常", 500
        resp = make_response(result)
        resp.headers["Content-type"] = "application/xml;charset=gbk"
        return resp

