# Private Bitcoin Core Wallet Frontend

Lokale FastAPI-Webapp als einfaches Wallet-Frontend und Light-Explorer für eine private historische Bitcoin-Mainnet-Fork.

**Nicht für produktiven Mainnet-Betrieb verwenden.** Die App ist für Lernen, LAN/local Experimente und eine private Chain gedacht.

## Funktionen

- Bitcoin Core JSON-RPC über `.env`
- optionaler Wallet-Endpoint `/wallet/<walletname>`
- Dashboard: Chain, Bestblockhash, Difficulty, IBD, Peers, Mempool, Wallet-Balances
- Wallet: neue Adresse, bekannte Adressen, `getbalances`, `listunspent 0`, `listtransactions`
- Coinbase-/immature-Hinweise in Wallet-Transaktionen
- Sendeflow mit Preview-Seite und anschließendem `sendtoaddress`
- Mempool: `getmempoolinfo`, `getrawmempool`, einzelne TX anzeigen
- Block-Explorer: Suche nach Höhe oder Hash, `getblock <hash> 2`, Inputs/Outputs, Coinbase-Markierung
- Jinja2, mobilfreundliches CSS, kein Frontend-Framework
- optionale Basic Auth

## Projektstruktur

```text
bitcoin_wallet_webapp/
├── app/
│   ├── auth.py
│   ├── config.py
│   ├── main.py
│   ├── rpc.py
│   ├── static/
│   │   └── style.css
│   └── templates/
│       ├── base.html
│       ├── block.html
│       ├── dashboard.html
│       ├── error.html
│       ├── mempool.html
│       ├── send.html
│       └── wallet.html
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── README.md
└── requirements.txt
```

## Bitcoin Core vorbereiten

Beispiel `bitcoin.conf` für LAN/local RPC. Passe User, Passwort, IPs und Chain-Daten an deine Umgebung an.

```ini
server=1
rpcuser=rpcuser
rpcpassword=rpcpassword
rpcbind=127.0.0.1
rpcallowip=127.0.0.1

# Falls Docker-Container oder LAN-Client zugreifen sollen, gezielt erlauben:
# rpcbind=0.0.0.0
# rpcallowip=172.16.0.0/12
# rpcallowip=192.168.0.0/16

# Optional, wenn Wallet beim Start geladen werden soll:
# wallet=deinwalletname
```

Wichtig: RPC niemals ungeschützt ins Internet hängen. Nutze Firewall, LAN-only Binding und am besten Basic Auth für diese Webapp.

## Start mit Docker Compose

```bash
cp .env.example .env
nano .env

docker compose up --build
```

Dann öffnen:

```text
http://localhost:8000
```

Auf Android im LAN:

```text
http://<IP-des-Docker-Hosts>:8000
```

## `.env` Beispiele

Wenn `bitcoind` direkt auf dem Host läuft und Docker auf Linux genutzt wird:

```env
BITCOIN_RPC_HOST=host.docker.internal
BITCOIN_RPC_PORT=8332
BITCOIN_RPC_USER=rpcuser
BITCOIN_RPC_PASSWORD=rpcpassword
BITCOIN_RPC_WALLET=meinwallet
WEB_AUTH_USER=admin
WEB_AUTH_PASSWORD=bitte-aendern
```

Wenn `bitcoind` auf einem LAN-Rechner läuft:

```env
BITCOIN_RPC_HOST=192.168.1.20
BITCOIN_RPC_PORT=8332
BITCOIN_RPC_USER=rpcuser
BITCOIN_RPC_PASSWORD=rpcpassword
BITCOIN_RPC_WALLET=meinwallet
```

Wenn kein Wallet-Endpoint genutzt werden soll:

```env
BITCOIN_RPC_WALLET=
```

Dashboard funktioniert dann eingeschränkt; Walletseiten brauchen ein geladenes Wallet.

## Nützliche Bitcoin-CLI Kommandos

RPC testen:

```bash
bitcoin-cli -rpcuser=rpcuser -rpcpassword=rpcpassword getblockchaininfo
bitcoin-cli -rpcuser=rpcuser -rpcpassword=rpcpassword getnetworkinfo
bitcoin-cli -rpcuser=rpcuser -rpcpassword=rpcpassword getmempoolinfo
```

Wallet prüfen/laden:

```bash
bitcoin-cli listwallets
bitcoin-cli loadwallet meinwallet
bitcoin-cli -rpcwallet=meinwallet getwalletinfo
bitcoin-cli -rpcwallet=meinwallet getbalances
```

Adressen/UTXOs/Transaktionen:

```bash
bitcoin-cli -rpcwallet=meinwallet getnewaddress "test"
bitcoin-cli -rpcwallet=meinwallet listreceivedbyaddress 0 true true
bitcoin-cli -rpcwallet=meinwallet listunspent 0
bitcoin-cli -rpcwallet=meinwallet listtransactions "*" 20 0 true
```

Block-Explorer:

```bash
bitcoin-cli getblockhash 0
bitcoin-cli getblock "<hash>" 2
```

Mempool:

```bash
bitcoin-cli getrawmempool
bitcoin-cli getrawtransaction "<txid>" true
```

## Hinweis zu Fee-Rate

Das Formular nimmt optional `sat/vB`. Die App konvertiert auf `BTC/kvB` für den `sendtoaddress` Parameter `fee_rate`. Je nach Bitcoin-Core-Version kann sich die genaue Signatur optionaler Parameter unterscheiden. Wenn deine Version dabei meckert, entferne die Fee-Rate im Formular oder passe `send_to_address()` in `app/rpc.py` an deine Core-Version an.

## Lokale Entwicklung ohne Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
