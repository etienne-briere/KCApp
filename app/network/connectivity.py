from kivy.utils import platform

def is_bluetooth_enabled():

    if platform == "android":
        from jnius import autoclass
        BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
        adapter = BluetoothAdapter.getDefaultAdapter()
        return adapter and adapter.isEnabled()

    return False

def is_wifi_enabled():

    if platform == "android":
        from jnius import autoclass
        from android import mActivity

        Context = autoclass('android.content.Context')
        WifiManager = autoclass('android.net.wifi.WifiManager')

        wifi_manager = mActivity.getSystemService(Context.WIFI_SERVICE)
        return wifi_manager.isWifiEnabled()
    
    elif platform == "win":
        # méthode simple : vérifier si une interface réseau est active
        import socket
        try:
            socket.create_connection(("8.8.8.8", 53))
            return True
        except:
            return False

    return False

def get_wifi_ssid():
    """Nom du réseau Wi-Fi actuellement connecté, ou None si indisponible."""

    if platform == "android":
        # Depuis Android 8+, le SSID réel n'est retourné que si la
        # permission ACCESS_FINE_LOCATION est accordée et la localisation
        # activée (restriction du système, pas de ce code) — sinon
        # getSSID() renvoie "<unknown ssid>".
        from jnius import autoclass
        from android import mActivity

        Context = autoclass('android.content.Context')
        WifiManager = autoclass('android.net.wifi.WifiManager')

        wifi_manager = mActivity.getSystemService(Context.WIFI_SERVICE)
        info = wifi_manager.getConnectionInfo()
        ssid = info.getSSID() if info else None
        return ssid.strip('"') if ssid else None

    elif platform == "win":
        import subprocess
        try:
            output = subprocess.check_output(
                ["netsh", "wlan", "show", "interfaces"],
                stderr=subprocess.DEVNULL,
                encoding="oem",
            )
            for line in output.splitlines():
                line = line.strip()
                if line.startswith("SSID"):
                    return line.split(":", 1)[1].strip()
        except Exception:
            return None

    return None