# encoding=utf8
# Author: ZKeeer 2020.02.26
import sys
import re
import os
import time
import copy
import commands
from threading import Thread
from watchdog.observers import Observer
from watchdog.events import *

FileCacheList  = []
FILECACHELOCK  = False

ThreadsList = []

class FileEventHandler(FileSystemEventHandler):
    """
    preprocess file events and put to FileCacheList
    the format after process:
    """
    def __init__(self):
        FileSystemEventHandler.__init__(self)

    def on_moved(self, event):
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
            time.sleep(0.1)
        FileCacheList.append(src_path)
        if src_path not in dest_path:
            FileCacheList.append(dest_path)

    def on_created(self, event):
        global FileCacheList
        global FILECACHELOCK
        while FILECACHELOCK:
            time.sleep(0.1)
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
            time.sleep(0.1)
        FileCacheList.append(src_path)

    def on_modified(self, event):
        global FileCacheList
        global FILECACHELOCK

        if event.is_directory:
            pass
        else:
            while FILECACHELOCK:
                time.sleep(0.1)
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
        self.watch_file_sleep_time = 5
        self.sync_file_sleep_time = 1

        self.load_config(self.config_file)

        with open(self.log_file, "a") as fa:
            fa.write("")

    def load_config(self, conf_file):
        config_string = ""
        with open(conf_file, "r") as fr:
            config_string = "".join(fr.readlines())
        config_string, nums = re.subn("#.*?\n", "", config_string)  # remove comments
        print config_strings

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
        # process event delay
        tmpeventdelay = global_config_dict.get("events_delay", "default")
        self.events_delay = int(tmpeventdelay) if "default" != tmpeventdelay else 10 * self.max_process
        # process time delay
        self.time_delay = int(global_config_dict.get("time_delay", 20))

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
            os.system("mv {lf} {lf}.{tmst}".format(lf=self.log_file, tmst=time.strftime('%Y%m%d', time.localtime())))
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

    def aggregations_tree_add_node_full(self, root, filepath):
        """
        添加树节点:节点为绝对路径
        root: the root of tree
        filepath: fullpath of files, /home/zkeeer/approot/backend/test
        """
        tree = root
        level = 0
        while level < filepath.split('/').__len__()-1:
            level += 1
            file_path_split = filepath.split('/')
            current_path = '/' + '/'.join(file_path_split[1:min(level+1, len(file_path_split))])
            current_node = tree.get(current_path, {})
            if not current_node:
                tree.update({current_path: {}})
            tree.update({current_path: current_node})
            tree = current_node

    def aggregations_screen_tree_node_full(self, tree, node_list):
        # 筛选出可聚合节点：深度优先遍历树
        for cur_node in tree.keys():
            cur_node_childs = tree.get(cur_node, {})
            if cur_node_childs:
                count = cur_node_childs.keys().__len__()
                if count >= self.max_process:
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
        # 添加树节点:节点为相对路径: 可用，暂时废弃
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
            
    def aggregations_screen_tree_node(self, tree, node_list, file_path):
        # 筛选出可聚合节点：深度优先遍历树：不可用
        for item in tree.keys():
            if item == "COUNT":
                continue
            child = tree.get(item, {})
            file_path += "/"+item
            if child:
                count = child.get("COUNT", 0)
                if count >= self.max_process:
                    node_list.append(file_path)
                    return
                else:
                    self.aggregations_screen_tree_node(child, node_list, file_path)
            else:
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
        for item in file_list:
            self.aggregations_tree_add_node_full(filetree, item)
        # 1.聚合，筛选出可聚合节点，聚合策略: 统计子节点数量，当子节点数量大于等于max process时，将该节点列入可聚合节点
        self.aggregations_screen_tree_node_full(filetree, agg_notes)
        # 2.去重，(暂时没必要去重)去除被包含的节点，例如/home/zkeeer和/home/zkeeer/test中，去掉/home/zkeeer/test
        #agg_notes.sort(key=lambda item: len(item.split("/")))
        #r_agg_notes = copy.deepcopy(agg_notes)
        #r_agg_notes.reverse()
        #for item in agg_notes:
        #    for item_sub in r_agg_notes:
        #        if item in item_sub:
        #            r_agg_notes.remove(item_sub)
        #            agg_notes.remove(item_sub)
        # 3.结果 return
        return agg_notes

    def cache_list_handler(self):
        """
        未测试
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
                FILECACHELOCK = True
                try:
                    local_file_cached_list = copy.deepcopy(FileCacheList)
                    del FileCacheList[:]
                except BaseException as e:
                    self.logger(e.__str__())
                finally:
                    FILECACHELOCK = False
                # do some aggregations, trigger condition: length of FileCacheList > 10*max_process
                if len(local_file_cached_list) >= 10*self.max_process:
                    result_file_list = self.aggregations(local_file_cached_list)
                else:
                    result_file_list = local_file_cached_list
                # put result into change file list
                self.changed_file_list.extend(result_file_list)
                # clear workspace
                last_time_sync = time.time()
                del local_file_cached_list
                del result_file_list
                is_time_accessible = False
                is_events_accessible = False
            time.sleep(1)

    def sync_file(self):
        """
        sync worker: 未测试
        :return:
        """
        print("start sync file")
        while True:
            # mutex
            while self.FILE_LOCK:
                time.sleep(self.sync_file_sleep_time)
            while not self.changed_file_list:
                time.sleep(self.sync_file_sleep_time)
            self.FILE_LOCK = True
            fullpath = ""
            try:
                fullpath = self.changed_file_list.pop(0) if self.changed_file_list else False
            except BaseException as e:
                self.logger(e.__str__())
            finally:
                self.FILE_LOCK = False
            if not fullpath:
                continue
            # end mutex
            # sync
            for config in self.module_config_list:
                source_path = config.get("source", None)
                if source_path and source_path in fullpath:
                    # get relative path
                    relative_path = fullpath.replace(source_path, "./")
                    print("{} {}".format(time.ctime(), relative_path))
                    self.logger("{} {}".format(time.ctime(), relative_path))
                    rsync_command = self.make_rsync_command(relative_path, config)
                    print("{} {}".format(time.ctime(), rsync_command))
                    self.execute_command(rsync_command)

            time.sleep(self.sync_file_sleep_time)

    def make_rsync_command(self, file_path, configs):
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
        try:
            os.system(command)
            self.logger(command)
        except BaseException as args:
            self.logger(args.__str__())

    def main(self):
        """
        未测试
        :return:
        """
        global ThreadsList
        ThreadsList.append(Thread(target=self.watch_file_change_new))
        ThreadsList.append(Thread(target=self.cache_list_handler))
        for index in range(self.max_process):
            ThreadsList.append(Thread(target=self.sync_file))

        for item in ThreadsList:
            item.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            sys.exit(0)

        #for item in ThreadsList:
        #    item.join()

if __name__ == '__main__':
    psync = Psyncd()
    psync.main()

