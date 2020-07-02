# encoding=utf8
# Author: ZKeeer 2020.02.26
# MIT License
# Copyright © 2020 ZKeeer. All Rights Reserved.
# Based on the python2.7
import sys
import re
import os
import time
import copy
from threading import Thread
from watchdog.observers import Observer
from watchdog.events import *

try:
    import commands
except BaseException as args:
    import subprocess as commands


FileCacheList = []
FILECACHELOCK = False

ThreadsList = []


class FileEventHandler(FileSystemEventHandler):
    """
    preprocess file events and put to FileCacheList
    the format after process:
    """

    def __init__(self):
        FileSystemEventHandler.__init__(self)

    def on_moved(self, event):
        """
        注册文件move事件，并对结果进行简单处理，结果放入FileCachedList
        :param event:
        :return:
        """
        global FileCacheList
        global FILECACHELOCK
        src_path = event.src_path
        dest_path = event.dest_path
        # get parent path
        path_split_list = src_path.split("/")
        if len(path_split_list) > 2:
            path_split_list.pop(-1)
            tmpresult = "/".join(path_split_list) + "/"
            src_path = tmpresult
        while FILECACHELOCK:
            time.sleep(0.01)
        FileCacheList.append(src_path)
        if src_path not in dest_path:
            FileCacheList.append(dest_path)

    def on_created(self, event):
        global FileCacheList
        global FILECACHELOCK
        while FILECACHELOCK:
            time.sleep(0.01)
        FileCacheList.append(event.src_path)

    def on_deleted(self, event):
        global FileCacheList
        global FILECACHELOCK

        src_path = event.src_path
        # get parent path
        path_split_list = src_path.split("/")
        if len(path_split_list) > 2:
            path_split_list.pop(-1)
            tmpresult = "/".join(path_split_list) + "/"
            src_path = tmpresult
        while FILECACHELOCK:
            time.sleep(0.01)
        FileCacheList.append(src_path)

    def on_modified(self, event):
        global FileCacheList
        global FILECACHELOCK

        if event.is_directory:
            pass
        else:
            while FILECACHELOCK:
                time.sleep(0.01)
            FileCacheList.append(event.src_path)


