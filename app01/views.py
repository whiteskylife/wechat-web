from django.shortcuts import render
from django.shortcuts import HttpResponse
import requests
import time
import re
import json
# Create your views here.


def ticket(html):
    """
    分析html，返回凭证信息以字典形式
    :param html:
    :return:
    """
    from bs4 import BeautifulSoup
    ret = {}
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.find(name='error').find_all():  # 找到所有的子标签
        ret[tag.name] = tag.text
    return ret


def login(req):
    """
        存储登录时间戳、uuid到session中
    """
    if req.method == 'GET':
        uuid_time = int(time.time() * 1000)
        base_uuid_url = 'https://login.wx.qq.com/jslogin?appid=wx782c26e4c19acffb&redirect_uri=https%3A%2F%2Fwx.' \
                        'qq.com%2Fcgi-bin%2Fmmwebwx-bin%2Fwebwxnewloginpage&fun=new&lang=zh_CN&_={0}'   # 请求这个url用于返回uuid
        uuid_url = base_uuid_url.format(uuid_time)
        r1 = requests.get(uuid_url)
        # print(r1, type(r1), r1.text) # window.QRLogin.code = 200; window.QRLogin.uuid = "YdIt_MoYUg==";
        result = re.findall('= "(.*)";', r1.text)
        uuid = result[0]
        print(uuid)
        req.session['UUID_TIME'] = uuid_time
        req.session['UUID'] = uuid
        return render(req, 'login.html', {'uuid': uuid})        # 拿到uuid用于生成二维码


def check_login(req):
    """
    确认登录后，
        获取cookie（LOGIN_COOKIE）、凭证信息（TICKET_DICT）、凭证cookie（TICKET_COOKIE、初始化信息最近联系人等（INIT_DICT）
    存储到session中，
    """
    response = {'code': 408, 'data': None}

    ctime = int(time.time()*1000)
    base_login_url = 'https://login.wx.qq.com/cgi-bin/mmwebwx-bin/login?loginicon=true&uuid={0}&tip=0&r=-1112403968&_={1}'
    login_url = base_login_url.format(req.session['UUID'], ctime)  # ctime需要实时的时间戳
    r1 = requests.get(login_url)
    print(r1.text)
    if 'window.code=408' in r1.text:
        response['code'] = 408  # 无人扫码
    elif 'window.code=201' in r1.text:
        # 有人扫码，返回头像
        response['code'] = 201
        user_avatar = re.findall("window.userAvatar = '(.*)';", r1.text)[0]  # 获取到头像
        response['data'] = user_avatar
    elif 'window.code=200' in r1.text:
        # 扫码，并确认登录
        req.session['LOGIN_COOKIE'] = r1.cookies.get_dict()     # 关键的请求可能会用到cookie，这里先放到session中
        base_redirect_url = re.findall('redirect_uri="(.*)";', r1.text)[0]
        """
window.code=200;
window.redirect_uri="https://wx2.qq.com/cgi-bin/mmwebwx-bin/webwxnewloginpage?ticket=A8JlKJZow9qK8aqVkk7mW5Jl@qrticket_0&uuid=IZ2rj97qwQ==&lang=zh_CN&scan=1525833600";
                     https://wx2.qq.com/cgi-bin/mmwebwx-bin/webwxnewloginpage?ticket=A3afZmsq0vwf1NME-AaEigP0@qrticket_0&uuid=wYiCzYjwzA==&lang=zh_CN&scan=1525834549&fun=new&version=v2&lang=zh_CN
        """
        redirect_url = base_redirect_url + '&fun=new&version=v2&lang=zh_CN'

        # 获取凭证
        r2 = requests.get(redirect_url)
        ticket_dict = ticket(r2.text)
        req.session['TICKET_DICT'] = ticket_dict
        req.session['TICKET_COOKIE'] = r2.cookies.get_dict()
        response['code'] = 200

        # 初始化，获取最近联系人、公众号
        post_data = {
            'BaseRequest': {
                'DeviceID': 'e298166576309624',
                'Sid': ticket_dict['wxsid'],
                'Uin': ticket_dict['wxuin'],
                'Skey': ticket_dict['skey'],
            }
        }

        # 用户初始化，将最近联系、人个人信息放在session中
        init_url = "https://wx2.qq.com/cgi-bin/mmwebwx-bin/webwxinit?r=-1121890234&lang=zh_CN&pass_ticket={0}"\
            .format(ticket_dict['pass_ticket'])
        r3 = requests.post(
            url=init_url,
            json=post_data,
        )
        r3.encoding = 'utf-8'
        init_dict = json.loads(r3.text)
        req.session['INIT_DICT'] = init_dict

    return HttpResponse(json.dumps(response))


