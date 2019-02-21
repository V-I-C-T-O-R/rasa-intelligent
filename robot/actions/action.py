import os

import requests
from rasa_core.actions.action import Action
from rasa_core_sdk.forms import EntityFormField, FormAction

from robot.tools.express_100 import Express100
from robot.tools.sql_handle import Sqlite

db_address = os.path.dirname(os.path.dirname(os.path.realpath(__file__))) + '/'


class ActionQueryOrder(FormAction):
    RANDOMIZE = True

    def __init__(self, url='http://183.63.121.18:8092/API/V1/CustomerServiceRobo/TrackOrder'):
        self.order_url = url

    @staticmethod
    def required_fields():
        return [
            EntityFormField("order_number", "order_number")
        ]

    def name(self):
        return "action_query_order"

    def submit(self, dispatcher, tracker, domain):
        # events = tracker.events_after_latest_restart()
        # for i in range (0,len(events)):
        #     if events[len(events)-1-i].get('event') == 'user':
        #         content = events[len(events)-1-i].get('text')
        #         break
        order_number = tracker.get_slot('order_number')
        if order_number is None:
            order_number = ''
        action = tracker.get_slot('action')
        if action is None:
            action = ''
        result = 'order_number=' + order_number+',action=' + action
        return dispatcher.utter_message('action_query_order' + '&&' + result)


        order_number = tracker.get_slot('order_number')
        if order_number is None:
            return dispatcher.utter_message('')
        else:
            result = self.fetch_order(order_number, 1)
        return dispatcher.utter_message(result)

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


class ActionQuerySize(FormAction):
    RANDOMIZE = True

    def name(self):
        return "action_search_size"

    def submit(self, dispatcher, tracker, domain):
        product = tracker.get_slot('product')
        size = tracker.get_slot('size')
        if product is None:
            product = ''
        if size is None:
            size = ''
        result = 'product=' + product + ',size=' + size
        return dispatcher.utter_message('action_search_size' + '&&' + result)



        product = tracker.get_slot('product')
        size = tracker.get_slot('size')

        sqlite = Sqlite(db_address + 'rasa')
        if size is None or str(size).strip(' ') == '':
            resp = self.fetch_product(product, sqlite)
            if len(resp) == 0:
                return dispatcher.utter_message('亲,没有产品叫' + product + '的哦')
            else:
                return dispatcher.utter_message(self.handle_resp(resp))
        else:
            resp = self.fetch_product_size(product, size, sqlite)
            if len(resp) == 0:
                return dispatcher.utter_message('亲,' + product + '产品没有' + size + '的哦')
            else:
                return dispatcher.utter_message(self.handle_resp(resp))

    def fetch_product(self, product, sqlite):
        results = sqlite.query_data(
            'select distinct prod_des,page_width,page_height,category from demo where instr(description, "' + product + '") > 0 or instr(catalog_desc, "' + product + '") > 0')
        return results

    def fetch_product_size(self, product, size, sqlite):
        results = sqlite.query_data(
            'select distinct prod_des,page_width,page_height,category from demo where (instr(description, "' + product + '") > 0 or instr(catalog_desc, "' + product + '") > 0 ) and instr(size, "' + size + '") > 0 ')
        return results

    def handle_resp(self, results):
        resp = {}
        for result in results:
            if resp.get(result[3]) is None:
                resp[result[3]] = [[result[0], result[1], result[2]]]
            else:
                resp[result[3]].append([result[0], result[1], result[2]])
        contents = ''
        mark = False
        for k, v in resp.items():
            page = ''
            flag = False
            for c in v:
                if not flag:
                    flag = True
                else:
                    page += '; '
                page = page + c[0] + ':' + c[1] + '*' + c[2] + 'mm'
            if not mark:
                mark = True
            else:
                contents += '\n'
            contents += k + ': ' + page
        return contents


class ActionQueryLink(FormAction):
    RANDOMIZE = True

    def name(self):
        return "action_search_links"

    def submit(self, dispatcher, tracker, domain):
        links = tracker.get_slot('links')
        action = tracker.get_slot('action')
        if links is None:
            links = ''
        if action is None:
            action = ''
        result = 'links=' + links + ',action=' + action
        return dispatcher.utter_message('action_search_links' + '&&' +result)

        # return dispatcher.utter_message(
        #     '亲，新的下单网址是：http://shop.hucais.com.cn/login.shtml。请添加到浏览器收藏夹')

class CustomAction(FormAction):
    def name(self):
        return 'action_default_custom'

    def submit(self, dispatcher, tracker, domain):
        return dispatcher.utter_message('sorry')

if __name__ == '__main__':
    url = 'http://183.63.121.18:8092/API/V1/CustomerServiceRobo/TrackOrder'
    bot = ActionQueryOrder()
    print(bot.fetch_order(118101602792, 1))
