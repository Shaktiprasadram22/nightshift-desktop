"""Read dated article cards from official Anthropic and Google indexes."""
from html.parser import HTMLParser
from urllib.parse import urljoin


class ArticleIndex(HTMLParser):
    """Prefer semantic elements; Google uses post-item divs instead."""

    def __init__(self, base_url, kind):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.kind = kind
        self.articles = []
        self.card = None
        self.field = None
        self.field_tag = None
        self.heading = None
        self.ignored = None
        self.container = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        if tag in ('script', 'style'):
            self.ignored = tag
        if self.ignored:
            return
        starts_card = ((self.kind == 'engineering' and tag == 'article') or
                       (self.kind == 'google_developers' and tag == 'div' and 'post-item' in classes))
        if self.card is None and starts_card:
            self.card = {'title': '', 'url': '', 'summary': '', 'date': ''}
            self.field = self.field_tag = self.heading = None
            self.container, self.depth = tag, 1
        elif self.card is not None and tag == self.container:
            self.depth += 1
        if self.card is None:
            return
        if tag in ('h2', 'h3') or (tag == 'span' and 'glue-headline' in classes):
            self.heading = tag
            self.field, self.field_tag = 'title', tag
        elif tag == 'a' and (self.heading or 'post-item__link' in classes) and not self.card['url']:
            self.card['url'] = urljoin(self.base_url, attrs.get('href', ''))
        elif tag == 'time':
            if attrs.get('datetime'):
                self.card['date'] = attrs['datetime']
            else:
                self.field, self.field_tag = 'date', tag
        elif tag == 'div' and 'post-item__top' in classes:
            self.field, self.field_tag = 'date', tag
        elif tag == 'p' and not self.heading:
            self.field, self.field_tag = 'summary', tag
            self.card['summary'] += ' '

    def handle_endtag(self, tag):
        if self.ignored:
            if tag == self.ignored:
                self.ignored = None
            return
        if self.card is None:
            return
        if tag == self.field_tag:
            self.field = self.field_tag = None
        if tag == self.heading:
            self.heading = None
        if tag == self.container:
            self.depth -= 1
        if not self.depth:
            if all(self.card[key].strip() for key in ('title', 'url', 'date')):
                self.articles.append(self.card)
            self.card = None

    def handle_data(self, data):
        if self.card is not None and self.field and not self.ignored:
            self.card[self.field] += data


def article_records(payload, base_url, kind):
    parser = ArticleIndex(base_url, kind)
    parser.feed(payload.decode('utf-8'))
    parser.close()
    if not parser.articles:
        raise ValueError('The publisher index did not contain dated article cards.')
    return parser.articles
