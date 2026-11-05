"""Explicit, local Cloudflare configuration. No account or host is bundled."""
import json
import re
from data import HOME

PATH = HOME / '.config/nightshift-home/sites.json'


def load_sites(path=PATH):
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError:
        return '', []
    except (OSError, ValueError) as exc:
        raise ValueError('Could not read sites.json; use the documented JSON format.') from exc
    account = value.get('account_id', '')
    if not re.fullmatch(r'[0-9a-f]{32}', account):
        raise ValueError('sites.json needs a 32-character Cloudflare account_id.')
    hosts = value.get('hosts', [])
    if not isinstance(hosts, list) or not 1 <= len(hosts) <= 4:
        raise ValueError('Configure one to four primary hostnames in sites.json.')
    result = []
    for host in hosts:
        if not isinstance(host, str) or len(host) > 253 or not re.fullmatch(
                r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', host):
            raise ValueError('Use bare lowercase public hostnames, without URLs or ports.')
        if host.endswith(('.local', '.localhost', '.internal')) or host in result:
            raise ValueError('Use distinct public hostnames.')
        result.append(host)
    # The current account-host query does not require zone IDs.
    return account, [(host, host) for host in result]
