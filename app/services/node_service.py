from ..bitcoin_rpc import BitcoinRPC, RPCError

rpc = BitcoinRPC()

def node_status():
    return {
        'chain': safe('getblockchaininfo'),
        'network': safe('getnetworkinfo'),
        'mempool': safe('getmempoolinfo'),
    }

def safe(method, params=None):
    try:
        return rpc.call(method, params or [])
    except Exception as e:
        return {'error': str(e)}
