# Psyncd
## Psyncd遵循[MIT协议](https://github.com/ZKeeer/Psyncd/blob/master/LICENSE)，所有添加到Psyncd的代码也将遵循[MIT协议](https://github.com/ZKeeer/Psyncd/blob/master/LICENSE)
#### Psyncd介绍：
Psyncd是一款类似于Lsyncd的文件同步工具，开发语言是python，原理是基于inotify对文件改动事件的监控，然后封装rsync命令进行同步。

Psyncd采用time delay和events delay机制，这两个参数对于海量小文件比较友好，可以对海量小文件进行聚合，避免使用inotify+rsync时海量文件造成频繁切换线程造成cpu负载增加，吃不满带宽。

Psyncd也可以监控到单个小文件改动，进行单个文件的精确推送，避免增加系统负载。

Psyncd可以同时监控百万级文件，推送十几个target。（参考目前的测试效果）

Psyncd文件改动事件的监控依赖于watchdog（其中watchdog的依赖，可以参考watchdog项目），watchdog封装了inotify和pathtools等，是python开发的一个文件事件监控库。

**Psyncd开发和测试环境是python2.7**，python3.5只进行过简单测试（50G/70W+ 文件） 。

#### 欢迎Pull Request

Psyncd是个小工具，文件结构并不复杂，读起来也不难，欢迎大家下载测试并提issue和pr。

如果要提pr，请附赠至少三例测试用例，不必附赠具体测试结果，只需体现是否正常。测试用例要覆盖代码改动所涉及flow的本环节，上下环节。

有好的想法欢迎跟我交流，可以通过我的邮箱联系到我。

---
#### 如何使用：

0.请预先安装pathtools=0.1.1和watchdog=0.10.2，可以直接使用pip安装。使用源码安装时，进入目录，执行"python setup.py install"即可。

1.下载本软件，使用命令"python psyncd.py"即可，记得执行命令前完成第二步的配置文件

2.如何写配置文件，在Psyncd.conf中已经写得很清楚的，请详细阅读

3.如何停止：请使用Ctrl+C

---
#### TODO:
- [x] 优化文件聚合逻辑和去重逻辑
- [x] 兼容python2和python3
- [x] 支持本地模式和rsync daemon模式（仅push，不支持pull）
- [ ] 支持日志格式自定义
- [ ] 增加rsync其他参数的支持
- [ ] 重新封装inotify，用来替代watchdog
- [ ] 增加跨平台支持 
