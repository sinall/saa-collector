# -*- coding: UTF-8 -*-
import http.client
import json
import urllib.request


class CninfoApiException(Exception):
    pass


class CninfoApiClient:
    BATCH_SIZE = 50

    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret

    def login(self):
        self.token = self.gettoken()

    def gettoken(self):
        url = 'http://webapi.cninfo.com.cn/api-cloud-platform/oauth2/token'  # api.before.com需要根据具体访问域名修改
        post_data = "grant_type=client_credentials&client_id=%s&client_secret=%s" % (self.client_id, self.client_secret)
        req = urllib.request.urlopen(url, post_data.encode("utf-8"))
        responsecontent = req.read()
        responsedict = json.loads(responsecontent)
        token = responsedict["access_token"]
        return token

    def get_plate_stock_list(self, platetype):
        url = "http://webapi.cninfo.com.cn/api/stock/p_public0004?platetype=%s&access_token=%s"
        conn = http.client.HTTPConnection("webapi.cninfo.com.cn")
        conn.request(method="GET", url=url % (platetype, self.token))
        response = conn.getresponse()
        rescontent = response.read()
        responsedict = json.loads(rescontent)
        if responsedict["resultmsg"] != "success":
            raise CninfoApiException(responsedict["resultmsg"])
        return responsedict

    def get_company_basic_info(self, scode):
        return self.get_stock_info('p_stock2100', scode)

    def get_stock_basic_info(self, scode):
        return self.get_stock_info('p_stock2101', scode)

    def get_balance_sheet_info(self, scode):
        return self.get_stock_info('p_stock2300', scode)

    def get_stock_info(self, sub_resource, scode, **kwargs):
        return self.apiget('stock/{}'.format(sub_resource), scode, **kwargs)

    def apiget(self, resource, scode, **kwargs):
        url = "http://webapi.cninfo.com.cn/api/%s?scode=%s&access_token=%s"
        url = url % (resource, self.stringfy_scode(scode), self.token)
        for key, value in kwargs.items():
            url += "&%s=%s" % (key, value)
        conn = http.client.HTTPConnection("webapi.cninfo.com.cn")
        conn.request(method="GET", url=url)
        response = conn.getresponse()
        rescontent = response.read()
        responsedict = json.loads(rescontent)
        if responsedict["resultmsg"] != "success":
            raise CninfoApiException(responsedict["resultmsg"])
        return responsedict

    def apipost(self, scode):
        url = "http://webapi.cninfo.com.cn/api/stock/p_stock2100"
        post_data = "scode=%s&access_token=%s" % (self.stringfy_scode(scode), self.token)
        req = urllib.request.urlopen(url, post_data.encode("utf-8"))
        content = req.read()
        responsedict = json.loads(content)
        if responsedict["resultmsg"] != "success":
            raise CninfoApiException(responsedict["resultmsg"])
        return responsedict

    def stringfy_scode(self, scode):
        return ','.join(scode) if isinstance(scode, list) else scode


if __name__ == "__main__":
    client_id, client_secret = "89cbe88148e6457392cad1d21f5cd96c", "976abd74d6a548dc86b12bd99df6df39"
    client = CninfoApiClient(client_id, client_secret)
    client.login()
    responsedict = client.apiget('000001')
    resultcode = responsedict["resultcode"]
    print(responsedict["resultmsg"], responsedict["resultcode"])
    if (responsedict["resultmsg"] == "success" and len(responsedict["records"]) >= 1):
        print(responsedict["records"])
    else:
        print('no data')
