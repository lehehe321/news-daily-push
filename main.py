#!/usr/bin/env python3
"""
通信与AI每日新闻采集与推送脚本
从今日头条搜索通信和AI相关新闻，通过PushPlus推送到微信
"""

import requests
import json
import os
import re
from datetime import datetime
from urllib.parse import quote

PUSHPLUS_TOKEN = os.environ.get('PUSHPLUS_TOKEN', '')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Referer': 'https://www.toutiao.com/',
}


def search_toutiao(keyword, count=9):
    """从今日头条搜索新闻"""
    news_list = []
    try:
        # 使用头条搜索API
        url = f'https://so.toutiao.com/search?keyword={quote(keyword)}&pd=information&source=input&dvpf=pc&aid=4926&page_num=0&count={count}&search_id='
        resp = requests.get(url, headers=HEADERS, timeout=15)
        data = resp.json()

        items = data.get('data', [])
        if not items and isinstance(data, dict):
            # 尝试不同的数据结构
            for key in ['data', 'list', 'result', 'items']:
                if key in data and isinstance(data[key], list):
                    items = data[key]
                    break

        for item in items:
            if not isinstance(item, dict):
                continue
            title = item.get('title', '') or item.get('topic', '') or ''
            if not title:
                continue
            # 过滤掉广告和无关内容
            abstract = item.get('abstract', '') or item.get('content', '') or ''
            source = item.get('source', '') or item.get('source_name', '') or '今日头条'
            publish_time = item.get('publish_time', '') or item.get('display_time', '') or item.get('time', '') or ''
            url_link = item.get('url', '') or item.get('share_url', '') or item.get('article_url', '') or ''

            # 清理摘要中的HTML标签
            abstract = re.sub(r'<[^>]+>', '', abstract)
            if len(abstract) > 200:
                abstract = abstract[:200] + '...'

            news_list.append({
                'title': title,
                'abstract': abstract,
                'source': source,
                'time': str(publish_time),
                'url': url_link,
            })

    except Exception as e:
        print(f"搜索 '{keyword}' 出错: {e}")

    return news_list[:count]


def search_baidu_news(keyword, count=9):
    """从百度新闻搜索（备用方案）"""
    news_list = []
    try:
        url = f'https://www.baidu.com/s?wd={quote(keyword)}&tn=news&rn={count}'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.encoding = 'utf-8'

        # 简单解析百度新闻结果
        from html.parser import HTMLParser
        titles = re.findall(r'<h3[^>]*class="c-title[^"]*"[^>]*>.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', resp.text, re.DOTALL)
        sources = re.findall(r'<span[^>]*class="c-color-gray[^"]*c-gap-right"[^>]*>(.*?)</span>', resp.text)

        for i, (link, title_html) in enumerate(titles[:count]):
            title = re.sub(r'<[^>]+>', '', title_html).strip()
            source_name = sources[i].strip() if i < len(sources) else '百度新闻'
            news_list.append({
                'title': title,
                'abstract': '',
                'source': source_name,
                'time': '',
                'url': link,
            })
    except Exception as e:
        print(f"百度新闻搜索 '{keyword}' 出错: {e}")

    return news_list[:count]


def format_news(news_list, category):
    """将新闻列表格式化为Markdown"""
    if not news_list:
        return f"### {category}\n\n暂无相关新闻\n\n"

    md = f"### {category}\n\n"
    for i, item in enumerate(news_list, 1):
        md += f"**{i}. {item['title']}**\n\n"
        if item['abstract']:
            md += f"> {item['abstract']}\n\n"
        meta_parts = []
        if item['source']:
            meta_parts.append(f"来源: {item['source']}")
        if item['time']:
            meta_parts.append(f"时间: {item['time']}")
        if meta_parts:
            md += f"{' | '.join(meta_parts)}\n\n"
        md += "---\n\n"
    return md


def push_to_wechat(title, content):
    """通过PushPlus推送到微信"""
    url = 'https://www.pushplus.plus/send'
    data = {
        'token': PUSHPLUS_TOKEN,
        'title': title,
        'content': content,
        'template': 'markdown',
    }
    try:
        resp = requests.post(url, json=data, timeout=15)
        result = resp.json()
        print(f"推送结果: {result}")
        return result.get('code') == 200
    except Exception as e:
        print(f"推送失败: {e}")
        return False


def main():
    today = datetime.now().strftime('%Y年%m月%d日')
    print(f"=== 开始采集 {today} 的通信与AI新闻 ===")

    # 搜索通信新闻
    print("正在搜索通信新闻...")
    comm_news = search_toutiao('通信')
    if not comm_news:
        print("头条搜索失败，尝试百度备用...")
        comm_news = search_baidu_news('通信行业最新消息')

    # 搜索AI新闻
    print("正在搜索AI新闻...")
    ai_news = search_toutiao('AI 人工智能')
    if not ai_news:
        print("头条搜索失败，尝试百度备用...")
        ai_news = search_baidu_news('AI 人工智能最新消息')

    # 格式化内容
    title = f"通信与AI每日新闻速览 | {today}"
    content = f"# {title}\n\n"
    content += format_news(comm_news, "通信新闻")
    content += format_news(ai_news, "AI 人工智能新闻")
    content += f"\n---\n\n*自动采集推送于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"

    print(f"采集完成: 通信新闻 {len(comm_news)} 条, AI新闻 {len(ai_news)} 条")

    # 推送
    if PUSHPLUS_TOKEN:
        result = push_to_wechat(title, content)
        if result:
            print("推送成功!")
        else:
            print("推送失败!")
    else:
        print("PUSHPLUS_TOKEN 未设置，仅输出内容:")
        print(content)


if __name__ == '__main__':
    main()
