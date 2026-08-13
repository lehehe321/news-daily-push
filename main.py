#!/usr/bin/env python3
"""
通信与AI每日新闻采集与推送脚本
多源采集通信和AI相关新闻，通过PushPlus推送到微信
"""

import requests
import json
import os
import re
import hashlib
import time
import argparse
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

PUSHPLUS_TOKEN = os.environ.get('PUSHPLUS_TOKEN', '')

HEADERS_PC = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Referer': 'https://www.toutiao.com/',
}

HEADERS_MOBILE = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}

# 通信相关关键词
COMM_KEYWORDS = ['通信', '5G', '6G', '运营商', '基站', '光缆', '宽带', '电信', '移动', '联通', '射频', '天线', '网络', '光纤', '物联网', 'IoT', '卫星通信', '频谱']
# AI相关关键词
AI_KEYWORDS = ['AI', '人工智能', '大模型', '机器学习', '深度学习', 'GPT', 'ChatGPT', 'LLM', '芯片', 'GPU', '算力', '自动驾驶', 'OpenAI', 'Claude', 'DeepSeek', '智谱', '文心', '通义', 'AGI', '智能体']


def matches_keywords(title, keywords):
    """检查标题是否匹配关键词"""
    for kw in keywords:
        if kw.lower() in title.lower():
            return True
    return False


def search_toutiao_trending(keywords_list, count=9):
    """从今日头条热榜API获取热门新闻并按关键词过滤"""
    news_list = []
    try:
        url = 'https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc'
        resp = requests.get(url, headers=HEADERS_PC, timeout=15)
        data = resp.json()

        items = data.get('data', [])
        for item in items:
            title = item.get('Title', '') or item.get('title', '')
            if not title or not matches_keywords(title, keywords_list):
                continue
            abstract = item.get('Abstract', '') or item.get('abstract', '') or ''
            hot_value = item.get('HotValue', '') or item.get('hot_value', '') or ''
            url_link = item.get('Url', '') or item.get('url', '') or ''
            cluster_id = item.get('ClusterId', '') or item.get('cluster_id', '') or ''

            news_list.append({
                'title': title,
                'abstract': abstract,
                'source': '今日头条热榜',
                'time': hot_value,
                'url': url_link,
            })

        print(f"头条热榜匹配到 {len(news_list)} 条相关新闻")
    except Exception as e:
        print(f"头条热榜API出错: {e}")

    return news_list[:count]


def search_toutiao_api(keyword, count=9):
    """从今日头条搜索API获取新闻"""
    news_list = []
    try:
        url = f'https://so.toutiao.com/search?keyword={quote(keyword)}&pd=information&source=input&dvpf=pc&aid=4926&page_num=0&count={count}&search_id='
        resp = requests.get(url, headers=HEADERS_PC, timeout=15)

        if resp.status_code != 200:
            print(f"头条搜索返回状态码: {resp.status_code}")
            return []

        data = resp.json()
        items = data.get('data', [])
        if not items and isinstance(data, dict):
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
            abstract = item.get('abstract', '') or item.get('content', '') or ''
            source = item.get('source', '') or item.get('source_name', '') or '今日头条'
            publish_time = item.get('publish_time', '') or item.get('display_time', '') or ''
            url_link = item.get('url', '') or item.get('share_url', '') or ''

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
        print(f"头条搜索 '{keyword}' 获取 {len(news_list)} 条")
    except Exception as e:
        print(f"头条搜索 '{keyword}' 出错: {e}")

    return news_list[:count]


