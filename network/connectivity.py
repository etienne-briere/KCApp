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