def avatar(req):
    """
        获取头像时需要提供：cookie, 请求头中的数据类型Content-Type
    """
    prev = req.GET.get('prev')                      # /cgi-bin/mmwebwx-bin/webwxgeticon?seq=153216430
    user_img_url = req.GET.get('username')          # @d28ed5d7275ca618f58ace8b928c717a7d3dd19d322ac04e0a111d72d9c72096
    skey = req.GET.get('skey')                      # @crypt_12a67636_d73f43f9df17ce1aa4fa7c2830fdd16e

    img_url = 'https://wx2.qq.com{0}&username={1}&skey={2}'.format(prev, user_img_url, skey)
    # img_url_old = 'https://wx2.qq.com' + req.session['INIT_DICT']['ContactList'][0]['HeadImgUrl']
    #  这种方式只能取一个用户头像，很多用户时用上面的方法取
    # print(img_url)
    # print(img_url_old)
    # res = requests.get(img_url, headers={'Referer': 'https://wx2.qq.com'})z
    # print(res.text)

    cookies = {}
    cookies.update(req.session['LOGIN_COOKIE'])
    cookies.update(req.session['TICKET_COOKIE'])

    res = requests.get(img_url, cookies=cookies, headers={'Content-Type': 'image/jpeg'})
    # print(res.content)   # 这里如果用text无返回，因为是unicode类型；必须用content返回bytes类型

    return HttpResponse(res.content)


def index(req):
    """显示最近联系人"""
    # Referer:https://wx2.qq.com/

    return render(req, 'index.html')


def contact_list(req):
    """
        获取所有联系人,经测试需要cookie
        请求url关键字：webwxgetcontact
        url："https://wx2.qq.com/cgi-bin/mmwebwx-bin/webwxgetcontact?r=1525866028382&seq=0&skey=@crypt_12a67636_e1baed3e6988183bf107a54dda335524"
    """
    ctime = int(time.time()*1000)
    base_url = "https://wx2.qq.com/cgi-bin/mmwebwx-bin/webwxgetcontact?r={0}&seq=0&skey={1}"
    url = base_url.format(ctime, req.session['TICKET_DICT']['skey'])

    cookies = {}
    cookies.update(req.session['LOGIN_COOKIE'])
    cookies.update(req.session['TICKET_COOKIE'])

    r1 = requests.get(url, cookies=cookies)
    r1.encoding = 'utf-8'
    # json.loads(r1.text)     # 转换为字典类型 type(r1.text))   #  <class 'str'>; type(json.loads(r1.text)) <class 'dict'>
    user_list = json.loads(r1.text)
    print(user_list)   # 观察可知MemberList为用户列表
    return render(req, 'contact_list.html', {'user_list': user_list})


