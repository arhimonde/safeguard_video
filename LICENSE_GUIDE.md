# 🔒 Licență + Ofuscare Cod — Ghid Complet

Acest sistem protejează codul sursă al aplicației Safeguard Vision:
- **Cod de acces** — aplicația nu pornește fără codul corect
- **Ofuscare PyArmor** — codul sursă devine illegibil (bytecode criptat AES)

---

## 1. Cod de Acces (Licență)

### Prima setare
Codul **îl alegi tu** (minim 4 caractere, recomandat 8+):

```bash
# Metoda 1 — comandă directă
python3 license.py --set CODUL_TAU
# Ex: python3 license.py --set safeguard2024

# Metoda 2 — prima pornire a aplicației
python3 app.py
# → "Introduceți cod de acces nou: ___"
# → "Confirmați codul: ___"
# → Cod salvat automat
```

Codul e salvat **hash-uit** (SHA-256 + salt) în fișierul `.license` — nu în plaintext.

### Verificare la pornire
După setare, la fiecare pornire aplicația cere codul:

```bash
python3 app.py
# → "Cod de acces: ___"
# → Cod corect → aplicația pornește
# → Cod greșit → "Acces refuzat" + se oprește
```

### Pornire automată (systemd)
Pentru ca aplicația să pornească singură după restart (fără să ceară cod interactiv):

```bash
# 1. Setează codul o dată
python3 license.py --set CODUL_TAU

# 2. Editează safeguard.service — adaugă linia:
#    Environment=SAFEGUARD_LICENSE=CODUL_TAU

# 3. Instalează serviciul
sudo cp safeguard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable safeguard
sudo systemctl start safeguard

# Acum aplicația pornește singură după restart
```

### Schimbare cod
```bash
rm .license                    # șterge codul vechi
python3 license.py --set NOU  # setează cod nou
```

### Cod uitat
Codul e **hash-uit** — nu se poate recupera. Dacă îl uiți:
```bash
rm .license
python3 license.py --set NOU_COD
```

---

## 2. Ofuscare Cod Sursă (PyArmor)

### Ce face
Transformă fișierele `.py` în **bytecode criptat AES**:
- Codul sursă nu mai e vizibil (e criptat)
- Aplicația rămâne **funcțională** (descifrare la runtime în memorie)
- Imposibil de reverse-engineering la codul original

### Instalare PyArmor (o singură dată peJetson)
```bash
pip install pyarmor
```

### Ofuscare
```bash
# Pe Jetson, după ce ai terminat de dezvoltat/configurat:
bash obfuscate.sh
```

Rezultat:
- 9 fișiere `.py` → bytecode criptat
- Backup automat în `*.py.bak` (în caz de problemă)
- `license.py` rămâne **neofuscat** (rulează primul, înainte de PyArmor)

### Restaurare (dacă vrei să editezi codul)
```bash
bash obfuscate.sh --restore
# → Toate fișierele .py restaurate din backup
```

### Ce e protejat și ce nu

| Fișier | Protejat? | Motiv |
|---|---|---|
| app.py, detector.py, camera.py, etc. | ✅ Ofuscat | Cod sursă illegibil |
| license.py | ❌ Neofuscat | Rulează primul, înainte de PyArmor |
| templates/*.html, style.css | ❌ Neofuscat | Frontend (vizibil în browser oricum) |
| .license | gitignored | Hash-ul codului de acces |
| .secret_key | gitignored | Cheie sesiuni Flask |
| cameras.json | gitignored | Credențiale RTSP (criptate) |

---

## 3. Workflow Recomandat

### Dezvoltare locală (PC/Mac)
```bash
# Codul e neofuscat — poți edita liber
python3 app.py                    # dezvoltare
git push origin main             # salvează pe GitHub
```

### Deploy pe Jetson
```bash
# 1. Sincronizează codul
bash deploy_to_jetson.sh

# 2. Pe Jetson — instalează dependențe
bash remote_setup_jetson.sh

# 3. Pe Jetson — setează cod de acces
python3 license.py --set CODUL_TAU

# 4. Pe Jetson — ofuscură codul
bash obfuscate.sh

# 5. Pe Jetson — pornește aplicația
python3 app.py
# → cere cod de acces → îl introduci → aplicația rulează
# → codul sursă e illegibil pentru oricine altcineva
```

### Schimbare cod pe Jetson (deja ofuscat)
```bash
# Nu poate rula license.py --set direct (codul e ofuscat)
# Solucție: setează codul ÎNAINTE de ofuscare
bash obfuscate.sh --restore      # restaura
python3 license.py --set NOU_COD # schimbă codul
bash obfuscate.sh                 # re-ofuscură
```

---

## 4. Fișiere relevante

| Fișier | Rol |
|---|---|
| `license.py` | Sistem cod de acces (verifică, setează, hash) |
| `obfuscate.sh` | Script ofuscare PyArmor |
| `.license` | Hash-ul codului (gitignored) |
| `.py.bak` | Backup-uri cod original (gitignored) |
| `safeguard.service` | systemd service (cu `SAFEGUARD_LICENSE` env var) |

---

## TL;DR

1. **`python3 license.py --set COD`** → setează codul de acces
2. **`bash obfuscate.sh`** → ascunde codul sursă (PyArmor)
3. **`python3 app.py`** → cere cod → pornește
4. **`bash obfuscate.sh --restore`** → restaura dacă vrei să editezi
