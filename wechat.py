# !/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Os: ubuntu 16.04
Data: 2018.2.1
Author: YYGN
Ide: pycharm
function: To crawl infomations from sogou-wechat.
"""

import pymongo
import requests
from config import *
from bs4 import BeautifulSoup
from requests.exceptions import ConnectionError
from urllib.parse import urlencode
import redis
import random
from multiprocessing import Pool

base_url = 'http://weixin.sogou.com/weixin?'
# 是需要cookie的！！！所以要先自己登陆获得cookie或者模拟登录。
headers = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Cache-Control': 'max-age=0',
    'Connection': 'keep-alive',
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.119 Safari/537.36',
    'cookie': 'SUV=1517189150150034; SMYUV=1517189150151339; UM_distinctid=1613f853679266-0610afeffb4f93-3a7f0e5a-100200-1613f85367a390; ABTEST=0|1517202681|v1; IPLOC=CN5000; SUID=0A596A0E4842910A000000005A6EACF9; SUID=0A596A0E5018910A000000005A6EACF9; pgv_pvi=79205376; SNUID=3D6F5C39363254D47F701FED37BA97F2; weixinIndexVisited=1; sct=5; JSESSIONID=aaapjXhvYyY7i_3--_Bew; ld=Ayllllllll2zb$1ylllllVIhzS1lllllRuIBjkllll9llllllylll5@@@@@@@@@@; clientId=0FE9278CD766695105D72CF0D6A66862; ppinf=5|1517449173|1518658773|dHJ1c3Q6MToxfGNsaWVudGlkOjQ6MjAxN3x1bmlxbmFtZTo0OllZR058Y3J0OjEwOjE1MTc0NDkxNzN8cmVmbmljazo0OllZR058dXNlcmlkOjQ0Om85dDJsdUx1anl5MjllMkFEbUE4YkFOOXE2Nm9Ad2VpeGluLnNvaHUuY29tfA; pprdig=srjCXwFuo6DPUW5sHScn-zSJQTjEZrfWp-uNrRq9ABR1R499y1Mcl83FwnCxSbIqt9Q-OEw36pSQm7PP6c10mb38Ynu2Aj6UjvziyRv65R1aOyAPrzKBVcWKUUOIA-0iWcG5qqaiN4fF8JOxQ93-VDwK4fNwyE1WJnocARxrbFc; sgid=10-33313597-AVpyb9UqCRicgymFSw6BAOKU; ppmdig=1517449173000000673ed29fcee1e72a901952ccdcac530e',
    'Host': 'weixin.sogou.com'
}

client = pymongo.MongoClient(HOST)
db = client[MONGO_DATABASE]

proxy_client = redis.Redis(host=HOST, port=PORT, password=PWD)
proxies = proxy_client.lrange('proxies', 0, -1)


def get_html(url, proxy=None):
    """
    发起初始请求
    :param url: 搜狗的搜索结果页面
    :param proxy: 代理IP，默认没有
    :return: 返回response
    """
    print('<----- Opening %s ----->.' % url)
    try:
        if proxy:
            response = requests.get(url, headers=headers, allow_redirects=False, proxies={'http': 'http://'+proxy})
        else:
            response = requests.get(url, headers=headers, allow_redirects=False)
        if response.status_code == 200:
            return response.text
        if response.status_code == 302:
            # 需要代理了
            print('<----- The status code is 302 ----->')
            proxy = get_proxy()
            if proxy:
                print('<----- Useing proxy %s----->' % proxy)
                return get_html(url, proxy)
            else:
                print('<----- Failed to get proxy ----->')
                # 重复回调，直到成功为止！！！
                return get_html(url)
    except ConnectionError as e:
        print('<----- Oops, error %s ----->' % e)
        proxy = get_proxy()
        if proxy:
            return get_html(url, proxy)
        else:
            # 同理！！！
            return get_html(url)

def parse_html(html):
    """
    解析得到的搜索页面中的文章地址
    :param html: 传入的response
    :return: 文章地址列表
    """
    soup = BeautifulSoup(html, 'lxml')
    urls = [url.get('href') for url in soup.select('div.txt-box h3 a')]
    return urls


def get_article(url):
    """
    对每篇文章发起请求
    :param url: 文章地址
    :return: response
    """
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return response.text
        else:
            return None
    except ConnectionError:
        return None

def parse_article(html):
    """
    解析每篇文章
    :param html: 传入的response
    :return: 将要存储到MONGODB的字典参数
    """
    soup = BeautifulSoup(html, 'lxml')
    title = soup.select('.rich_media_title')[0].get_text().replace(' ', '')
    content = soup.select('.rich_media_content')[0].get_text().replace(' ', '')
    data = soup.select('#post-date')[0].get_text().replace(' ', '')
    nickname = soup.select('#js_profile_qrcode > div > strong')[0].get_text().replace(' ', '')
    wechat = soup.select('#js_profile_qrcode > div > p:nth-of-type(1) > span')[0].get_text().replace(' ', '')
    return {
        'title': title,
        'content': content,
        'data': data,
        'nickname': nickname,
        'wechat': wechat
    }

def save_to_mongo(data):
    """
    将结果存储到MONGODB
    :param data: 字典参数
    :return: None
    """
    try:
        db['article'].update({'title': data['title']}, {'$set': data}, True)
        print('<----- Saved to mongodb ----->')
    except:
        print('<----- Failed to mongodb ----->')


def get_proxy():
    """
    获取代理IP
    :return: 得到的代理IP
    """
    proxy = bytes.decode(random.choice(proxies))
    return proxy

def spider(url):
    # 搜索列表只有100页，搜狗平台说有好几十万条都是假的！！！
    html = get_html(url)
    if html:
        urls = parse_html(html)
        for url in urls:
            html = get_article(url)
            if html:
                data = parse_article(html)
                save_to_mongo(data)
        print('<----- Saved url: %s ----->' % url)


def main():
    urls = []
    for page in range(1, 101):
        data = {
            'type': 2,
            'page': page,
            'query': KEYWORD
        }
        urls.append(base_url + urlencode(data))
    pool = Pool(4)
    pool.map(spider, urls)
    pool.close()
    pool.join()

if __name__ == '__main__':
    main()
