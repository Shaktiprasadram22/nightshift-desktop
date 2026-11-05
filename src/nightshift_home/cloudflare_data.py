"""Read-only Cloudflare zone analytics, with an honest timestamp and an offline cache."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from data import BASE, HOME, write_json

from sites_config import load_sites
ACCOUNT, SITES = load_sites()
CACHE = HOME / '.cache/nightshift-home/cloudflare.json'
REFRESH_SECONDS = 300
QUERY = '''query($account: string!, $hosts: [string!], $primary: [string!], $start: Time!, $end: Time!) {
  viewer { accounts(filter: {accountTag: $account}) {
    totals: httpRequestsAdaptiveGroups(limit: 20, filter: {datetime_geq: $start, datetime_lt: $end, requestSource: "eyeball", clientRequestHTTPHost_in: $hosts}) {
      count dimensions {clientRequestHTTPHost} sum {edgeResponseBytes}
    }
    history: httpRequestsAdaptiveGroups(limit: 500, filter: {datetime_geq: $start, datetime_lt: $end, requestSource: "eyeball", clientRequestHTTPHost_in: $primary}, orderBy: [datetimeFifteenMinutes_ASC]) {
      count dimensions {clientRequestHTTPHost datetimeFifteenMinutes}
    }
    breakdown: httpRequestsAdaptiveGroups(limit: 2000, filter: {datetime_geq: $start, datetime_lt: $end, requestSource: "eyeball", clientRequestHTTPHost_in: $primary}) {
      count dimensions {clientRequestHTTPHost cacheStatus edgeResponseStatus}
    }
  } }
}'''


def load_cache():
    for path in [CACHE]:
        try:
            value = json.loads(path.read_text())
            datetime.fromtimestamp(value['fetched_at'],timezone.utc)
            datetime.fromisoformat(value['period']['start'].replace('Z','+00:00'))
            datetime.fromisoformat(value['period']['end'].replace('Z','+00:00'))
            if isinstance(value['sites'], list) and value['account_id'] == ACCOUNT:
                return value
        except (OSError, ValueError, KeyError, TypeError, OverflowError, AttributeError):
            pass
    return None


def period(now=None):
    # Match the dashboard's rolling 24h, including the current partial hour.
    now = now or datetime.now(timezone.utc)
    end = now.replace(second=0, microsecond=0)
    return {'start': (end - timedelta(hours=24)).isoformat(), 'end': end.isoformat()}


def normalize(record, name):
    try:return _normalize(record,name)
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):return None


def _normalize(record, name):
    site = next((s for s in (record or {}).get('sites', []) if s['name'] == name), None)
    if not site or not site.get('data'):
        return None
    if record.get('kind')=='account-hosts-v2':return site['data']
    raw = site['data']
    # Missing fields are unavailable data, distinct from an empty valid dataset.
    totals = raw['totals']
    if not isinstance(totals,list) or not isinstance(raw['hourly'],list):return None
    values = totals[0].get('sum', {}) if totals else {}
    requests = values.get('requests', 0)
    responses = values.get('responseStatusMap', [])
    result = dict(name=name, id=site['id'], requests=requests,
                  cached_requests=values.get('cachedRequests', 0), bytes=values.get('bytes', 0),
                  unique_ips=totals[0].get('uniq', {}).get('uniques') if totals else 0,
                  server_errors=sum(r['requests'] for r in responses if 500 <= r['edgeResponseStatus'] < 600),
                  client_errors=sum(r['requests'] for r in responses if 400 <= r['edgeResponseStatus'] < 500),
                  not_found=sum(r['requests'] for r in responses if r['edgeResponseStatus'] == 404))
    result['cache_percent'] = 100 * result['cached_requests'] / requests if requests else None
    # Preserve gaps as zero-volume hours, not as an invented trend between adjacent buckets.
    buckets = {datetime.fromisoformat(row['dimensions']['datetime'].replace('Z','+00:00')).astimezone(timezone.utc): row['sum']['requests'] for row in raw['hourly']}
    start = datetime.fromisoformat(record['period']['start'].replace('Z', '+00:00')).astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    result['hourly'] = [buckets.get(start + timedelta(hours=i), 0) for i in range(24)]
    return result


def compact(value):
    if value is None:return '—'
    if value >= 1_000_000:return f'{value/1_000_000:.1f}m'
    if value >= 10_000:return f'{value/1_000:.0f}k'
    if value >= 1_000:return f'{value/1_000:.2f}k'
    return str(int(value))


def dashboard(name):
    if name not in dict(SITES):raise ValueError('Unknown site.')
    return f'https://dash.cloudflare.com/{ACCOUNT}/'


def account_record(response,window,stamp=None):
    if response.get('errors'):raise RuntimeError('Cloudflare could not return account analytics. Your saved figures remain visible.')
    accounts=response.get('data',{}).get('viewer',{}).get('accounts',[])
    if not accounts:raise RuntimeError('Cloudflare returned no account analytics. Your saved figures remain visible.')
    account=accounts[0]
    if any(not isinstance(account.get(key),list) for key in ('totals','history','breakdown')):
        raise RuntimeError('Cloudflare returned incomplete account analytics.')
    if len(account['history'])>=500 or len(account['breakdown'])>=2000:
        raise RuntimeError('The analytics result reached its limit. Saved figures remain visible.')
    totals={row['dimensions']['clientRequestHTTPHost']:row for row in account['totals']}
    start=datetime.fromisoformat(window['start'].replace('Z','+00:00')).astimezone(timezone.utc)
    end=datetime.fromisoformat(window['end'].replace('Z','+00:00')).astimezone(timezone.utc)
    first=start.replace(minute=start.minute//15*15,second=0,microsecond=0)
    buckets=[];cursor=first
    while cursor<end:buckets.append(cursor);cursor+=timedelta(minutes=15)
    sites=[]
    for name,identifier in SITES:
        row=totals.get(name,{});requests=row.get('count',0)
        parts=[r for r in account['breakdown'] if r['dimensions']['clientRequestHTTPHost']==name]
        cached=sum(r['count'] for r in parts if r['dimensions']['cacheStatus'].lower()=='hit')
        series={datetime.fromisoformat(r['dimensions']['datetimeFifteenMinutes'].replace('Z','+00:00')).astimezone(timezone.utc):r['count'] for r in account['history'] if r['dimensions']['clientRequestHTTPHost']==name}
        metrics=dict(name=name,id=identifier,requests=requests,www_requests=totals.get('www.'+name,{}).get('count',0),
            cached_requests=cached,cache_percent=100*cached/requests if requests else None,
            bytes=row.get('sum',{}).get('edgeResponseBytes',0),unique_ips=None,
            server_errors=sum(r['count'] for r in parts if 500<=r['dimensions']['edgeResponseStatus']<600),
            client_errors=sum(r['count'] for r in parts if 400<=r['dimensions']['edgeResponseStatus']<500),
            not_found=sum(r['count'] for r in parts if r['dimensions']['edgeResponseStatus']==404),
            hourly=[series.get(bucket,0) for bucket in buckets])
        sites.append(dict(name=name,id=identifier,data=metrics))
    return dict(kind='account-hosts-v2',fetched_at=stamp or datetime.now(timezone.utc).timestamp(),period=window,
        account_id=ACCOUNT,source='Cloudflare account HTTP requests · adaptive sampling',
        dataset='httpRequestsAdaptiveGroups',request_source='eyeball',bucket_minutes=15,headline_scope='exact hostname',sites=sites)


def fetch():
    if not ACCOUNT or not SITES:
        raise RuntimeError("Configure your account and hosts in ~/.config/nightshift-home/sites.json, then restart Nightshift.")
    from cloudflare_oauth import execute
    window = period()
    primary=[name for name,_ in SITES]
    variables = {'account':ACCOUNT,'primary':primary,'hosts':primary+['www.'+name for name in primary],**window}
    code = ('async () => { return cloudflare.request({method:"POST",path:"/graphql",body:'
            + json.dumps({'query': QUERY, 'variables': variables}) + '}); }')
    response = execute(code, ACCOUNT)
    record=account_record(response,window)
    write_json(CACHE, record)
    return record