class Psyncd:
    def __init__(self):
        self.config_file = "./Psyncd.conf"
        self.FILE_LOCK = False
        self.log_file = None
        self.max_process = 5
        self.module_config_list = []
        self.changed_file_list = []
        self.sync_file_list = []
        self.rsync_command_list = []

        self.stop_flag = "force_stop"

        self.load_config(self.config_file)

        with open(self.log_file, "a") as fa:
            fa.write("")

    def is_stopped(self):
        if os.path.exists(self.stop_flag):
            return True
        return False

    def clean_stop_flag(self):
        if os.path.exists(self.stop_flag):
            os.remove(self.stop_flag)

    def create_stop_flag(self):
        if not os.path.exists(self.stop_flag):
            os.system("touch %s" % self.stop_flag)

    def load_config(self, conf_file):
        """
        从Psyncd.conf加载配置
        :param conf_file:
        :return:
        """
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
        self.max_process = int(global_config_dict.get("max_process", 4))
        # process event delay
        tmpeventdelay = global_config_dict.get("events_delay", "default")
        self.events_delay = int(tmpeventdelay) if "default" != tmpeventdelay else 10 * self.max_process
        # process time delay
        self.time_delay = int(global_config_dict.get("time_delay", 60))

        # parser module config
        for module_item in module_configs:
            tmp_dict = {}
            tmp_dict.update(global_config_dict)
            for item in module_item.split("\n"):
                if "=" in item:
                    key, value = item.split("=")
                    tmp_dict.update({key.strip(): value.strip()})
            self.module_config_list.append(tmp_dict)
        # check configuration validity
        for module_item in self.module_config_list:
            # check source
            source = module_item.get("source", "")
            if source[-1] != '/':
                source += '/'
                module_item.update({"source": source})
        # init record file (temporary)

    def logger(self, log_string):
        """
        记录log并进行切割
        :param log_string:
        :return:
        """
        if os.path.getsize(self.log_file) >= 100000000:
            os.system("mv {lf} {lf}.{tmst}".format(lf=self.log_file, tmst=time.strftime('%Y%m%d', time.localtime())))
        with open(self.log_file, "a") as fa:
            fa.write("{} {}\n".format(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()), log_string))

    def aggregations_tree_add_node_full(self, root, filelist):
        """
        添加树节点:节点为绝对路径
        root: the root of tree
        filelist: list of fullpath
                  [/home/zkeeer/approot/backend/test, /home/zkeeer/app/test,....]
        """
        for filepath in filelist:
            tree = root
            file_path_split = filepath.split('/')
            file_path_depth = file_path_split.__len__()
            for level in range(1, file_path_depth):
                current_path = '/' + '/'.join(file_path_split[1:min(level + 1, len(file_path_split))])
                current_node = tree.get(current_path, {})
                if not current_node:
                    tree.update({current_path: {}})
                tree.update({current_path: current_node})
                tree = current_node

    def aggregations_screen_tree_node_full(self, tree, node_list):
        """
        筛选出可聚合节点：深度优先遍历树
        :param tree: a file tree
        :param node_list:
        :return:
        """
        for cur_node in list(tree.keys()):  # python3.6
            cur_node_childs = tree.get(cur_node, {})
            if cur_node_childs:
                count = cur_node_childs.keys().__len__()
                # if count >= self.max_process:
                if count > self.max_process:
                    node_list.append(cur_node)
                    tree.pop(cur_node)
                    continue
                self.aggregations_screen_tree_node_full(cur_node_childs, node_list)
            else:
                node_list.append(cur_node)
                tree.pop(cur_node)
                continue
        return

    def aggregations_tree_add_node_relative(self, root, filepath):
        """
        添加树节点:节点为相对路径: 可用，暂时废弃;目前使用绝对路径
        :param root:
        :param filepath:
        :return:
        """
        tree = root
        while len(filepath) > 1:
            current_path = filepath.split('/')[1]
            filepath = '/' + '/'.join(filepath.split('/')[2:])
            current_node = tree.get(current_path, {})
            if not current_node:
                tree.update({current_path: {}})
            tree.update({current_path: current_node})
            tree = current_node
            if len(filepath) == 1:
                return

    def aggregations(self, file_list):
        """
        # 聚合操作基于树，将文件结构映射为树结构
        # 然后进行聚合操作
        # 进行去重操作:暂时不用
        # 返回结果
        :param file_list:
        :return:
        """
        filetree = {}
        agg_notes = []
        # 0.构造文件树
        self.aggregations_tree_add_node_full(filetree, file_list)
        # 1.聚合，筛选出可聚合节点，聚合策略: 统计子节点数量，当子节点数量大于等于max process时，将该节点列入可聚合节点
        self.aggregations_screen_tree_node_full(filetree, agg_notes)
        # 2.去重，(暂时没必要去重)去除被包含的节点，例如/home/zkeeer和/home/zkeeer/test中，去掉/home/zkeeer/test
        agg_notes.sort(key=lambda item: len(item.split("/")))
        cagg_notes = copy.deepcopy(agg_notes)
        for index in range(len(cagg_notes)):
            for sindex in range(index + 1, len(cagg_notes)):
                if cagg_notes[index] in cagg_notes[sindex]:
                    agg_notes[sindex] = None
        agg_notes = [item for item in agg_notes if item]
        # 3.结果 return
        # clean memory before return
        del filetree
        del cagg_notes
        return agg_notes

    def cache_list_handler(self):
        """
        从FileCachedList获取改动的文件，进行聚合和去重
        :return:
        """
        global FileCacheList
        global FILECACHELOCK
        last_time_sync = time.time()
        is_time_accessible = False
        is_events_accessible = False
        while True:
            # time delay
            if (time.time() - last_time_sync) >= self.time_delay:
                is_time_accessible = True
            # events delay
            if len(FileCacheList) >= self.events_delay:
                is_events_accessible = True
            # check conditions
            if (is_time_accessible and len(FileCacheList) > 0) or is_events_accessible:
                # get files cached
                local_file_cached_list = []
                result_file_list = []
                try:
                    FILECACHELOCK = True
                    local_file_cached_list = copy.deepcopy(FileCacheList)
                    del FileCacheList[:]
                    FILECACHELOCK = False
                except BaseException as e:
                    self.logger("ERROR: Psyncd.cache_list_handler FileCacheList:" + e.__str__())
                finally:
                    FILECACHELOCK = False
                # do some aggregations, trigger condition: length of FileCacheList > 10*max_process
                if len(local_file_cached_list) >= (10 * self.max_process):
                    result_file_list = self.aggregations(local_file_cached_list)
                else:
                    local_file_cached_list.sort(key=lambda item: len(item.split('/')))
                    result_file_list = copy.deepcopy(local_file_cached_list)
                    # 去重
                    for index in range(len(local_file_cached_list)):
                        for sindex in range(index + 1, len(local_file_cached_list)):
                            if local_file_cached_list[index] in local_file_cached_list[sindex]:
                                result_file_list[sindex] = None
                result_file_list = [item for item in result_file_list if item]
                # construct sync command and put into rsync command list
                for fullpath in result_file_list:
                    for config in self.module_config_list:
                        source_path = config.get("source", None)
                        if source_path.endswith("/"):
                            source_path = source_path[:-1]
                        if source_path and source_path+'/' in fullpath:
                            # get relative path
                            relative_path = fullpath.replace(source_path, "./").replace("//", "/")
                            # self.logger(relative_path)
                            rsync_command = self.make_rsync_command(relative_path, config)
                            if rsync_command not in self.rsync_command_list:
                                self.rsync_command_list.append(rsync_command)
                # clear workspace
                last_time_sync = time.time()
                del local_file_cached_list
                del result_file_list
                is_time_accessible = False
                is_events_accessible = False

            time.sleep(1)
            if self.is_stopped():
                break

    def make_rsync_command(self, file_path, configs):
        """
        构造rsync命令
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
        default_params = "-aR"
        # options
        delete = "--delete" if configs.get("delete", "").lower() == "true" else ""
        partial = "--partial" if configs.get("partial", "").lower() == "true" else ""
        ignore_errors = "--ignore-errors" if configs.get("ignore_errors", "").lower() == "true" else ""
        trans_progress = "--progress" if configs.get("trans_progress", "").lower() == "true" else ""
        compress = "--compress" if configs.get("compress", "").lower() == "true" else ""
        password_file = "--password-file={}".format(password_file) if password_file else ""

        rsync_command = "{rsync_path} {default_command} " \
                        "{passwd_file} " \
                        "{delete} {partial} {ign_err} {tra_prog} {compress} " \
                        "{source} {target} ".format(
            rsync_path=rsync_binary,
            default_command=default_params,
            passwd_file=password_file,
            delete=delete,
            partial=partial,
            ign_err=ignore_errors,
            tra_prog=trans_progress,
            compress=compress,
            source=sync_file,
            target=target
        )
        return "cd {} && {}".format(source, rsync_command)

    def execute_command(self):
        """
        执行shell命令
        :return:
        """
        while True:
            sleep_time = 0.001
            while not self.rsync_command_list:
                time.sleep(min(sleep_time, 1))
                sleep_time += 0.1
            command = ""
            try:
                command = self.rsync_command_list.pop(0)
                os.system(command)
                self.logger(command)
            except BaseException as args:
                if command:
                    self.logger("ERROR: Psyncd.execute_command: " + args.__str__() + command)
            if self.is_stopped():
                break

    def init_sync(self):
        """
        初始化watchdog进程之前，进行一次全量同步。
        :return:
        """
        for module in self.module_config_list:
            sync_command = self.make_rsync_command("./", module)
            try:
                os.system(sync_ommand)
                self.logger(sync_command)
            except BaseException as args:
                if sync_command:
                    self.logger("ERROR: Psyncd.execute_command: " + args.__str__() + sync_command)


    def main(self):
        """
        Psyncd主程，注册各种工作线程
        :return:
        """
        if self.is_stopped():
            self.clean_stop_flag()
        threads_list = []
        # start cache file handler thread
        threads_list.append(Thread(target=self.cache_list_handler))
        # start rsync job threads
        for index in range(self.max_process):
            threads_list.append(Thread(target=self.execute_command))
        #  Initialize full synchronization
        self.init_sync()
        # start watchdog threads
        sources = []
        for module in self.module_config_list:
            tmpsource = module.get("source", None)
            if tmpsource and tmpsource not in sources:
                sources.append(tmpsource)
        for source_path in sources:
            observer = Observer()
            event_handler = FileEventHandler()
            observer.schedule(event_handler, source_path, True)
            threads_list.append(observer)
        # setDaemon
        for item in threads_list:
            item.setDaemon(True)
        # start threads
        for item in threads_list:
            item.start()

        # kill threads by Ctrl+C
        try:
            while True:
                time.sleep(1)
                if self.is_stopped():
                    break
        except KeyboardInterrupt as args:
            print "Exit Psyncd!"
        finally:
            self.create_stop_flag()
            sys.exit(0)


if __name__ == '__main__':
    psync = Psyncd()
    psync.main()

