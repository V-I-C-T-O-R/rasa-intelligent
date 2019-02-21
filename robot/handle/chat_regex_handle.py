import re

import requests
from flask import make_response
from flask_restful import Resource, request
from robot.config import constants
from robot import app
from robot.tools.express_100 import Express100
from robot.tools.xml import Xml

#正则机器人处理
class ChatRegexHandler(Resource):
    REGEX_ORDER_NUMBER_12 = r'\d{12}'
    REGEX_ORDER_NUMBER_15 = r'\d{15}'
    REGEX_ORDER_NUMBER_118 = r'(118|228)[0-9]{9}'
    order_url = 'http://183.63.121.18:8092/API/V1/CustomerServiceRobo/TrackOrder'

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
        contents = self.regex_handle(_info)

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

    # def regex_handle(self,text):
    #     pattern = re.compile(self.REGEX_ORDER_NUMBER_12)
    #     order_num_group = pattern.search(text)
    #
    #     if order_num_group is not None and ('查' in text or '还没' in text  or '吗' in text  or '么' in text ):
    #         return self.fetch_order(order_num_group.group(),1)
    #     else:
    #         return '转人工服务中，请等待...'

    def fetch_order(self, order_no, is_task):
        body = {'OrderNO': order_no,
                'OrderField': 'customer_no,region_code,pay_state,order_state',
                'IsTaskInfo': is_task}
        if is_task == 1:
            body['OrderLineField'] = 'line_no,worker_note,design_desc,logical_company,logical_no'
        headers = {'Content-Type': "application/x-www-form-urlencoded"}
        try:
            resp = requests.post(self.order_url, data=body, headers=headers).json()
            if resp.get('Code') != 0:
                # return str(resp.get('Msg'))
                return '系统中查询不到此订单号'
            data = resp.get('Data')
            if data is not None:
                result = self.handle_response(data)
                return result
            else:
                return ""
        except Exception as e:
            print(e)
            return '订单系统访问异常'

    def handle_response(self, data):
        no_paid = '亲,您的订单未付款,请及时付款'
        created_text = '亲,您的订单正在调色中,调色后会尽快下发生产'
        producting_text = '亲,您查询的订单目前正在生产中'
        producted_text = '亲,您查询的订单目前已生产完,准备发货'
        received_text = '''虎彩售后服务时效温馨提示:\n快递破损:请在签收后24小时内反馈至虎彩客服虎彩客服,\n质量问题:请在签收后7天内反馈至虎彩客服,超出7天未向虎彩反馈由客户自行承担,客服电话/QQ:4008052189'''
        pay_state = data.get('OrderField').get('pay_state')
        if str(pay_state) == 'Created':
            return no_paid
        order_state = data.get('OrderField').get('order_state')
        if str(pay_state) == 'Paid' and str(order_state) == 'Created':
            return created_text
        if str(pay_state) == 'Paid' and str(order_state) == 'Producting':
            return producting_text
        if str(pay_state) == 'Paid' and str(order_state) == 'Producted':
            return producted_text
        order_field = data.get('OrderLineField')
        if order_field is not None and len(data.get('OrderLineField')) > 0:
            for i in range(0, len(order_field)):
                logical_company = order_field[i].get('logical_company')
                logical_no = str(order_field[i].get('logical_no'))
                break
        if str(pay_state) == 'Paid' and str(order_state) == 'Delivered':
            result = '亲,您查询的订单目前已发货,' + logical_company + '快递,快递单号' + logical_no + ',请留意查收\n \n' + received_text
            return result
        if str(pay_state) == 'Paid' and str(order_state) == 'Received':
            status = Express100.get_express_status(logical_no.strip())
            result = '亲,您查询的订单我们这边显示已收货,请您确认一下,快递收货信息如下:\n' + status + '\n \n' + received_text
            return result

        return self.handle_all(data)

    def handle_all(self, data):
        result = ''
        customer_no = data.get('OrderField').get('customer_no')
        result += "客户编号:" + customer_no + '\n'
        region_code = data.get('OrderField').get('region_code')
        result += "地域编号:" + region_code + '\n'
        pay_state = data.get('OrderField').get('pay_state')
        result += "支付状态:" + pay_state + '\n'
        order_state = data.get('OrderField').get('order_state')
        result += "订单状态:" + order_state + '\n'
        order_field = data.get('OrderLineField')
        if order_field is not None and len(data.get('OrderLineField')) > 0:
            result += '商品明细：' + '\n'
            for i in range(0, len(order_field)):
                design_desc = order_field[i].get('design_desc')
                result += "* 商品描述:" + design_desc + '\n'
                logical_company = order_field[i].get('logical_company')
                result += "* 快递公司:" + logical_company + '\n'
        return result

    def regex_handle(self,text):

        status, content, intent = self.handle_query_url(text)
        if status:
            result = intent + '&&' + content
            return result
        status, content, intent = self.handle_query_order(text)
        if status:
            result = intent + '&&' + content
            return result
        status, content, intent = self.handle_query_greet(text)
        if status:
            result = intent + '&&' + content
            return result
        return constants.IMCC_MESSAGE_BY_HUMAN_FLAG

    def handle_query_order(self,text):
        pattern = re.compile(self.REGEX_ORDER_NUMBER_118)
        order_num_group = pattern.search(text)
        if order_num_group:
            mark = self.handle_query_switch(text)
            if mark:
                return True, '查订单', 'order'
                # 暂时测试屏蔽掉调用接口
                order_no = order_num_group.group()
                return True,self.fetch_order(order_no, 1),'order'
            return False,None,None
        return False,None,None

    def handle_query_switch(self,text):
        pattern = re.compile(r'发(货|快递)了{0,1}(吗|没|嘛)')
        result = pattern.search(text)
        if result:
            return True
        pattern = re.compile(r'寄出(了|去){0,1}(吗|没|嘛)')
        result = pattern.search(text)
        if result:
            return True
        pattern = re.compile(r'(还没|还没有|有没有|是否)(发货|收到|寄出)')
        result = pattern.search(text)
        if result:
            return True
        pattern = re.compile(r'(什么时候|多久)(能|可以){0,1}(好|到|回来|做好|发货)')
        result = pattern.search(text)
        if result:
            return True
        pattern = re.compile(r'(查|看|跟进)(下|个)')
        result = pattern.search(text)
        if result:
            return True
        pattern = re.compile(r'(在|开始)(生产|制作|生产制作)了{0,1}(吗|没|嘛)')
        result = pattern.search(text)
        if result:
            return True
        pattern = re.compile(r'(做好了吗|什么程度了|现在到哪一步了)')
        result = pattern.search(text)
        if result:
            return True
        return False

    def handle_query_url(self,text):
        if ('网址' in text or '页面' in text or '网站' in text or '官网' in text \
                or '链接' in text or '客户端' in text) and ('发'in text or '给' in text):
            return True,'亲，新的下单网址是：http://shop.hucais.com.cn/login.shtml。请添加到浏览器收藏夹','address'
        return False,None,None

    def handle_query_greet(self,text):
        pattern = re.compile(r'^(你好|您好|在吗|在不在)$')
        result = pattern.search(text.strip(' '))
        if result:
            return True, '您好，请问有什么可以帮您？', 'greet'
        return False,None,None