def search_baidu_news(keyword, count=9):
    """从百度新闻搜索获取新闻（移动端）"""
    news_list = []
    try:
        url = f'https://m.baidu.com/s?word={quote(keyword)}&tn=news&rn={count}'
        resp = requests.get(url, headers=HEADERS_MOBILE, timeout=15)
        resp.encoding = 'utf-8'
        html = resp.text

        # 解析移动端百度新闻结果
        # 移动端结果通常在特定的HTML结构中
        titles = re.findall(r'<a[^>]*class="[^"]*c-title[^"]*"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html, re.DOTALL)
        if not titles:
            titles = re.findall(r'<a[^>]*href="([^"]*)"[^>]*data-type="[^"]*"[^>]*>(.*?)</a>', html, re.DOTALL)

        sources = re.findall(r'class="[^"]*c-color-gray[^"]*"[^>]*>(.*?)</span>', html)
        if not sources:
            sources = re.findall(r'class="[^"]*source[^"]*"[^>]*>(.*?)</(?:span|div)>', html)

        for i, (link, title_html) in enumerate(titles[:count]):
            title = re.sub(r'<[^>]+>', '', title_html).strip()
            if not title or len(title) < 5:
                continue
            source_name = re.sub(r'<[^>]+>', '', sources[i]).strip() if i < len(sources) else '百度新闻'
            news_list.append({
                'title': title,
                'abstract': '',
                'source': source_name,
                'time': '',
                'url': link,
            })
        print(f"百度移动端搜索 '{keyword}' 获取 {len(news_list)} 条")
    except Exception as e:
        print(f"百度新闻搜索 '{keyword}' 出错: {e}")

    return news_list[:count]


def search_bing_news(keyword, count=9):
    """从Bing新闻搜索获取新闻（国际IP友好）"""
    news_list = []
    try:
        url = f'https://www.bing.com/news/search?q={quote(keyword)}&format=rss'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        resp = requests.get(url, headers=headers, timeout=15)

        # 解析RSS格式
        items = re.findall(r'<item>(.*?)</item>', resp.text, re.DOTALL)
        for item in items[:count]:
            title = re.search(r'<title><!\[CDATA\[(.*?)\]\]></title>', item, re.DOTALL)
            if not title:
                title = re.search(r'<title>(.*?)</title>', item, re.DOTALL)
            link = re.search(r'<link>(.*?)</link>', item)
            pub_date = re.search(r'<pubDate>(.*?)</pubDate>', item)
            source_match = re.search(r'<source[^>]*>(.*?)</source>', item)

            title_text = title.group(1).strip() if title else ''
            if not title_text:
                continue

            news_list.append({
                'title': title_text,
                'abstract': '',
                'source': source_match.group(1).strip() if source_match else 'Bing新闻',
                'time': pub_date.group(1).strip() if pub_date else '',
                'url': link.group(1).strip() if link else '',
            })
        print(f"Bing新闻搜索 '{keyword}' 获取 {len(news_list)} 条")
    except Exception as e:
        print(f"Bing新闻搜索 '{keyword}' 出错: {e}")

    return news_list[:count]


def search_rss_feed(feed_url, keywords_list, count=9, source_name='RSS'):
    """从RSS Feed获取新闻并按关键词过滤"""
    news_list = []
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; NewsBot/1.0)',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*',
        }
        resp = requests.get(feed_url, headers=headers, timeout=15)

        items = re.findall(r'<item>(.*?)</item>', resp.text, re.DOTALL)
        for item in items:
            title = re.search(r'<title><!\[CDATA\[(.*?)\]\]></title>', item, re.DOTALL)
            if not title:
                title = re.search(r'<title>(.*?)</title>', item, re.DOTALL)
            link = re.search(r'<link>(.*?)</link>', item)
            if not link:
                link = re.search(r'<link[^>]*href="([^"]*)"', item)
            desc = re.search(r'<description><!\[CDATA\[(.*?)\]\]></description>', item, re.DOTALL)
            if not desc:
                desc = re.search(r'<description>(.*?)</description>', item, re.DOTALL)
            pub_date = re.search(r'<pubDate>(.*?)</pubDate>', item)

            title_text = title.group(1).strip() if title else ''
            if not title_text or not matches_keywords(title_text, keywords_list):
                continue

            abstract = desc.group(1).strip() if desc else ''
            abstract = re.sub(r'<[^>]+>', '', abstract)
            if len(abstract) > 200:
                abstract = abstract[:200] + '...'

            news_list.append({
                'title': title_text,
                'abstract': abstract,
                'source': source_name,
                'time': pub_date.group(1).strip() if pub_date else '',
                'url': link.group(1).strip() if link else '',
            })

        print(f"RSS {source_name} 匹配到 {len(news_list)} 条相关新闻")
    except Exception as e:
        print(f"RSS {source_name} 出错: {e}")

    return news_list[:count]


