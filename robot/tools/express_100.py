import requests


class Express100(object):
    company_url = "http://www.kuaidi100.com/autonumber/autoComNum"
    trace_url = "http://www.kuaidi100.com/query"

    @classmethod
    def get_json_data(cls, url, payload):
        r = requests.get(url=url, params=payload)
        return r.json()

    @classmethod
    def get_company_info(cls, express_code):

        payload = {'text': express_code}
        data = cls.get_json_data(cls.company_url, payload)
        return data

    @classmethod
    def get_express_info(cls, express_code):
        company_info = cls.get_company_info(express_code)
        company_code = ""
        if company_info.get("auto", ""):
            company_code = company_info.get("auto", "")[0].get("comCode", "")

        if company_code == "":
            return None, False
        payload = {'type': company_code, 'postid': express_code, 'id': 1}

        data = cls.get_json_data(cls.trace_url, payload)

        data.update(company_info)

        return data, True

    @classmethod
    def get_express_status(cls, express_code):
        res, status = cls.get_express_info(express_code)
        if not status:
            return '快递单号异常：快递单号不属于任何快递公司'
        if res['message'] != 'ok':
            return '快递公司参数异常：单号不存在或者已经过期'
        datas = res['data']
        flag = False
        content = ''
        for data in datas:
            if not flag:
                flag = True
            else:
                content += '\n'
            in_time = data.get('time', '')
            context = data.get('context', '')
            content += in_time + ' : ' + context
        return content

if __name__ == "__main__":
    code = 13383641764005
    res = Express100.get_express_status(str(code).strip())
    print(res)
