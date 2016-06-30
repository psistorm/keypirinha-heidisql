import winreg

class HeidiRegistry:

    HEIDI_REGISTRY_PATH = r'SOFTWARE\\HeidiSQL\\Servers'

    def get_sessions(self):
        list_of_sessions = []
        self._traverse_registry_tree(winreg.HKEY_CURRENT_USER, self.HEIDI_REGISTRY_PATH, list_of_sessions)
        return list_of_sessions

    def _get_subkeys(self, key):
        i = 0
        while True:
            try:
                subkey = winreg.EnumKey(key, i)
                yield subkey
                i += 1
            except WindowsError as e:
                break

    def _traverse_registry_tree(self, hkey, keypath, list_of_sessions, tabs=0):
        with winreg.OpenKey(hkey, keypath, 0, winreg.KEY_READ) as key:
            hostName = ''
            try:
                hostName, hostNameType = winreg.QueryValueEx(key, 'Host')
            except FileNotFoundError as e:
                pass

            if not hostName:
                for subkeyname in self._get_subkeys(key):
                    subkeypath = "%s\\%s" % (keypath, subkeyname)
                    self._traverse_registry_tree(hkey, subkeypath, list_of_sessions, tabs + 1)
            else:
                list_of_sessions.append(keypath.rpartition('Servers\\')[2])