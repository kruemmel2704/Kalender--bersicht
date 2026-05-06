import os
import sys
import socket
import subprocess
import platform

def get_internal_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Eine Verbindung nach außen aufbauen (ohne wirklich Daten zu senden),
        # um die korrekte lokale IP zu ermitteln.
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def is_tool_installed(name):
    """Überprüft, ob ein CLI-Tool installiert ist."""
    try:
        devnull = open(os.devnull, 'w')
        subprocess.Popen([name], stdout=devnull, stderr=devnull).communicate()
    except OSError as e:
        if e.errno == os.errno.ENOENT:
            return False
    return True

def install_mkcert():
    system = platform.system().lower()
    print("mkcert ist nicht installiert. Versuche automatische Installation...")
    
    if system == "darwin": # macOS
        if not is_tool_installed("brew"):
            print("Homebrew fehlt! Bitte installiere Homebrew, um mkcert automatisch zu laden.")
            sys.exit(1)
        subprocess.check_call(["brew", "install", "mkcert"])
        
    elif system == "linux":
        if is_tool_installed("apt"):
            print("Für die Installation unter Linux werden sudo-Rechte benötigt.")
            subprocess.check_call(["sudo", "apt", "update"])
            subprocess.check_call(["sudo", "apt", "install", "-y", "mkcert", "libnss3-tools"])
        else:
            print("Paketmanager apt nicht gefunden. Bitte installiere mkcert manuell.")
            sys.exit(1)
    else:
        print(f"Betriebssystem {system} wird nicht automatisch unterstützt. Bitte mkcert manuell installieren.")
        sys.exit(1)

def ensure_certificates():
    ip = get_internal_ip()
    # Wir benennen die Zertifikate nach der IP.
    # Wenn sich die IP ändert, werden automatisch neue Zertifikate generiert.
    cert_file = f"cert_{ip}.pem"
    key_file = f"key_{ip}.pem"

    if os.path.exists(cert_file) and os.path.exists(key_file):
        print(f"Gültige Zertifikate für {ip} gefunden.")
        return cert_file, key_file

    print(f"Keine Zertifikate für {ip} gefunden. Generiere neue...")
    
    if not is_tool_installed("mkcert"):
        install_mkcert()

    # Lokale Zertifizierungsstelle (CA) installieren.
    # Das kann unter macOS/Linux nach einem Passwort fragen.
    try:
        print("Installiere lokale CA (falls Passwort abgefragt wird, bitte eingeben)...")
        subprocess.check_call(["mkcert", "-install"])
    except subprocess.CalledProcessError:
        print("Hinweis: 'mkcert -install' fehlgeschlagen oder abgebrochen. Zertifikate werden trotzdem erstellt.")

    # Zertifikate generieren
    try:
        subprocess.check_call([
            "mkcert", 
            "-cert-file", cert_file, 
            "-key-file", key_file, 
            ip, "localhost", "127.0.0.1", "::1"
        ])
        print(f"Zertifikate erfolgreich erstellt: {cert_file}, {key_file}")
    except subprocess.CalledProcessError as e:
        print(f"Fehler bei der Zertifikatserstellung: {e}")
        sys.exit(1)

    return cert_file, key_file
