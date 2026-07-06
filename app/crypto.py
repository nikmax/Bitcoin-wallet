import os, hmac, hashlib, struct
from ecdsa import SECP256k1, SigningKey
from mnemonic import Mnemonic

ALPHABET='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
N=SECP256k1.order
G=SECP256k1.generator

def sha256(b): return hashlib.sha256(b).digest()
def ripemd160(b):
    h=hashlib.new('ripemd160'); h.update(b); return h.digest()
def hash160(b): return ripemd160(sha256(b))
def dblsha(b): return sha256(sha256(b))

def b58encode(b):
    n=int.from_bytes(b,'big'); s=''
    while n: n,r=divmod(n,58); s=ALPHABET[r]+s
    return '1'*(len(b)-len(b.lstrip(b'\0'))) + (s or '')
def b58check(prefix, payload):
    data=bytes([prefix])+payload
    return b58encode(data+dblsha(data)[:4])
def address_from_pubkey(pub): return b58check(0x00, hash160(pub))
def wif_from_priv(priv): return b58check(0x80, priv+b'\x01')

def priv_to_pub(priv):
    sk=SigningKey.from_string(priv, curve=SECP256k1)
    point = sk.verifying_key.pubkey.point
    p = point() if callable(point) else point
    x=p.x(); y=p.y()
    return (b'\x02' if y%2==0 else b'\x03') + x.to_bytes(32,'big')

def gen_mnemonic(): return Mnemonic('english').generate(strength=128)
def seed_from_mnemonic(words): return Mnemonic('english').to_seed(words, passphrase='')

def ser32(i): return struct.pack('>L', i)
def ser256(i): return i.to_bytes(32,'big')
def parse256(b): return int.from_bytes(b,'big')
def point_from_pub(pub):
    prefix=pub[0]; x=int.from_bytes(pub[1:],'big'); curve=SECP256k1.curve
    alpha=(x*x*x+curve.a()*x+curve.b())%curve.p(); beta=pow(alpha,(curve.p()+1)//4,curve.p())
    y=beta if (beta%2==0)==(prefix==2) else curve.p()-beta
    return x,y

def master_from_seed(seed):
    I=hmac.new(b'Bitcoin seed', seed, hashlib.sha512).digest()
    return I[:32], I[32:]

def ckd_priv(k, c, i):
    hardened=i>=0x80000000
    data=(b'\x00'+k if hardened else priv_to_pub(k)) + ser32(i)
    I=hmac.new(c, data, hashlib.sha512).digest(); IL,IR=I[:32],I[32:]
    child=(parse256(IL)+parse256(k))%N
    if child==0: raise ValueError('invalid child key')
    return ser256(child), IR

def derive_path(seed, path):
    k,c=master_from_seed(seed)
    for part in path.split('/')[1:]:
        hardened=part.endswith("'"); num=int(part.rstrip("'")) + (0x80000000 if hardened else 0)
        k,c=ckd_priv(k,c,num)
    return k,c

def derive_address(seed_hex, branch, idx):
    seed=bytes.fromhex(seed_hex); path=f"m/44'/0'/0'/{branch}/{idx}"
    priv,_=derive_path(seed,path); pub=priv_to_pub(priv)
    return {'path':path,'privkey_hex':priv.hex(),'pubkey_hex':pub.hex(),'wif':wif_from_priv(priv),'address':address_from_pubkey(pub)}

def varint(n):
    if n<0xfd: return bytes([n])
    if n<=0xffff: return b'\xfd'+struct.pack('<H',n)
    if n<=0xffffffff: return b'\xfe'+struct.pack('<I',n)
    return b'\xff'+struct.pack('<Q',n)
def le32(n): return struct.pack('<I',n)
def le64(n): return struct.pack('<Q',n)
def der_sig(r,s):
    if s>N//2: s=N-s
    def enc(x):
        b=x.to_bytes((x.bit_length()+7)//8 or 1,'big')
        return b'\x00'+b if b[0]&0x80 else b
    rb,sb=enc(r),enc(s)
    return b'\x30'+bytes([4+len(rb)+len(sb)])+b'\x02'+bytes([len(rb)])+rb+b'\x02'+bytes([len(sb)])+sb

def p2pkh_scriptpubkey(address):
    # decode minimal b58check
    n=0
    for ch in address: n=n*58+ALPHABET.index(ch)
    full=n.to_bytes((n.bit_length()+7)//8,'big')
    full=b'\0'*(len(address)-len(address.lstrip('1'))) + full
    h160=full[1:-4]
    return b'\x76\xa9\x14'+h160+b'\x88\xac'

def serialize_tx(inputs, outputs):
    res=le32(1)+varint(len(inputs))
    for i in inputs:
        res+=bytes.fromhex(i['txid'])[::-1]+le32(i['vout'])+varint(len(i.get('script_sig',b'')))+i.get('script_sig',b'')+bytes.fromhex('ffffffff')
    res+=varint(len(outputs))
    for o in outputs:
        spk=p2pkh_scriptpubkey(o['address'])
        res+=le64(o['amount_sats'])+varint(len(spk))+spk
    return res+le32(0)

def sign_p2pkh(inputs, outputs):
    signed=[]
    for idx, inp in enumerate(inputs):
        tmp=[]
        for j,x in enumerate(inputs):
            script=p2pkh_scriptpubkey(x['address']) if j==idx else b''
            tmp.append({**x,'script_sig':script})
        sighash=dblsha(serialize_tx(tmp, outputs)+le32(1))
        sk=SigningKey.from_string(bytes.fromhex(inp['privkey_hex']), curve=SECP256k1)
        sig=sk.sign_digest_deterministic(sighash, sigencode=lambda r,s,order: der_sig(r,s)) + b'\x01'
        pub=bytes.fromhex(inp['pubkey_hex'])
        script=varint(len(sig))+sig+varint(len(pub))+pub
        signed.append({**inp,'script_sig':script})
    return serialize_tx(signed, outputs).hex()
