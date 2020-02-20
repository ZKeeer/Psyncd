import re
import os
import time
from threading import Thread
from watchdog.observers import Observer
from watchdog.events import *

FileChangeList = []
FileDeleteList = []  #lazy delete
FILEDELETELOCK = False

class FileEventHandler(FileSystemEventHandler):
    def __init__(self):
        FileSystemEventHandler.__init__(self)

    def on_moved(self, event):
        if event.is_directory:
            file_string = "directory#moveto#{}".format(event.dest_path)
        else:
            file_string = "file#moveto#{}".format(event.dest_path)
        if file_string not in FileChangeList:
            FileChangeList.append(file_string)

    def on_created(self, event):
        if event.is_directory:
            file_string = "directory#created#{0}".format(event.src_path)
        else:
            file_string = "file#created#{0}".format(event.src_path)
        if file_string not in FileChangeList:
            FileChangeList.append(file_string)

    def on_deleted(self, event):
        if event.is_directory:
            file_string = "directory#deleted#{0}".format(event.src_path)
        else:
            file_string = "file#deleted#{0}".format(event.src_path)
        if file_string not in FileDeleteList:
            while FILEDELETELOCK:
                time.sleep(0.1)
            FILEDELETELOCK = True
            FileDeleteList.append(file_string)
            FILEDELETELOCK = False

    def on_modified(self, event):
        if event.is_directory:
            file_string = "directory#modified#{0}".format(event.src_path)
        else:
            file_string = "file#modified#{0}".format(event.src_path)
            if file_string not in FileChangeList:
                FileChangeList.append(file_string)


