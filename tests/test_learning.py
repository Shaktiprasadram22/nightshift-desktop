import copy
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
import ai_feed as feed
from learning_actions import append_note, task_text
from personal_store import NotesStore, TodoStore

NOW = 1793880000
RSS = b'''<rss><channel><item><title>Reduce LLM latency with prefix caching</title>
<link>https://huggingface.co/blog/caching?utm_source=rss</link>
<description>&lt;b&gt;Reuse shared prompts&lt;/b&gt; and benchmark AI inference.</description>
<pubDate>Thu, 05 Nov 2026 00:00:00 GMT</pubDate></item>
<item><title>LLM cache unsafe</title><link>javascript:alert(1)</link><pubDate>Thu, 05 Nov 2026 00:00:00 GMT</pubDate></item>
<item><title>LLM cache wrong host</title><link>https://evil.example/guide</link><pubDate>Thu, 05 Nov 2026 00:00:00 GMT</pubDate></item>
</channel></rss>'''
ENGINEERING = b'''<!DOCTYPE html><html><body><article>
<header><time>Nov 04, 2026</time></header>
<h3><a href="/research/engineering-workflows">Scaling engineering workflows</a></h3>
<p>Build reliable systems.<script>ignore this</script></p></article></body></html>'''
GOOGLE_DEVELOPERS = b'''<div class="post-item glue-spacer-1-top">
<div class="post-item__top">\n NOV. 3, 2026\n </div>
<a href="/gemini-routing/" class="post-item__link">
<span class="glue-headline glue-headline--headline-5">Gemini cost per task</span>
<p class="glue-caption">Route chatbot requests to a smaller model.</p></a></div>'''


