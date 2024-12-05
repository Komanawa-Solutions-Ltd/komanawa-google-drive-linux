"""
created matt_dumont
on: 17/09/23
"""
import traceback
from pathlib import Path
import subprocess
import webbrowser
from komanawa.lgdrive.path_support import google_mount_dir, mount_options_path, master_config
from komanawa.lgdrive.utils.base_functions import join_character, get_rclone_config, get_drive_export_format, \
    add_user_set_shortcode, \
    update_master_config, create_config, get_user_shortcode, read_shortcodes, write_shortcodes, check_shortcode, \
    user_authenticated, list_users, get_prebuilt_mount_options, get_user_from_shortcode, list_active_drive_mounts, \
    list_drives_available, unmount_drive, close_google_drive, mount_drive, get_email_from_mountpoint_tmux_name, \
    read_mounted_drives, _get_config_path, list_drives_in_config, read_google_client, write_google_client, \
    update_mounted_drives


class LGDrive():
    def __init__(self):
        pass

    @staticmethod
    def _get_mnt_drives(user):
        """

        :param user: None (return all mounted) or email address
        :return:
        """
        mt_drives = list_active_drive_mounts()
        if user is None:
            return mt_drives
        short_code = get_user_shortcode(user)
        mt_drives = [e for e in mt_drives if short_code in e.split(join_character)[1]]
        return mt_drives

    @staticmethod
    def _get_possible_drives(user):
        """
        list all possible drives for a given user
        :return:
        """
        users = list_users()
        assert user in users, f'{user} not in {users}'
        drives = list_drives_available(user)
        return drives

    @staticmethod
    def _get_shortcode(user):
        """
        get the shortcode for a given user
        :param user: email address
        :return:
        """
        return get_user_shortcode(user)

    @staticmethod
    def _get_users():
        users = list_users()
        return users

    def _mnt_previous_drives(self):
        """
        mount all previous drives
        :return:
        """
        drives = read_mounted_drives()
        for drive in drives:
            self.mount_drive(drive)

    def _open_in_google_drive(self, path, open=True):
        """
        opens the parent folder in google drive
        :param path: path to file or folder
        :return:
        """
        path = Path(path)
        if path.is_dir():
            pass
        else:
            path = path.parent
        gid = self.get_google_id(path)
        link = f'https://drive.google.com/drive/folders/{gid}'
        if open:
            webbrowser.open(link, new=0, autoraise=True)
        else:
            return link

    @staticmethod
    def _user_authenticated(user):
        """
        check if a user is authenticated
        :param user: email address
        :return:
        """
        users = list_users()
        assert user in users, f'{user} not in {users}'
        return user_authenticated(user)

    @staticmethod
    def add_user(user, short_code, local=False):
        """
        add the user and shortcode, update the master config, then create the config
        :param user: email address
        :param short_code: short code for the user, must be unique
        :param local: if True launch authentication in local browser, if False print link to authenticate
        :return:
        """
        success, mssage = add_user_set_shortcode(user, short_code)
        assert success, mssage
        update_master_config(add_email=user, remove_email=None, local=local)
        create_config(user)

    def change_shortcode(self, user, new_shortcode):
        """
        change the shortcode for a given user
        :param user: email address
        :param new_shortcode: new shortcode
        :return:
        """
        short_codes = read_shortcodes()
        old_shortcode = get_user_shortcode(user)
        success, mssage = check_shortcode(email=user, shortcode=new_shortcode, short_codes=short_codes)
        if success:
            short_codes[user] = new_shortcode
            write_shortcodes(short_codes)
            old_config = _get_config_path(short_code=old_shortcode)
            old_config.unlink(missing_ok=True)
            get_rclone_config(short_code=new_shortcode, recreate_config=True)
            mnted_drives = list_active_drive_mounts()
            mnted_drives = [e for e in mnted_drives if
                            old_shortcode == get_email_from_mountpoint_tmux_name(mp_name=e)[1]]
            for d in mnted_drives:
                unmount_drive(d)
            for d in mnted_drives:
                mount_drive(d.replace(old_shortcode, new_shortcode))
        else:
            raise ValueError(f'failed to change shortcode for {user} to {new_shortcode}, keeping {old_shortcode} '
                             f'instead.\nError: {mssage}')

    def get_google_client(self):
        """
        get the google client id used to manage the api calls. see https://rclone.org/drive/#making-your-own-client-id
        :return:
        """
        t = read_google_client()[0]
        print(t)
        return t

    @staticmethod
    def get_google_id(path):
        """
        get the google ID for a given path
        :param path: path to file or folder
        :return:
        """
        path = Path(path)
        path = path.relative_to(google_mount_dir)
        mount_name = path.parts[0]
        drive_nm, short_code = get_email_from_mountpoint_tmux_name(mp_name=mount_name)
        email = get_user_from_shortcode(short_code)
        rclone_config = get_rclone_config(short_code=short_code, recreate_config=False)
        mount_id = list_drives_in_config(rclone_config).get(mount_name, '')
        if str(path) == mount_name:
            if mount_id == '':
                rclone_config = get_rclone_config(short_code=mount_name.split(join_character)[1], recreate_config=True)
                mount_id = list_drives_in_config(rclone_config)[mount_name]
                if mount_id == '':
                    raise ValueError(f'failed to get google id for {path}')
            return mount_id
        path = path.relative_to(mount_name)
        parent_path = path.parent
        if str(parent_path) == '.':
            parent_path = ''
        file_name = path.name

        code = ['rclone',
                'lsjson',
                f'--drive-export-formats {get_drive_export_format()}',  # ensure constant file names
                '--config', str(master_config),
                '--no-mimetype',
                '--no-modtime',
                '--fast-list',
                ]
        if mount_id == '':
            code.append(f'{email}:{parent_path}')
        else:
            code.append(f'{email},team_drive={mount_id}:{parent_path}')
        code = ' '.join(code)
        output = subprocess.run(code, capture_output=True, shell=True)
        assert output.returncode == 0, f'failed to get google id for {path}:\n{output.stderr.decode()}'
        output = output.stdout.decode()
        output = output.split('\n')
        out_id = []
        for l in output:
            if file_name in l:
                l = l.strip(',{}')
                data = {e.split(':')[0].strip('"'): e.split(':')[1].strip('"') for e in l.split(',') if ':' in e}
                if file_name == data['Name']:
                    out_id.append(data['ID'])
        if len(out_id) == 0:
            raise ValueError(f'failed to get google id for {path}')
        elif len(out_id) > 1:
            print(out_id)
            raise ValueError(f'found more than one match for {path}: {out_id}')
        else:
            print(out_id)
            return out_id[0]

    @staticmethod
    def ls_mnt_drives():
        """
        list all mounted drives
        :return:
        """
        mt_drives = list_active_drive_mounts()
        print(f'mounted drives:\n * ' + '\n * '.join(mt_drives))

    @staticmethod
    def ls_pos_drives(user=None, short_code=None):
        """
        list all possible drives for a given user
        :return:
        """
        if user is None:
            user = get_user_from_shortcode(short_code)
        users = list_users()
        assert user is not None, 'must provide either user or short_code'
        assert user in users, f'{user} not in {users}'
        drives = list_drives_available(user)
        print(f'drives for {user}:\n * ' + '\n * '.join(drives))

    @staticmethod
    def ls_users(detailed=False):
        """
        list all users
        :param detailed: if True, print more information about the users
        :return:
        """
        users = list_users()
        if not detailed:
            print(f'users:\n * ' + '\n * '.join(users))
            return
        out = []
        for user in users:
            temp = {}
            temp['short_code'] = sc = get_user_shortcode(user)
            temp['authenticated'] = user_authenticated(user)
            mounted = [e for e in list_active_drive_mounts() if sc in e]
            temp['nmounted'] = len(mounted)
            temp['mounted'] = mounted
            temp = '\n    * ' + '\n    * '.join([f'{k}: {v}' for k, v in temp.items()])
            out.append(f'{user}: {temp}')
        out = '\n * '.join(out)
        print(f'users:\n * {out}')

    @staticmethod
    def mount_drive(drivenm):
        """
        mount a drive
        :param drivenm: drive name (shortcode + drive name) which is returned by ls_pos_drives
        :return:
        """
        mount_drive(drivenm)

    def open_glink(self, path):
        """
        opens the google drive link for a file or folder
        :param path: path to file or folder
        :return:
        """
        self._open_in_google_drive(path, open=True)

    def print_glink(self, path):
        """
        prints the google drive link for a file or folder
        :param path: path to file or folder
        :return:
        """
        link = self._open_in_google_drive(path, open=False)
        print(link)

    @staticmethod
    def reauthenticate_user(user, local=False):
        """
        re authenicate an existing user
        :param user: email address
        :param local: if True launch authentication in local browser, if False print link to authenticate
        :return:
        """
        users = list_users()
        assert user in users, f'{user} not in {users}'
        if user_authenticated(user):
            pass
        else:
            update_master_config(add_email=user, remove_email=None, local=local)
        create_config(user)

    @staticmethod
    def recreate_all_configs():
        """
        recreate all configs, re-run to get all drives and at start of each session
        :return:
        """
        users = list_users()
        all_success = True
        errors = {}
        for user in users:
            print(f'creating configs for {user}')
            if not user_authenticated(user):
                continue
            try:
                create_config(user)
            except Exception:
                success = False
                message = traceback.format_exc()
                all_success = False
                errors[user] = message
        assert all_success, ('errors in creating configs:\n' + ' * '
                             + '\n * '.join([f'{k}: {v}' for k, v in errors.items()]))

    def rm_all_users(self):
        """
        remove all users
        :return:
        """
        users = list_users()
        for user in users:
            self.rm_user(user)
        master_config.unlink(missing_ok=True)

    @staticmethod
    def rm_user(user):
        """
        remove the user and shortcode, update the master config, then delete the user specific config
        :param user: email address
        :return:
        """
        _get_config_path(email_address=user).unlink(missing_ok=True)
        update_master_config(add_email=None, remove_email=user)
        shortcodes = read_shortcodes()
        ushort_code = shortcodes.pop(user)
        all_mnts = list_active_drive_mounts()
        mnts = [e for e in all_mnts if ushort_code == e.split(join_character)[1]]
        for mnt in mnts:
            unmount_drive(mnt)
        write_shortcodes(shortcodes)

    def set_google_client(self, client_id, client_secret):
        """
        set the google client id
        see https://github.com/Komanawa-Solutions-Ltd/google_drive_linux#google-client-id-and-secret
        for more information
        :param client_id: google client id
        :param client_secret: google client secret
        :return:
        """
        write_google_client(client_id, client_secret)
        update_master_config(add_email=None, remove_email=None, local=True)
        self.recreate_all_configs()

    def set_mount_options(self, option_name, remount=False):
        """
        set the mount options to a prebuilt option
        :param option_name: one of the prebuilt options ('light', 'default')
        :param remount: if True, remount all drives otherwise updates will only be applied to new drives
        :return:
        """
        t = get_prebuilt_mount_options(option_name)
        mount_options_path.write_text('\n'.join(t))
        print(f'mount options set to {option_name}')
        if remount:
            self.stop_drive()
            self.start_drive()

    def start_drive(self, quick_start=False):
        """
        start google drive, this is what gets called at start of session
        :param quick_start: if True, will not recreate all configs
        :return:
        """
        if quick_start:
            try:
                self._mnt_previous_drives()
            except Exception:
                self.recreate_all_configs()
                self._mnt_previous_drives()
        else:
            self.recreate_all_configs()
            self._mnt_previous_drives()

    def stop_drive(self):
        """
        stop google drive, this is what gets called at end of session
        :return:
        """
        close_google_drive()

    def unmount_drive(self, drivenm):
        """
        unmount a drive
        :param drivenm: drive name (shortcode + drive name)
        :return:
        """
        mnts = list_active_drive_mounts()
        if drivenm in mnts:
            unmount_drive(drivenm)
        else:
            print(f'{drivenm} was not mounted')

    @staticmethod
    def _update_from_drivelist(add_drive=None, remove_drive=None):
        update_mounted_drives(add_drive=add_drive, remove_drive=remove_drive)
