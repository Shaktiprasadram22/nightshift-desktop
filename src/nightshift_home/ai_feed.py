"""Small public AI reading feed. No account, model calls, or private inputs."""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from data import HOME
from personal_store import private_write

CACHE=HOME/'.cache/nightshift-home/ai-feed.json'
REFRESH_SECONDS=900
RSS='https://huggingface.co/blog/feed.xml'
MAX_BYTES=2*1024*1024
LEARN=[
    {'title':'Understand language models','description':'LLM Course · transformers, datasets, tokenizers and fine-tuning','url':'https://huggingface.co/learn/llm-course/chapter1/1','source':'Hugging Face'},
    {'title':'Build your first AI agent','description':'Agents Course · tools, frameworks and hands-on projects','url':'https://huggingface.co/learn/agents-course/en/unit0/introduction','source':'Hugging Face'},
    {'title':'Try a practical AI recipe','description':'Open-Source AI Cookbook · runnable notebooks and examples','url':'https://huggingface.co/learn/cookbook/index','source':'Hugging Face'},
]

def clean(value,limit=250):
    return re.sub(r'\s+',' ',unescape(re.sub(r'<[^>]*>','',str(value or '')))).strip()[:limit]

def safe_url(value,host):
    if not isinstance(value,str):return False
    try:
        parsed=urllib.parse.urlsplit(value)
        return parsed.scheme=='https' and parsed.hostname==host and parsed.port in (None,443) and not parsed.username and not parsed.password
    except ValueError:return False

def parse_latest(payload):
    if b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper():raise ValueError('Unexpected feed format')
    root=ET.fromstring(payload);items=[]
    for node in root.findall('./channel/item'):
        title=clean(node.findtext('title'));url=node.findtext('link','').strip()
        if not title or not safe_url(url,'huggingface.co'):continue
        try:published=parsedate_to_datetime(node.findtext('pubDate')).timestamp()
        except (TypeError,ValueError,OverflowError):published=None
        items.append({'title':title,'url':url,'source':'Hugging Face','published':published})
        if len(items)==8:break
    return items

def parse_tools(payload):
    value=json.loads(payload)
    if not isinstance(value,dict) or not isinstance(value.get('items'),list):raise ValueError('Unexpected repository response')
    items=[]
    for repo in value['items']:
        if not isinstance(repo,dict):continue
        title=clean(repo.get('full_name'),100);url=repo.get('html_url')
        stars=repo.get('stargazers_count')
        if not title or not safe_url(url,'github.com') or type(stars) is not int or stars<0:continue
        items.append({'title':title,'url':url,'source':'GitHub','description':clean(repo.get('description'),180),'stars':stars})
        if len(items)==8:break
    return items

def read_url(url):
    request=urllib.request.Request(url,headers={'User-Agent':'Nightshift-Desktop/1.0','Accept':'application/json, application/rss+xml, application/xml'})
    with urllib.request.urlopen(request,timeout=12) as response:
        result=response.read(MAX_BYTES+1)
    if len(result)>MAX_BYTES:raise ValueError('Feed response is too large')
    return result

def tools_url(now):
    since=(datetime.fromtimestamp(now,timezone.utc)-timedelta(days=60)).strftime('%Y-%m-%d')
    query=urllib.parse.urlencode({'q':f'topic:llm created:>{since} stars:>=25 archived:false fork:false','sort':'stars','order':'desc','per_page':8})
    return 'https://api.github.com/search/repositories?'+query

def load_cache(path=CACHE):
    result={}
    try:
        value=json.loads(Path(path).read_text())
        for key,host in [('latest','huggingface.co'),('tools','github.com')]:
            source=value.get(key,{})
            if not isinstance(source,dict) or not isinstance(source.get('updated_at'),(float,int)):continue
            items=source.get('items')
            if not isinstance(items,list):continue
            valid=[item for item in items[:8] if isinstance(item,dict) and isinstance(item.get('title'),str) and safe_url(item.get('url'),host)]
            result[key]={'items':valid,'updated_at':source['updated_at']}
    except (OSError,ValueError,TypeError,AttributeError):pass
    return result

def refresh(previous,fetch=read_url,now=None):
    now=time.time() if now is None else now
    result=dict(previous);errors={}
    for key,url,parser in [('latest',RSS,parse_latest),('tools',tools_url(now),parse_tools)]:
        try:result[key]={'items':parser(fetch(url)),'updated_at':now}
        except urllib.error.HTTPError as exc:
            errors[key]='Source rate limit reached. Try again later.' if exc.code in (403,429) else 'Source is unavailable. Try again later.'
        except (OSError,ValueError,TypeError,ET.ParseError):
            errors[key]='Could not reach this source. Check your connection.'
    return result,errors

def save_cache(value,path=CACHE):private_write(Path(path),value)
