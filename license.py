"""
Sistem de licență — aplicăția nu pornește fără cod de acces.
Codul e verificat local (nu necesită internet).

Configurare:
  1. La prima pornire, setează codul: python3 license.py --set COD
  2. Codul e salvat hash-uit în .license (nu plaintext)
  3. La fiecare pornire, app.py verifică codul

Pentru a schimba codul: șterge .license și rulează din nou --set
"""
import os
import sys
import hashlib
import getpass

LICENSE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.license')


def _hash_code(code):
    """Hash SHA-256 + salt — nu stocăm codul în plaintext."""
    salt = b'safeguard_vision_2024'
    return hashlib.sha256(salt + code.encode('utf-8')).hexdigest()


def set_license_code(code):
    """Salvează codul de acces (hash-uit) în .license."""
    with open(LICENSE_PATH, 'w') as f:
        f.write(_hash_code(code))
    os.chmod(LICENSE_PATH, 0o600)
    print(f"✅ Cod de acces salvat în .license")


def verify_license_code(code):
    """Verifică dacă codul introdus e corect."""
    if not os.path.exists(LICENSE_PATH):
        return False
    with open(LICENSE_PATH, 'r') as f:
        stored_hash = f.read().strip()
    return _hash_code(code) == stored_hash


def check_license():
    """
    Verifică licența la pornirea aplicației.
    Dacă .license nu există → cere setare cod.
    Dacă există → cere cod de acces.
    Returnează True dacă codul e corect, False altfel.
    """
    if not os.path.exists(LICENSE_PATH):
        print("\n" + "=" * 50)
        print("  PRIMA PORNIRE — Setare cod de acces")
        print("=" * 50)
        print("Codul protejează accesul la codul sursă.")
        code = getpass.getpass("Introduceți cod de acces nou: ")
        if len(code) < 4:
            print("❌ Codul trebuie să aibă minim 4 caractere.")
            return False
        confirm = getpass.getpass("Confirmați codul: ")
        if code != confirm:
            print("❌ Codurile nu coincid.")
            return False
        set_license_code(code)
        return True

    # Verificare cod existent
    print("\n" + "=" * 50)
    print("  Safeguard Vision — Verificare acces")
    print("=" * 50)
    code = getpass.getpass("Cod de acces: ")
    if verify_license_code(code):
        print("✅ Acces permis.")
        return True
    print("❌ Cod de acces incorect.")
    return False


def check_license_noninteractive():
    """
    Verifică non-interactiv — citește codul din variabila de mediu
    SAFEGUARD_LICENSE sau din linia de comandă.
    Util pentru pornire automată (systemd).
    """
    code = os.environ.get('SAFEGUARD_LICENSE', '')
    if not code and len(sys.argv) > 1 and sys.argv[1] == '--license':
        if len(sys.argv) > 2:
            code = sys.argv[2]

    if not code:
        return False

    if not os.path.exists(LICENSE_PATH):
        # Prima pornire non-interactivă → salvează codul
        set_license_code(code)
        return True

    return verify_license_code(code)


if __name__ == '__main__':
    if '--set' in sys.argv:
        idx = sys.argv.index('--set')
        if len(sys.argv) > idx + 1:
            set_license_code(sys.argv[idx + 1])
        else:
            code = getpass.getpass("Cod de acces nou: ")
            set_license_code(code)
    elif '--check' in sys.argv:
        if check_license():
            print("✅ Licență validă")
        else:
            print("❌ Licență invalidă")
            sys.exit(1)
    else:
        check_license()
