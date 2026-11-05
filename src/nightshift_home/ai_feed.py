"""Fresh, practical AI learning from public engineering feeds. No model calls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from data import HOME
from personal_store import private_write

CACHE = HOME / '.cache/nightshift-home/ai-learning.json'
REFRESH_SECONDS = 300
MAX_BYTES = 2 * 1024 * 1024
MAX_ITEMS = 60
MAX_AGE_DAYS = 90
SOURCES = {
    'huggingface': {'name': 'Hugging Face', 'url': 'https://huggingface.co/blog/feed.xml', 'host': 'huggingface.co'},
    'cloudflare': {'name': 'Cloudflare', 'url': 'https://blog.cloudflare.com/tag/ai/rss/', 'host': 'blog.cloudflare.com'},
    'nvidia': {'name': 'NVIDIA', 'url': 'https://developer.nvidia.com/blog/feed/', 'host': 'developer.nvidia.com'},
    'google': {'name': 'Google Research', 'url': 'https://research.google/blog/rss/', 'host': 'research.google'},
}
HOSTS = {value['host'] for value in SOURCES.values()} | {'docs.vllm.ai'}
TOPICS = {
    'cost': r'cost|cach|quantiz|distill|compress|efficien|spars|prun|small(?:er)? model|token budget|routing',
    'latency': r'latency|inference|throughput|speculative|batch|prefill|decod|serving|streaming|speed|accelerat|cach',
    'build': r'agent|retrieval|\brag\b|evaluat|fine.tun|reasoning|embed|tool.call|guardrail|prompt|deploy|cookbook|tutorial|training',
}
AI_CONTEXT = re.compile(r'\bai\b|\bllms?\b|language model|transformer|agent|inference|retrieval|\brag\b|generative|quantiz|fine.tun|chatbot', re.I)
GUIDES = [
    {'title': 'Reuse repeated prompt prefixes', 'summary': 'Learn how prefix caching avoids recomputing shared prompts in vLLM.', 'url': 'https://docs.vllm.ai/en/stable/features/automatic_prefix_caching/', 'source': 'vLLM', 'topics': ['cost', 'latency'], 'action': 'Test prefix caching on repeated chatbot prompts; compare cost and time to first token.'},
    {'title': 'Choose an inference optimization', 'summary': 'A practical reference for quantization, caching, and efficient model execution.', 'url': 'https://huggingface.co/docs/transformers/en/optimization_overview', 'source': 'Hugging Face', 'topics': ['cost', 'latency'], 'action': 'Benchmark one inference optimization against the same prompts; record latency, memory, and answer quality.'},
    {'title': 'Build and evaluate an AI agent', 'summary': 'Work through tools, agent workflows, and hands-on exercises at your own pace.', 'url': 'https://huggingface.co/learn/agents-course/en/unit0/introduction', 'source': 'Hugging Face', 'topics': ['build'], 'action': 'Build one small agent workflow and test it on a fixed set of tasks before expanding it.'},
    {'title': 'Turn an AI recipe into a small experiment', 'summary': 'Runnable notebooks and examples from the open-source AI cookbook.', 'url': 'https://huggingface.co/learn/cookbook/index', 'source': 'Hugging Face', 'topics': ['build'], 'action': 'Choose one cookbook example, run it locally, and write down what would change in your chatbot.'},
]
GUIDES = [{**item, 'published': None, 'kind': 'guide'} for item in GUIDES]


def clean(value, limit=300):
    value = unescape(str(value or ''))
    value = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', value, flags=re.I | re.S)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]*>', ' ', value)).strip()[:limit]


def safe_url(value, host=None):
    if not isinstance(value, str) or len(value) > 1800 or any(ord(c) < 32 for c in value):
        return False
    try:
        parts = urllib.parse.urlsplit(value)
        return (parts.scheme == 'https' and parts.hostname in ({host} if host else HOSTS)
                and parts.port in (None, 443) and not parts.username and not parts.password)
    except ValueError:
        return False


def canonical_url(value):
    if not safe_url(value):
        raise ValueError('This learning link is not from a supported source.')
    parts = urllib.parse.urlsplit(value)
    query = urllib.parse.urlencode([(k, v) for k, v in urllib.parse.parse_qsl(parts.query)
                                   if not k.lower().startswith('utm_')])
    return urllib.parse.urlunsplit(('https', parts.hostname, parts.path or '/', query, ''))


def topics_for(value):
    return [name for name, pattern in TOPICS.items() if re.search(pattern, value, re.I)]


def suggested_action(title, summary, topics):
    value = (title + ' ' + summary).lower()
    if re.search(r'cach|prefix', value):
        return 'Test caching on repeated chatbot requests; compare cost and time to first token.'
    if re.search(r'quantiz|compress|distill', value):
        return 'Compare a smaller or quantized model on your evaluation prompts; record quality, memory, and cost.'
    if re.search(r'routing|route', value):
        return 'Try routing simple requests to a smaller model; compare total cost and failed-answer rates.'
    if 'latency' in topics:
        return 'Benchmark this technique on the same prompts; compare first-token and total response time.'
    if 'cost' in topics:
        return 'Measure cost per successful chatbot answer before and after trying this technique.'
    return 'Try one idea from this guide in a small prototype and evaluate it on representative tasks.'


def timestamp(value):
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except (TypeError, ValueError, OverflowError):
            return None
    try:
        result = parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).timestamp()
        return result if math.isfinite(result) else None
    except (ValueError, OverflowError, OSError):
        return None


def parse_feed(payload, source, now=None):
    if len(payload) > MAX_BYTES or b'\x00' in payload or b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper():
        raise ValueError('Unexpected feed format or size.')
    now = time.time() if now is None else now
    root = ET.fromstring(payload)
    namespace = '{http://www.w3.org/2005/Atom}'
    if root.tag == namespace + 'feed':
        nodes, atom = root.findall(namespace + 'entry'), True
    elif root.tag == 'rss':
        nodes, atom = root.findall('./channel/item'), False
    else:
        raise ValueError('The source did not return an RSS or Atom feed.')
    result, seen = [], set()
    for node in nodes[:1200]:
        prefix = namespace if atom else ''
        title = clean(node.findtext(prefix + 'title'), 220)
        if atom:
            url = next((el.get('href', '') for el in node.findall(namespace + 'link') if el.get('rel', 'alternate') == 'alternate'), '')
            summary = node.findtext(namespace + 'summary') or node.findtext(namespace + 'content')
            date = node.findtext(namespace + 'published') or node.findtext(namespace + 'updated')
        else:
            url = node.findtext('link', '').strip()
            summary = node.findtext('description') or node.findtext('{http://purl.org/rss/1.0/modules/content/}encoded')
            date = node.findtext('pubDate')
        if not title or not safe_url(url, source['host']):
            continue
        published = timestamp(date)
        if published is None or not now - MAX_AGE_DAYS * 86400 <= published <= now + 86400:
            continue
        summary = clean(summary, 260)
        value = title + ' ' + summary
        topics = topics_for(value)
        if not topics or not AI_CONTEXT.search(value):
            continue
        url = canonical_url(url)
        if url in seen:
            continue
        seen.add(url)
        result.append({'title': title, 'url': url, 'source': source['name'], 'summary': summary,
                       'published': published, 'topics': topics, 'kind': 'article',
                       'action': suggested_action(title, summary, topics)})
    return sorted(result, key=lambda item: item['published'], reverse=True)[:MAX_ITEMS]


def read_url(url, headers=None):
    request = urllib.request.Request(url, headers={'User-Agent': 'Nightshift-Desktop/0.2',
        'Accept': 'application/rss+xml, application/atom+xml, application/xml', **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            if not safe_url(response.url, urllib.parse.urlsplit(url).hostname):
                raise ValueError('The source redirected to an unexpected host.')
            data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError('Feed response is too large.')
            return data, {key: response.headers.get(header, '')[:300] for key, header in [('etag', 'ETag'), ('modified', 'Last-Modified')]}
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return None, {}
        raise


def load_cache(path=CACHE):
    try:
        path = Path(path)
        if path.stat().st_size > 4 * MAX_BYTES:
            return {}
        value = json.loads(path.read_text())
        result = {}
        for key, source in SOURCES.items():
            saved = value.get(key, {})
            stamp = saved.get('updated_at')
            if type(stamp) not in (float, int) or not math.isfinite(stamp) or not 0 <= stamp <= time.time()+86400 or not isinstance(saved.get('items'), list):
                continue
            items = []
            for item in saved['items'][:MAX_ITEMS]:
                if not isinstance(item, dict) or not isinstance(item.get('title'), str) or not safe_url(item.get('url'), source['host']):
                    continue
                published = item.get('published')
                if type(published) not in (float, int) or not math.isfinite(published) or not 0 <= published <= time.time()+86400:
                    continue
                title, summary = clean(item['title'], 220), clean(item.get('summary'), 260)
                topics = topics_for(title + ' ' + summary)
                if not topics:
                    continue
                items.append(dict(title=title, summary=summary, source=source['name'], url=canonical_url(item['url']),
                    published=published, kind='article', topics=topics, action=suggested_action(title, summary, topics)))
            result[key] = {'items': items, 'updated_at': stamp,
                          **{k: saved[k][:300] for k in ('etag', 'modified') if isinstance(saved.get(k), str) and '\n' not in saved[k] and '\r' not in saved[k]}}
        return result
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def refresh(previous, fetch=read_url, now=None):
    now = time.time() if now is None else now
    result, errors = dict(previous), {}
    def update(pair):
        key, source = pair
        old = previous.get(key, {})
        headers = {header: old[field] for field, header in [('etag', 'If-None-Match'), ('modified', 'If-Modified-Since')]
                   if isinstance(old.get(field), str)}
        try:
            payload, validators = fetch(source['url'], headers)
            if payload is None:
                if 'items' not in old:
                    raise ValueError('An unchanged response needs a saved feed.')
                value = {**old, 'updated_at': now}
            else:
                value = {'items': parse_feed(payload, source, now), 'updated_at': now, **validators}
            return key, value, None
        except urllib.error.HTTPError as exc:
            return key, None, 'Source rate limit reached; saved guides remain available.' if exc.code in (403, 429) else 'Source unavailable; saved guides remain available.'
        except (OSError, ValueError, TypeError, ET.ParseError):
            return key, None, 'Could not refresh this source; check your connection and retry.'
    with ThreadPoolExecutor(max_workers=4) as pool:
        for key, value, error in pool.map(update, SOURCES.items()):
            if error:
                errors[key] = error
            else:
                result[key] = value
    return result, errors


def select_items(data, topic='latest', query='', now=None):
    now = time.time() if now is None else now
    query = clean(query, 180).casefold()
    # Search aliases keep ordinary language useful for technical publisher titles.
    words = re.findall(r'[\w-]+', query)
    aliases = {'cheap': 'cost', 'cheaper': 'cost', 'costs': 'cost', 'saving': 'cost', 'savings': 'cost',
               'fast': 'latency', 'faster': 'latency', 'speed': 'latency', 'performance': 'latency',
               'caching': 'cach', 'cache': 'cach', 'cached': 'cach', 'caches': 'cach'}
    words = [aliases.get(word, word) for word in words if word not in {'ai', 'llm', 'how', 'to', 'the', 'a', 'in', 'my', 'chatbot', 'reduce', 'lower', 'and', 'can', 'i', 'do', 'what', 'is', 'for'}]
    seen, items = set(), []
    for key in SOURCES:
        for item in data.get(key, {}).get('items', []):
            if item.get('published', 0) < now - MAX_AGE_DAYS * 86400:
                continue
            if item['url'] not in seen:
                items.append(item);seen.add(item['url'])
    items.sort(key=lambda item: item.get('published', 0), reverse=True)
    if query or topic != 'latest' or not items:
        items.extend(item for item in GUIDES if item['url'] not in seen)
    def matches(item):
        if topic != 'latest' and topic not in item.get('topics', []):
            return False
        haystack = ' '.join([item['title'], item.get('summary', ''), item.get('action', ''), item['source'], *item.get('topics', [])]).casefold()
        return all(word in haystack for word in words)
    return [item for item in items if matches(item)][:60]


def web_search_url(query):
    query = clean(query, 180).strip() or 'chatbot cost latency optimization guides'
    return 'https://www.google.com/search?' + urllib.parse.urlencode({'q': 'AI ' + query})


def save_cache(value, path=CACHE):
    private_write(Path(path), value)
