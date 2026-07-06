# Bitcoin Wallet WebApp v1.0 Final Lab

Eine lokale FastAPI-Webapp als experimentelles Wallet-Frontend für eine private Bitcoin-Core-Mainnet-Fork.

## Features

- Mobile-first Oberfläche
- Login / Registrierung
- mehrere Konten pro User
- BIP39-Mnemonic pro Konto
- Backup / Restore als neues Konto
- eigene HD-Wallet-Logik mit Legacy-P2PKH-Adressen
- Empfangs- und Change-Adressen
- QR-Code-Anzeige für Empfangsadressen
- QR-Code-Scanner im Senden-Formular, sofern der Browser die `BarcodeDetector` API unterstützt
- lokaler SQLite-UTXO-Index
- manueller Scan und Hintergrund-Scan in Blockgruppen
- Coin-Control beim Senden optional
- eigene Coin-Selection
- eigene P2PKH-Signatur
- Broadcast über Bitcoin Core `sendrawtransaction`

## Start

```bash
cp .env.example .env
docker compose up
```

Dann im Browser:

```text
http://localhost:8000
```

## Wichtige Hinweise

Dies ist eine Labor-App für private Chains und Experimente. Private Keys und Mnemonics liegen lokal in SQLite. Nicht für produktives Mainnet verwenden.

## QR-Scanner

Der Scanner nutzt die Browser-API `BarcodeDetector`. Auf vielen aktuellen Android-Chrome/Chromium-Browsern funktioniert das direkt. Falls der Browser die API nicht unterstützt, Adresse einfach manuell einfügen.

## Hintergrund-Scan

Unter **Sync** kann ein Hintergrund-Scan gestartet werden. Die App scannt die Chain in Gruppen, z. B. 200 Blöcke pro Gruppe. Das blockiert die Oberfläche nicht.

Für importierte Konten oder alte Guthaben:

```text
Start-Blockhöhe: 0
```

## Daten

Standardmäßig:

```text
data/app.db
```