class Psyncd:
    def __init__(self):
        self.config_file = "./Psyncd.conf"
        self.FILE_LOCK = False
        self.log_file = None
        self.max_process = 5
        self.module_config_list = []
        self.changed_file_list = []
        self.rsync_command_list = []
        self.watch_file_sleep_time = 10
        self.sync_file_sleep_time = 0.5

        self.load_config(self.config_file)

        with open(self.log_file, "a") as fa:
            fa.write("")

    def load_config(self, conf_file):
        config_string = ""
        with open(conf_file, "r") as fr:
            config_string = "".join(fr.readlines())
        config_string, nums = re.subn("#.*?\n", "", config_string)  # remove comments

        global_config_string = re.findall("\[global\]\s+([^\[]*)", config_string)[0]
        module_configs = re.findall("\[module\]\s+([^\[]*)", config_string)

        # parser global config
        global_config_dict = {}
        for item in global_config_string.strip().split("\n"):
            if "=" in item:
                key, vaule = item.split("=")
                global_config_dict.update({key.strip(): vaule.strip()})
        self.log_file = global_config_dict.get("log_file", "")
        self.max_process = int(global_config_dict.get("max_process", 5))
        # parser module config
        for module_item in module_configs:
            tmp_dict = {}
            tmp_dict.update(global_config_dict)
            for item in module_item.split("\n"):
                if "=" in item:
                    key, value = item.split("=")
                    tmp_dict.update({key.strip(): value.strip()})
            self.module_config_list.append(tmp_dict)
        # init record file (temporary)

    def logger(self, log_string):
        if os.path.getsize(self.log_file) >= 100000000:
            os.system("mv {} {}.{}".format(self.log_file, self.log_file, time.strftime('%Y%m%d', time.localtime())))
        with open(self.log_file, "a") as fa:
            fa.write("{} {}\n".format(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()), log_string))

    def watch_file_change_new(self):
        print("start watch file new")
        threads_list = []
        for module in self.module_config_list:
            source_path = module.get("source", None)
            observer = Observer()
            event_handler = FileEventHandler()
            observer.schedule(event_handler, source_path, True)
            threads_list.append(observer)

        for item in threads_list:
            item.start()

        for item in threads_list:
            item.join()

    def get_relative_path(self, FileChangeList_item, root_path):
        """
        just for sync_file function
        :param FileChangeList_item:file#created#/home/zkeeer/test.txt
        :param root_path: /home/zkeeer/
        :return: filename
        """
        ftype, action, filename = FileChangeList_item.split("#")
        # get relative path
        if action == "moveto":
            filename = filename.replace(root_path, "./")
            return filename
        elif action == "created":
            filename = filename.replace(root_path, "./")
            return filename
        elif action == "deleted":
            filename = filename.replace(root_path, "./")
            filename = re.sub("/[^/]+$", "/", filename)
            return filename
        elif action == "modified":
            filename = filename.replace(root_path, "./")
            return filename
        return ""

    def sync_file(self):
        print("start sync file")
        while True:
            while self.FILE_LOCK:
                time.sleep(self.sync_file_sleep_time)
            while not FileChangeList:
                time.sleep(self.sync_file_sleep_time)
            self.FILE_LOCK = True
            FileChangeList_item = FileChangeList.pop(0) if FileChangeList else False
            self.FILE_LOCK = False
            if not FileChangeList_item:
                continue
            self.logger(FileChangeList_item)

            for item in self.module_config_list:
                source_path = item.get("source", None)
                if source_path and source_path in FileChangeList_item:
                    sync_file = self.get_relative_path(FileChangeList_item, source_path)
                    print("{} {}".format(time.ctime(), sync_file))
                    self.logger("{} {}".format(time.ctime(), sync_file))
                    rsync_command = self.make_rsync_command(sync_file, item)
                    if rsync_command not in self.rsync_command_list:
                        self.rsync_command_list.append(rsync_command)
                        print("{} {}".format(time.ctime(), rsync_command))
                        self.execute_command(rsync_command)
                        self.rsync_command_list.remove(rsync_command)

    def is_syncing(self):
        """check if is rsync process running"""
        cm_status, cm_output = commands.getstatusoutput("ps aux|grep 'rsync'")
        if cm_status == 0:
            cm_output = cm_output.split('\n')
            for item in cm_output:
                if "grep rsync" not in item and "ps aux" not in item:
                    return True
        return False

    def sync_file_delete(self):
        """sync files deleted"""
        print "start sync file(delete)"
        while True:
            # wait for file change message
            while not FileDeleteList:
                time.sleep(1)
            # wait for producter
            while FILEDELETELOCK:
                time.sleep(0.1)
            # wait for sync process
            # sync delete files after created/modified
            while self.is_syncing():
                time.sleep(1)
            # let producter wait
            FILEDELETELOCK = True
            tmplist = FileDeleteList
            FileDeleteList = []
            FILEDELETELOCK = False
            # get absolute path
            path_list = []
            for item in tmplist:
                # item : directory#deleted#filename
                # filepath : /home/zkeeer/approot/backend/test
                filepath = item.split("#")[2]
                path_split_list = filepath.split("/")
                if len(path_split_list) > 2:
                    path_split_list.pop(-1)
                tmpresult = "/"+"/".join(path_split_list)
                path_list.append(tmpresult)
            
            # get top path
            path_list.sort(key=lambda item: len(item))
            rpath_list = path_list
            rpath_list.reverse()
            for item in path_list:
                for item_sub in rpath_list:
                    if item in item_sub:
                        path_list.remove(item_sub)
                        rpath_list.remove(item_sub)
            # sync
            for path_item in path_list:
                for config_item in self.module_config_list:
                source_path = config_item.get("source", None)
                if source_path and source_path in path_item:
                    print("{} {}".format(time.ctime(), sync_file))
                    self.logger("{} {}".format(time.ctime(), sync_file))
                    rsync_command = self.make_rsync_command(sync_file, config_item)
                    print("{} {}".format(time.ctime(), rsync_command))
                    self.execute_command(rsync_command)
                    

    def make_rsync_command(self, file_path, configs: dict):
        """
        file_path: /home/zkeeer/approot/backend/test.py
        configs.source : /home/zkeeer/
        :param configs: module config dict
        :return: a shell command
        """
        # rsync
        # -azR --progress --password-file=/etc/rsync.password
        # ./approot/backend/tests.py
        # zhangke@192.168.234.129::backup

        # necessary
        rsync_binary = configs.get("rsync_binary", None)
        password_file = configs.get("password_file", None)
        source = configs.get("source", None)
        target = configs.get("target", None)
        # default
        sync_file = file_path
        default_params = "-azR"
        # options
        delete = "--delete" if configs.get("delete", "").lower() == "true" else ""
        partial = "--partial" if configs.get("partial", "").lower() == "true" else ""
        ignore_errors = "--ignore-errors" if configs.get("ignore_errors", "").lower() == "true" else ""
        trans_progress = "--progress" if configs.get("trans_progress", "").lower() == "true" else ""

        rsync_command = "{rsync_path} {default_command} " \
                        "--password-file={passwd_file} " \
                        "{delete} {partial} {ign_err} {tra_prog} " \
                        "{source} {target}".format(
            rsync_path=rsync_binary,
            default_command=default_params,
            passwd_file=password_file,
            delete=delete,
            partial=partial,
            ign_err=ignore_errors,
            tra_prog=trans_progress,
            source=sync_file,
            target=target
        )
        return "cd {} && {}".format(source, rsync_command)

    def execute_command(self, command):
        os.system(command)
        self.logger(command)

    def main(self):
        watch_file_thread = Thread(target=self.watch_file_change_new)
        # sync_file_thread = Thread(target=self.sync_file)
        sync_file_thread_list = []
        sync_file_delete_thread = Thread(target=self.sync_file_delete)
        for index in range(self.max_process):
            sync_file_thread_list.append(Thread(target=self.sync_file))

        watch_file_thread.start()
        # sync_file_thread.start()
        for item in sync_file_thread_list:
            item.start()
        sync_file_delete_thread.start()

        watch_file_thread.join()
        # sync_file_thread.join()
        for item in sync_file_thread_list:
            item.join()
        sync_file_delete_thread.join()


if __name__ == '__main__':
    psync = Psyncd()
    psync.main()

