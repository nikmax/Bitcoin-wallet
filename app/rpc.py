import requests
from .config import settings

class RPCError(Exception): pass

class BitcoinRPC:
    def __init__(self):
        self.url = f"http://{settings.rpc_host}:{settings.rpc_port}/"
        self.auth = (settings.rpc_user, settings.rpc_password)
    def call(self, method, params=None):
        payload = {'jsonrpc':'1.0','id':'wallet-web','method':method,'params':params or []}
        try:
            r = requests.post(self.url, json=payload, auth=self.auth, timeout=settings.rpc_timeout)
        except requests.RequestException as e:
            raise RPCError(f'Bitcoin Core nicht erreichbar: {e}')
        if r.status_code != 200:
            raise RPCError(f'Bitcoin Core RPC HTTP {r.status_code}: {r.text}')
        data = r.json()
        if data.get('error'):
            raise RPCError(f"Bitcoin Core RPC Fehler {data['error'].get('code')}: {data['error'].get('message')}")
        return data.get('result')