def send_msg(req):
    ctime = int(time.time()*1000)
    # s_msg = req.POST.get('msg')
    s_msg = req.POST.get('send_msg')
    url = 'https://wx2.qq.com/cgi-bin/mmwebwx-bin/webwxsendmsg?pass_ticket={0}'
    url.format(req.session['TICKET_DICT']['pass_ticket'])
    current_user = req.session['INIT_DICT']['User']['UserName']     # 每次登陆都不一样，要从登录的session中实时获取
    to = req.POST.get('to')
    # print('current_user:', current_user, 'to: ', to, 's_msg:', s_msg)
    post_data = {
        'BaseRequest': {
            'DeviceID': "e521133385150967",
            'Sid': req.session['TICKET_DICT']['wxsid'],
            'Uin': req.session['TICKET_DICT']['wxuin'],
            'Skey': req.session['TICKET_DICT']['skey'],
        },
        'Msg': {
            'ClientMsgId': ctime,
            'Content': s_msg,
            'FromUserName': current_user,
            'LocalID': ctime,
            'ToUserName': to,
            'Type': 1,
        },
        "Scene": 0
    }

    cookies = {}
    cookies.update(req.session['LOGIN_COOKIE'])
    cookies.update(req.session['TICKET_COOKIE'])
    cookies.update(req.session['TICKET_DICT'])
    # cookies.update(req.session['INIT_DICT'])
    r3 = requests.post(
        url=url,
        headers={'Content-Type': 'application/json;charset=UTF-8'},
        data=json.dumps(post_data, ensure_ascii=False).encode('utf-8'),
        cookies=cookies,
    )
    print(r3.text)
    # requests 内部会把json.dumps(post_data, ensure_ascii=False).转换为latin编码，如果里面有中文会报错，所以要先转成utf-8
    return HttpResponse('OK')


def get_msg(req):
    """长轮询获取消息"""
    # 检查是否有消息到来，有--获取新消息
    ctime = int(time.time()*1000)
    ticket_dict = req.session['TICKET_DICT']
    check_msg_url = 'https://webpush.wx2.qq.com/cgi-bin/mmwebwx-bin/synccheck'
    synckey_dict = req.session['INIT_DICT']['SyncKey']
    synckey_list = []
    for item in synckey_dict['List']:
        temp = "%s_%s" % (item['Key'], item['Val'])
        synckey_list.append(temp)
    synckey = '|'.join(synckey_list)

    cookies = {}
    cookies.update(req.session['LOGIN_COOKIE'])
    cookies.update(req.session['TICKET_COOKIE'])

    ret = requests.get(
        url=check_msg_url,
        params={
            'r': ctime,
            'deviceid': "e521133385150967",
            'sid': ticket_dict['wxsid'],
            'uin': ticket_dict['wxuin'],
            'skey': ticket_dict['skey'],
            '_': ctime,
            'synckey': synckey,
        },
        cookies=cookies,
    )
    print(ret.text)

    # 返回格式：  window.synccheck={retcode:"0",selector:"0"}
    if '{retcode:"0",selector:"0"}' in ret.text:  # 没收到消息
        return HttpResponse('没收到消息')
    # 有消息：获取消息
    base_get_msg_url = 'https://wx2.qq.com/cgi-bin/mmwebwx-bin/webwxsync?sid={0}&skey={1}'
    get_msg_url = base_get_msg_url.format(ticket_dict['wxsid'], ticket_dict['skey'])

    post_data = {
        'BaseRequest': {
            'DeviceID': "e521133385150967",
            'Sid': req.session['TICKET_DICT']['wxsid'],
            'Uin': req.session['TICKET_DICT']['wxuin'],
            'Skey': req.session['TICKET_DICT']['skey'],
        },
        'SyncKey': req.session['INIT_DICT']['SyncKey']
    }

    r2 = requests.post(
        url=get_msg_url,
        json=post_data,
        cookies=cookies,
    )

    r2.encoding = 'utf-8'
    msg_dict = json.loads(r2.text)
    print(msg_dict)
    for msg in msg_dict['AddMsgList']:
        print('有新的消息：', msg['Content'])

    # 收到消息后要更新SyncKey
    init_dict = req.session['INIT_DICT']
    # req.session['INIT_DICT']['SyncKey'] = msg_dict['SyncKey']  # 这种方法无法正确更新
    init_dict['SyncKey'] = msg_dict['SyncKey']
    req.session['INIT_DICT'] = init_dict

    return HttpResponse('ok')

'''
synckey:1_668516454|2_668516764|3_668516668|11_668516732|201_1525946160|203_1525944199|1000_1525944358|1001_1525944554|1002_1525840027|2001_1525944384
:1525938389932

'''