class LearningFeedTests(unittest.TestCase):
    def test_safe_dated_rss_metadata_and_practical_topics(self):
        items=feed.parse_feed(RSS, feed.SOURCES['huggingface'], NOW)
        self.assertEqual(len(items),1)
        item=items[0]
        self.assertEqual(item['url'],'https://huggingface.co/blog/caching')
        self.assertEqual(item['summary'],'Reuse shared prompts and benchmark AI inference.')
        self.assertIn('cost',item['topics']);self.assertIn('latency',item['topics'])
        self.assertIn('Test caching',item['action'])

    def test_atom_uses_alternate_link_and_publication_date(self):
        atom=b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Benchmark AI inference latency</title>
        <link rel="replies" href="https://developer.nvidia.com/comments"/>
        <link rel="alternate" href="https://developer.nvidia.com/blog/latency/"/>
        <summary>Profile LLM serving.</summary><published>2026-11-05T00:00:00Z</published><updated>2026-11-04T00:00:00Z</updated></entry></feed>'''
        item=feed.parse_feed(atom,feed.SOURCES['nvidia'],NOW)[0]
        self.assertEqual(item['url'],'https://developer.nvidia.com/blog/latency/')
        self.assertEqual(item['published'],feed.timestamp('2026-11-05T00:00:00Z'))

    def test_requested_official_rss_sources_and_brand_context(self):
        for key, title in [('openai', 'OpenAI prompt caching'), ('n8n', 'Build a Claude agent in n8n'),
                           ('google_ai', 'Gemini inference latency')]:
            source = feed.SOURCES[key]
            rss = RSS.replace(b'huggingface.co', source['host'].encode())
            rss = rss.replace(b'Reduce LLM latency with prefix caching', title.encode())
            rss = rss.replace(b'&lt;b&gt;Reuse shared prompts&lt;/b&gt; and benchmark AI inference.', b'Practical developer guide.')
            items = feed.parse_feed(rss, source, NOW)
            self.assertEqual(len(items), 1, key)
            self.assertEqual(items[0]['source'], source['name'])

    def test_anthropic_official_index_dates_links_and_cache(self):
        source = feed.SOURCES['anthropic']
        items = feed.parse_index(ENGINEERING, source, NOW)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item['source'], 'Anthropic / Claude')
        self.assertEqual(item['url'], 'https://www.anthropic.com/research/engineering-workflows')
        self.assertEqual(item['summary'], 'Build reliable systems.')
        self.assertEqual(item['topics'], ['build'])
        self.assertEqual(item['published'], feed.timestamp('2026-11-04T00:00:00Z'))
        iso = ENGINEERING.replace(b'<time>Nov 04, 2026</time>', b'<time datetime="2026-11-04T00:00:00Z">4 November</time>')
        self.assertEqual(feed.parse_index(iso, source, NOW), items)
        self.assertEqual(feed.parse_index(ENGINEERING + ENGINEERING, source, NOW), items)
        for bad in [b'https://evil.example/research/test', b'javascript:alert(1)', b'/careers/test']:
            self.assertEqual(feed.parse_index(ENGINEERING.replace(b'/research/engineering-workflows', bad), source, NOW), [])
        self.assertEqual(feed.parse_index(ENGINEERING.replace(b'2026', b'2020'), source, NOW), [])
        self.assertEqual(feed.parse_index(ENGINEERING.replace(b'Nov 04, 2026', b'unknown'), source, NOW), [])
        for payload in [b'<html>Maintenance</html>', b'\x00<article/>', b'X' * (feed.MAX_BYTES + 1)]:
            with self.assertRaises(ValueError): feed.parse_index(payload, source, NOW)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'cache.json'
            value = {'anthropic': {'items': items, 'updated_at': NOW}}
            feed.save_cache(value, path)
            self.assertEqual(feed.load_cache(path)['anthropic']['items'], items)

    def test_engineering_index_changes_preserve_previous_cache(self):
        previous = {'anthropic': {'items': feed.parse_index(ENGINEERING, feed.SOURCES['anthropic'], NOW), 'updated_at': NOW - 300}}
        def fetch(url, headers):
            if 'developers.googleblog' in url: return GOOGLE_DEVELOPERS, {}
            return (b'<html>Maintenance</html>' if 'anthropic' in url else b'<rss><channel/></rss>'), {}
        value, errors = feed.refresh(previous, fetch, NOW)
        self.assertEqual(value['anthropic'], previous['anthropic'])
        self.assertEqual(set(errors), {'anthropic'})

    def test_google_developer_index_uses_publisher_dates(self):
        source = feed.SOURCES['google_developers']
        item = feed.parse_index(GOOGLE_DEVELOPERS, source, NOW)[0]
        self.assertEqual(item['published'], feed.timestamp('2026-11-03T00:00:00Z'))
        self.assertEqual(item['url'], 'https://developers.googleblog.com/gemini-routing/')
        self.assertIn('cost', item['topics'])
        self.assertIn('routing', item['action'])
        self.assertEqual(feed.parse_index(GOOGLE_DEVELOPERS.replace(b'NOV. 3, 2026', b'JAN. 3, 2020'), source, NOW), [])
        with self.assertRaises(ValueError):
            feed.parse_index(b'<html>Unavailable</html>', source, NOW)

    def test_html_xml_bad_dates_old_news_and_non_ai_are_not_live_learning(self):
        for payload in [b'<html>error page</html>', b'<!DOCTYPE x [<!ENTITY boom "x">]><rss/>', b'\x00<rss/>']:
            with self.assertRaises(ValueError):feed.parse_feed(payload,feed.SOURCES['huggingface'],NOW)
        self.assertEqual(feed.parse_feed(RSS.replace(b'2026',b'2020'),feed.SOURCES['huggingface'],NOW),[])
        self.assertEqual(feed.parse_feed(RSS.replace(b'Thu, 05 Nov 2026 00:00:00 GMT',b'unknown'),feed.SOURCES['huggingface'],NOW),[])
        self.assertEqual(feed.parse_feed(RSS.replace(b'Thu, 05 Nov 2026',b'Thu, 05 Nov 2030'),feed.SOURCES['huggingface'],NOW),[])
        self.assertFalse(feed.safe_url('https://huggingface.co@evil.example/guide'))
        self.assertFalse(feed.safe_url('https://huggingface.co:444/guide'))

    def test_partial_failure_and_304_preserve_per_source_data(self):
        item=feed.parse_feed(RSS,feed.SOURCES['huggingface'],NOW)[0]
        previous={'huggingface':{'items':[item],'updated_at':NOW-300,'etag':'"fixture"'},'cloudflare':{'items':[],'updated_at':NOW-300}}
        def fetch(url,headers):
            if 'huggingface' in url:
                self.assertEqual(headers['If-None-Match'],'"fixture"');return None,{}
            if 'cloudflare' in url:raise HTTPError(url,429,'limited',{},None)
            if 'anthropic' in url:return ENGINEERING,{}
            if 'developers.googleblog' in url:return GOOGLE_DEVELOPERS,{}
            return b'<rss><channel/></rss>',{'etag':'new'}
        value,errors=feed.refresh(previous,fetch,NOW)
        self.assertEqual(value['huggingface']['items'],[item])
        self.assertEqual(value['huggingface']['updated_at'],NOW)
        self.assertEqual(value['cloudflare'],previous['cloudflare'])
        self.assertIn('rate limit',errors['cloudflare'])
        self.assertEqual(set(errors),{'cloudflare'})

    def test_cache_roundtrip_sanitizes_metadata_and_never_stores_searches(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cache.json'
            item=feed.parse_feed(RSS,feed.SOURCES['huggingface'],NOW)[0]
            value={'huggingface':{'items':[item],'updated_at':NOW,'etag':'fixture','modified':''}}
            feed.save_cache(value,path)
            self.assertEqual(feed.load_cache(path),value)
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            item['url']='https://evil.example/guide';feed.save_cache(value,path)
            self.assertEqual(feed.load_cache(path)['huggingface']['items'],[])

    def test_topic_search_and_reference_guides_have_honest_dates(self):
        item=feed.parse_feed(RSS,feed.SOURCES['huggingface'],NOW)[0]
        data={'huggingface':{'items':[item],'updated_at':NOW}}
        self.assertEqual(feed.select_items(data,now=NOW),[item])
        found=feed.select_items(data,'cost','how to reduce chatbot cost',NOW)
        self.assertIn(item,found);self.assertTrue(any(x['kind']=='guide' for x in found))
        self.assertEqual(feed.select_items(data,query='not-a-real-topic-xyz',now=NOW),[])
        for query in ('cache','caching','cached','how can I reduce latency'):
            self.assertTrue(feed.select_items({},query=query,now=NOW),query)
        self.assertTrue(all(x['published'] is None for x in feed.GUIDES))
        query='caching & latency # "$()"'
        parsed=urlsplit(feed.web_search_url(query))
        self.assertEqual(parsed.netloc,'www.google.com')
        self.assertEqual(parse_qs(parsed.query)['q'],['AI '+query])

    def test_nvidia_guides_remain_findable_with_a_full_article_cache(self):
        template = feed.parse_feed(RSS.replace(b'huggingface.co', b'developer.nvidia.com'), feed.SOURCES['nvidia'], NOW)[0]
        articles = [{**template, 'url': f'https://developer.nvidia.com/blog/example-{i}/', 'published': NOW - i} for i in range(feed.MAX_ITEMS)]
        matches = feed.select_items({'nvidia': {'items': articles}}, query='NVIDIA', now=NOW)
        guides = [item for item in matches if item['kind'] == 'guide']
        self.assertEqual(len(guides), 3)
        self.assertEqual(matches[:3], guides)
        self.assertTrue(any(item['kind'] == 'article' for item in matches))
        self.assertTrue(all(item['published'] is None and item['source'].startswith('NVIDIA') for item in guides))
        for item in guides:
            self.assertEqual(feed.canonical_url(item['url']), item['url'])
            self.assertTrue(append_note('', item)[1])


class LearningSaveTests(unittest.TestCase):
    def setUp(self):self.item=copy.deepcopy(feed.GUIDES[0])

    def test_note_append_preserves_text_and_deduplicates_exact_source(self):
        current='My private notes\n  keep whitespace  \n'
        result,added=append_note(current,self.item)
        self.assertTrue(added);self.assertTrue(result.startswith(current))
        self.assertIn('Try: ',result);self.assertIn('Source: '+self.item['url'],result)
        self.assertEqual(append_note(result,self.item),(result,False))

    def test_task_preserves_existing_items_and_retains_link_after_edit_undo_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'todos.json';store=TodoStore(path)
            original=store.add('Keep existing task')
            task=store.add(task_text(self.item),source_url=self.item['url'])
            self.assertEqual(store.items[0]['id'],original)
            self.assertEqual(store.add(task_text(self.item),source_url=self.item['url']),task)
            self.assertEqual(len(store.items),2)
            store.update(task,text='My own experiment');store.remove(task);store.undo()
            loaded=TodoStore(path)
            self.assertEqual(loaded.items[-1]['source_url'],self.item['url'])
            self.assertEqual(loaded.items[-1]['text'],'My own experiment')

    def test_failed_writes_keep_previous_documents(self):
        with tempfile.TemporaryDirectory() as folder:
            notes=NotesStore(Path(folder)/'notes.json');notes.save('keep')
            todo=TodoStore(Path(folder)/'todos.json');todo.add('keep')
            with patch('personal_store.private_write',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):notes.save(append_note(notes.text,self.item)[0])
                with self.assertRaises(OSError):todo.add(task_text(self.item),source_url=self.item['url'])
            self.assertEqual(notes.text,'keep');self.assertEqual(len(todo.items),1)
            self.assertEqual(NotesStore(notes.path).text,'keep')

    def test_unsafe_or_incomplete_learning_is_not_saved(self):
        for item in [{**self.item,'url':'javascript:alert(1)'},{**self.item,'action':''}]:
            with self.assertRaises(ValueError):append_note('keep',item)
