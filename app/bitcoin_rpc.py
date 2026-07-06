import json
import requests
from .config import get_settings

settings = get_settings()

class RPCError(Exception):
    pass

class BitcoinRPC:
    def __init__(self):
        self.url = f'http://{settings.rpc_host}:{settings.rpc_port}/'
        self.auth = (settings.rpc_user, settings.rpc_password)
        self.timeout = settings.rpc_timeout

    def call(self, method: str, params=None):
        payload = {'jsonrpc': '1.0', 'id': 'wallet-web', 'method': method, 'params': params or []}
        try:
            r = requests.post(self.url, auth=self.auth, data=json.dumps(payload), headers={'content-type': 'text/plain'}, timeout=self.timeout)
        except requests.RequestException as e:
            raise RPCError(f'Bitcoin Core nicht erreichbar: {e}')
        if r.status_code != 200:
            raise RPCError(f'Bitcoin Core RPC HTTP {r.status_code}: {r.text[:300]}')
        try:
            data = r.json()
        except ValueError:
            raise RPCError('Ungültige JSON-Antwort von Bitcoin Core.')
        if data.get('error'):
            raise RPCError(str(data['error']))
        return data.get('result')