def multi_source_search(keyword, keywords_list, count=9):
    """多源搜索：依次尝试多个数据源"""
    all_news = []
    seen_titles = set()

    def add_news(news_list):
        for item in news_list:
            # 用标题去重
            title_key = item['title'][:20]
            if title_key not in seen_titles:
                seen_titles.add(title_key)
                all_news.append(item)

    # 方案1: 头条搜索API
    print(f"[1] 尝试头条搜索API...")
    result = search_toutiao_api(keyword, count)
    if result:
        add_news(result)
        return all_news[:count]

    # 方案2: 头条热榜过滤
    print(f"[2] 尝试头条热榜API...")
    result = search_toutiao_trending(keywords_list, count)
    if result:
        add_news(result)

    # 方案3: Bing新闻
    if len(all_news) < count:
        print(f"[3] 尝试Bing新闻搜索...")
        result = search_bing_news(keyword, count - len(all_news))
        add_news(result)

    # 方案4: 百度移动端
    if len(all_news) < count:
        print(f"[4] 尝试百度移动端搜索...")
        result = search_baidu_news(keyword, count - len(all_news))
        add_news(result)

    # 方案5: RSS Feed
    if len(all_news) < count:
        print(f"[5] 尝试RSS源...")
        rss_sources = [
            ('http://36kr.com/feed', '36氪'),
            ('https://www.cnbeta.com.tw/backend.php', 'cnBeta'),
            ('https://feeds.feedburner.com/ruanyifeng', '阮一峰'),
        ]
        for feed_url, feed_name in rss_sources:
            if len(all_news) >= count:
                break
            result = search_rss_feed(feed_url, keywords_list, count - len(all_news), feed_name)
            add_news(result)

    return all_news[:count]


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


def main(marker=None):
    bj_tz = timezone(timedelta(hours=8))
    today = datetime.now(bj_tz).strftime('%Y年%m月%d日')
    today_marker = datetime.now(bj_tz).strftime('%Y-%m-%d')

    # 去重检查：当天已推送过则跳过（支持多点触发只推一次）
    if marker:
        if os.path.exists(marker):
            with open(marker, 'r', encoding='utf-8') as fh:
                last_pushed = fh.read().strip()
            if last_pushed == today_marker:
                print(f"【{today_marker}】今天已推送过，跳过本次任务")
                return

    print(f"=== 开始采集 {today} 的通信与AI新闻 ===")

    # 搜索通信新闻（多源）
    print("\n--- 搜索通信新闻 ---")
    comm_news = multi_source_search('通信', COMM_KEYWORDS, count=9)

    # 搜索AI新闻（多源）
    print("\n--- 搜索AI新闻 ---")
    ai_news = multi_source_search('AI 人工智能', AI_KEYWORDS, count=9)

    # 格式化内容
    title = f"通信与AI每日新闻速览 | {today}"
    content = f"# {title}\n\n"
    content += format_news(comm_news, "通信新闻")
    content += format_news(ai_news, "AI 人工智能新闻")
    content += f"\n---\n\n*自动采集推送于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"

    print(f"\n采集完成: 通信新闻 {len(comm_news)} 条, AI新闻 {len(ai_news)} 条")

    # 推送
    if PUSHPLUS_TOKEN:
        result = push_to_wechat(title, content)
        if result:
            print("推送成功!")
            # 写入去重标记
            if marker:
                with open(marker, 'w', encoding='utf-8') as fh:
                    fh.write(today_marker)
                print(f"已写入推送标记: {today_marker}")
        else:
            print("推送失败!")
    else:
        print("PUSHPLUS_TOKEN 未设置，仅输出内容:")
        print(content)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--wait-until', type=int, help='Wait until this Beijing hour (0-23) before pushing')
    parser.add_argument('--marker', type=str, help='Marker file path for daily dedup')
    args = parser.parse_args()

    if args.wait_until is not None:
        # 计算北京时间当前小时
        utc_now = datetime.now(timezone.utc)
        bj_tz = timezone(timedelta(hours=8))
        bj_now = utc_now.astimezone(bj_tz)
        current_hour = bj_now.hour

        if current_hour < args.wait_until:
            wait_seconds = (args.wait_until - current_hour) * 3600 - bj_now.minute * 60 - bj_now.second
            print(f"当前北京时间 {bj_now.strftime('%H:%M:%S')}，等待到 {args.wait_until}:00 再推送（约{wait_seconds//60}分钟）")
            time.sleep(wait_seconds)
            print(f"已到 {args.wait_until}:00，开始执行！")

    main(marker=args.marker)
