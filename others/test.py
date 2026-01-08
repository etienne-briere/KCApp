import socket
import subprocess
import platform
import ipaddress
from concurrent.futures import ThreadPoolExecutor


def get_local_ip():
    """Retourne l'adresse IP locale de la machine"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def ping_ip(ip):
    """Pinge une IP pour voir si elle répond"""
    param = "-n" if platform.system().lower() == "windows" else "-c"
    result = subprocess.run(
        ["ping", param, "1", str(ip)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    if result.returncode == 0:
        return str(ip)
    return None


def scan_network():
    local_ip = get_local_ip()
    if not local_ip:
        print("Impossible de scanner le réseau : IP locale introuvable.")
        return []

    print(f"IP locale : {local_ip}")

    net = ipaddress.IPv4Network(local_ip + '/23', strict=False)
    hosts = list(net.hosts())

    print(f"Scan du réseau {net} en cours...")

    alive_hosts = []
    with ThreadPoolExecutor(max_workers=50) as executor:
        results = executor.map(ping_ip, hosts)

    for ip in results:
        if ip:
            alive_hosts.append(ip)

    print(f"{len(alive_hosts)} appareil(s) détecté(s) :")
    for ip in alive_hosts:
        print(f"- {ip}")

    return alive_hosts


# Exécution
if __name__ == "__main__":
    scan_network()

