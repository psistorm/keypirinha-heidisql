import keypirinha as kp
import keypirinha_util as kpu
import os
from .lib.heidiregistry import HeidiRegistry
from .lib.heidisettings import HeidiSettings

class HeidiSQL(kp.Plugin):
    """
    Launch HeidiSQL sessions.

    This plugin automatically detects the installed version of the official
    HeidiSQL distribution and lists its configured sessions so they can be launched
    directly without having to pass through the sessions selection dialog
    """

    DIST_SECTION_PREFIX = "dist/"  # lower case

    EXE_NAME_OFFICIAL = "HEIDISQL.EXE"

    _registry_reader = None
    _settings_reader = None

    _default_icon_handle = None
    _distros = {}

    def __init__(self):
        super().__init__()

    def __del__(self):
        self._clean_icon()

    def on_start(self):
        self._registry_reader = HeidiRegistry()
        self._settings_reader = HeidiSettings()
        self._read_config()

    def on_catalog(self):
        self._read_config()
        catalog = []

        for distro_name, distro in self._distros.items():
            if not distro['enabled']:
                continue
            self.dbg('Creating catalogItem for action: ', distro['label'], distro['exe_file'])
            catalog.append(self.create_item(
                category=kp.ItemCategory.KEYWORD,
                label=distro['label'],
                short_desc='Open HeidiSQL or open sessions via auto-complete',
                target=distro['exe_file'],
                args_hint=kp.ItemArgsHint.ACCEPTED,
                hit_hint=kp.ItemHitHint.NOARGS,
                data_bag=kpu.kwargs_encode(
                    distro_name=distro_name
                )
            ))

        self.set_catalog(catalog)

    def on_suggest(self, user_input, initial_item, current_item):
        if not initial_item or initial_item.category() != kp.ItemCategory.KEYWORD:
            return

        suggestions = []

        data_bag = kpu.kwargs_decode(initial_item.data_bag())
        sessions = self._distros[data_bag['distro_name']]['sessions']
        for session in sessions:
            session_name = str(session).rpartition('\\')[2]
            if not user_input or kpu.fuzzy_score(user_input, session_name) > 0:
                suggestions.append(self.create_item(
                    category=kp.ItemCategory.REFERENCE,
                    label=session_name,
                    short_desc='Open "{}" with HeidiSQL'.format(session_name),
                    target=kpu.kwargs_encode(
                        distro_name=data_bag['distro_name'],
                        session=session
                    ),
                    args_hint=kp.ItemArgsHint.FORBIDDEN,
                    hit_hint=kp.ItemHitHint.IGNORE
                ))

        self.set_suggestions(suggestions, kp.Match.ANY, kp.Sort.NONE)

    def on_execute(self, item, action):
        if not item:
            return

        if item.category() == kp.ItemCategory.KEYWORD:
            kpu.shell_execute(item.target())
            return

        if item.category() != kp.ItemCategory.REFERENCE:
            return

        # extract info from item's target property
        try:
            target = kpu.kwargs_decode(item.target())
            distro_name = target['distro_name']
            session_name = target['session']
        except Exception as e:
            self.dbg(e)
            return

        # check if the desired distro is available and enabled
        if distro_name not in self._distros:
            self.warn('Could not execute item "{}". Distro "{}" not found.'.format(item.label(), distro_name))
            return
        distro = self._distros[distro_name]
        if not distro['enabled']:
            self.warn('Could not execute item "{}". Distro "{}" is disabled.'.format(item.label(), distro_name))
            return

        # check if the desired session still exists
        if session_name not in distro['sessions']:
            self.warn(
                'Could not execute item "{}". Session "{}" not found in distro "{}".'.format(item.label(), session_name,
                                                                                             distro_name))
            return

        # find the placeholder of the session name in the args list and execute
        sidx = distro['cmd_args'].index('%1')
        kpu.shell_execute(
            distro['exe_file'],
            args=distro['cmd_args'][0:sidx] + [session_name] + distro['cmd_args'][sidx + 1:])


    def on_events(self, flags):
        if flags & kp.Events.PACKCONFIG:
            self.info("Configuration changed, rebuilding catalog...")
            self.on_catalog()

    def _read_config(self):
        self._clean_icon()
        self._distros = {}

        settings = self.load_settings()
        for section_name in settings.sections():
            if not section_name.lower().startswith(self.DIST_SECTION_PREFIX):
                continue

            dist_name = section_name[len(self.DIST_SECTION_PREFIX):]

            detect_method = getattr(self, "_detect_distro_{}".format(dist_name.lower()), None)
            if not detect_method:
                self.err("Unknown HeidiSQL distribution name: ", dist_name)
                continue

            dist_path = settings.get_stripped("path", section_name)
            dist_enable = settings.get_bool("enable", section_name)

            dist_props = detect_method(
                dist_enable,
                settings.get_stripped("label", section_name),
                dist_path)

            if not dist_props:
                if dist_path:
                    self.warn('HeidiSQL distribution "{}" not found in: {}'.format(dist_name, dist_path))
                elif dist_enable:
                    self.warn('HeidiSQL distribution "{}" not found'.format(dist_name))
                continue

            self._distros[dist_name.lower()] = {
                'orig_name': dist_name,
                'enabled': dist_props['enabled'],
                'label': dist_props['label'],
                'exe_file': dist_props['exe_file'],
                'cmd_args': dist_props['cmd_args'],
                'sessions': dist_props['sessions']}

            if dist_props['enabled'] and not self._default_icon_handle:
                self._default_icon_handle = self.load_icon(
                    "@{},0".format(dist_props['exe_file']))
                if self._default_icon_handle:
                    self.set_default_icon(self._default_icon_handle)

    def _clean_icon(self):
        if self._default_icon_handle:
            self._default_icon_handle.free()
            self._default_icon_handle = None


    def _detect_distro_official(self, given_enabled, given_label, given_path):
        dist_props = {
            'enabled': given_enabled,
            'label': given_label,
            'exe_file': None,
            'cmd_args': ['-d', '%1'],
            'sessions': []}

        # label
        if not dist_props['label']:
            dist_props['label'] = "HeidiSQL"

        # enabled? don't go further if not
        if dist_props['enabled'] is None:
            dist_props['enabled'] = True
        if not dist_props['enabled']:
            return dist_props

        # find executable
        exe_file = None
        if given_path:
            exe_file = os.path.join(given_path, self.EXE_NAME_OFFICIAL)
            if not os.path.exists(exe_file):
                exe_file = None
        if not exe_file:
            exe_file = self._autodetect_startmenu(self.EXE_NAME_OFFICIAL, "HeidiSQL.lnk")
        if not exe_file:
            exe_file = self._autodetect_official_progfiles()
        if not exe_file:
            return None
        dist_props['exe_file'] = exe_file

        dist_sessions = self._registry_reader.get_sessions()
        if dist_sessions:
            dist_props['sessions'].extend(dist_sessions)

        return dist_props

    def _detect_distro_portable(self, given_enabled, given_label, given_path):
        dist_props = {
            'enabled': given_enabled,
            'label': given_label,
            'exe_file': None,
            'cmd_args': ['-d', '%1'],
            'sessions': []}

        # label
        if not dist_props['label']:
            dist_props['label'] = "HeidiSQL Portable"

        # enabled? don't go further if not
        if dist_props['enabled'] is None:
            dist_props['enabled'] = False
        if not dist_props['enabled']:
            return dist_props

        # find executable
        exe_file = None
        if given_path:
            exe_file = os.path.join(given_path, self.EXE_NAME_OFFICIAL)
            if not os.path.exists(exe_file):
                exe_file = None
        dist_props['exe_file'] = exe_file

        dist_sessions = self._settings_reader.get_sessions(given_path)
        if dist_sessions:
            dist_props['sessions'].extend(dist_sessions)

        return dist_props


    def _autodetect_official_progfiles(self):
        for hive in ('%PROGRAMFILES%', '%PROGRAMFILES(X86)%'):
            exe_file = os.path.join(
                os.path.expandvars(hive), "HeidiSQL", self.EXE_NAME_OFFICIAL)
            if os.path.exists(exe_file):
                return exe_file


    def _autodetect_startmenu(self, exe_name, name_pattern):
        known_folders = (
            "{625b53c3-ab48-4ec1-ba1f-a1ef4146fc19}",  # FOLDERID_StartMenu
            "{a4115719-d62e-491d-aa7c-e74b8be3b067}")  # FOLDERID_CommonStartMenu

        found_link_files = []
        for kf_guid in known_folders:
            try:
                known_dir = kpu.shell_known_folder_path(kf_guid)
                found_link_files += [
                    os.path.join(known_dir, f)
                    for f in kpu.scan_directory(
                        known_dir, name_pattern, kpu.ScanFlags.FILES, -1)]
            except Exception as e:
                self.dbg(e)
                pass

        for link_file in found_link_files:
            try:
                link_props = kpu.read_link(link_file)
                if (link_props['target'].lower().endswith(exe_name) and
                        os.path.exists(link_props['target'])):
                    return link_props['target']
            except Exception as e:
                self.dbg(e)
                pass

        return None