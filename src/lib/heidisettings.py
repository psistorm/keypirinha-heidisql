import re
import os

class HeidiSettings:

    HEIDI_SETTINGS_FILE = 'portable_settings.txt'

    def get_sessions(self, path):
        list_of_sessions = []

        settingsFile = os.path.join(path, self.HEIDI_SETTINGS_FILE)
        with open(settingsFile) as f:
            for line in f:
                match = re.search(r'Servers.*\\(.*)\\Host', line)
                if match:
                    session_name = match.group(1)
                    list_of_sessions.append(session_name)

        return list_of_sessions