<!-- https://www.drissionpage.cn/browser_control/intro -->

# 🛰️ 概述

## ✅️️ 基本逻辑

操作浏览器的基本逻辑如下：

1. 创建浏览器对象，用于启动或接管浏览器
2. 获取一个 Tab 对象
3. 使用 Tab 对象访问网址
4. 使用 Tab 对象获取标签页内需要的元素对象
5. 使用元素对象进行交互

除此以外，还能执行更为复杂的操作，如执行 js 代码、监听网络数据、下载文件等。这些在后面的章节再介绍。

**示例：** 在百度搜索 “Drissionpage”，并打印结果。

```python
# 导入
from DrissionPage import Chromium

# 连接浏览器
browser = Chromium()
# 获取标签页对象
tab = browser.latest_tab
# 访问网页
tab.get('https://www.baidu.com')
# 获取文本框元素对象
ele = tab.ele('#kw')
# 向文本框元素对象输入文本
ele.input('DrissionPage')
# 点击按钮，上两行的代码可以缩写成这样
tab('#su').click()
# 获取所有<h3>元素
links = tab.eles('tag:h3')
# 遍历并打印结果
for link in links:
    print(link.text)
```

---

## ✅️️ 浏览器对象

即`Chromium`对象，用于管理浏览器整体相关的操作。

如标签页管理、获取浏览器信息、设置整体运行参数等。

```python
from DrissionPage import Chromium

browser = Chromium()  # 创建浏览器对象
browser.set.retry_times(10)  # 设置整体运行参数
tab = browser.latest_tab  # 获取Tab对象
browser.quit()  # 关闭浏览器
```

---

## ✅️️ 标签页对象

Tab 对象从浏览器对象获取，每个 Tab 对象对应浏览器上一个实际的标签页。

大部分操作都使用 Tab 对象进行，如访问网站、调整窗口大小、监听网络等。

默认情况下每个标签页只有一个 Tab 对象，关闭单例模式后可用多个 Tab 对象同时控制一个标签页。

```python
from DrissionPage import Chromium

browser = Chromium()
tab1 = browser.latest_tab  # 获取最后激活的标签页对象
tab1.get('http://DrissionPage.cn')  # 标签页访问一个网址
tab2 = browser.new_tab('https://www.baidu.com')  # 新建一个标签页并访问网址
tab3 = browser.get_tab(title='DrissionPage')  # 按条件获取标签页对象
```

---

## ✅️️ 元素对象

元素对象`ChromiumElemet`是交互的执行者，如点击、文本输入、获取元素信息等。

元素对象可从 Tab 对象获取，也可从另一个元素对象通过内部查找或相对定位的方式获取。

### 📌 对象内部查找

Tab 对象和 元素对象都有`ele()`方法，用于在其内部查找指定元素。

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('http://DrissionPage.cn')
ele = tab.ele('text=文档')  # 获取文本为“文档”的元素
ele.click()  # 点击该元素
```

---

### 📌 相对位置查找

可先获取一个元素对象，然后以这个元素为基准定位其内部或指定相对关系的元素。

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('http://DrissionPage.cn')
ele1 = tab.ele('text=文档')  # 获取文本为“文档”的元素
ele2 = ele1.next()  # 获取ele1的后一个元素
ele2.click()  # 点击该元素
```

---

<!-- https://www.drissionpage.cn/SessionPage/intro -->

# 🛩️ 概述

`SessionPage`对象和`WebPage`对象的 s 模式，可用收发数据包的形式访问网页。

`SessionPage`是一个使用使用`Session`（requests 库）对象的页面，封装了网络连接和结果解析功能，使收发数据包也可以像操作页面一样便利。

**示例：**

获取 gitee 推荐项目第一页所有项目。

```python
# 导入
from DrissionPage import SessionPage
# 创建页面对象
page = SessionPage()
# 访问网页
page.get('https://gitee.com/explore/all')
# 在页面中查找元素
items = page.eles('t:h3')
# 遍历元素
for item in items[:-1]:
    # 获取当前<h3>元素下  的<a>元素
    lnk = item('tag:a')
    # 打印<a>元素文本和href属性
    print(lnk.text, lnk.link)
```

**输出：**

```shell
七年觐汐/wx-calendar https://gitee.com/qq_connect-EC6BCC0B556624342/wx-calendar
ThingsPanel/thingspanel-go https://gitee.com/ThingsPanel/thingspanel-go
APITable/APITable https://gitee.com/apitable/APITable
Indexea/ideaseg https://gitee.com/indexea/ideaseg
CcSimple/vue-plugin-hiprint https://gitee.com/CcSimple/vue-plugin-hiprint
william_lzw/ExDUIR.NET https://gitee.com/william_lzw/ExDUIR.NET
anolis/ancert https://gitee.com/anolis/ancert
cozodb/cozo https://gitee.com/cozodb/cozo
后面省略...
```

<!-- https://www.drissionpage.cn/download/intro -->

# ⤵️ 概述

DrissionPage 提供了强大的文件下载管理功能。

能够主动发起下载任务，也能够对浏览器触发的下载任务进行管理。

## ✅️️ `download()`方法

该方法可以主动发起下载任务，提供任务管理、多线程、大文件分块、自动重连、文件名冲突处理等功能。

页面对象、`<iframe>`元素对象均支持此方法。

此方法是封装 requests 实现的，下载时会自动同步 cookies。

**示例：**

```python
from DrissionPage import SessionPage

page = SessionPage()
page.download('https://dldir1.qq.com/qqfile/qq/TIM3.4.8/TIM3.4.8.22092.exe')
```

---

## ✅️️ 浏览器的下载任务

浏览器页面对象、`<iframe>`对象可对浏览器下载任务进行控制。

包含以下功能：

- 每个标签页对象可独立指定下载地址
- 可在下载前指定重命名文件名
- 可拦截下载任务，获取任务信息

**示例：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
mission = tab('t:a').click.to_download('tmp', 'file_name')  # 点击一个会触发下载的链接，同时设置下载路径和文件名
mission.wait()  # 等待下载结束
```

功能分解写法，效果和上面的一样：

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.set.download_path('save_path')  # 设置文件保存路径
tab.set.download_file_name('file_name')  # 设置重命名文件名
tab('t:a').click()  # 点击一个会触发下载的链接
tab.wait.download_begin()  # 等待下载开始
tab.wait.downloads_done()  # 等待下载结束
```

<!-- https://www.drissionpage.cn/advance/ini -->

# ⚙️ 配置文件的使用

本库使用 ini 文件记录浏览器或`Session`对象的启动配置。便于配置复用，免于在代码中加入繁琐的配置信息。
默认情况下，页面对象启动时自动加载文件中的配置信息。
也可以在默认配置基础上用简单的方法再次修改，再保存到 ini 文件。
也可以保存多个 ini 文件，按不同项目需要调用。

注意

- ini 文件仅用于管理启动配置，页面对象创建后再修改 ini 文件是没用的。
- 如果是接管已打开的浏览器，这些设置也没有用。
- 每次升级本库，ini 文件都会被重置，可另存到其它路径以免重置。

## ✅️️ ini 文件内容

ini 文件初始内容如下。

```ini
[paths]
download_path =
tmp_path =

[chromium_options]
address = 127.0.0.1:9222
browser_path = chrome
arguments = ['--no-default-browser-check', '--disable-suggestions-ui', '--no-first-run', '--disable-infobars', '--disable-popup-blocking', '--hide-crash-restore-bubble', '--disable-features=PrivacySandboxSettings4']
extensions = []
prefs = {'profile.default_content_settings.popups': 0, 'profile.default_content_setting_values': {'notifications': 2}}
flags = {}
load_mode = normal
user = Default
auto_port = False
system_user_path = False
existing_only = False
new_env = False

[session_options]
headers = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6) AppleWebKit/603.3.8 (KHTML, like Gecko) Version/10.1.2 Safari/603.3.8', 'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'connection': 'keep-alive', 'accept-charset': 'GB2312,utf-8;q=0.7,*;q=0.7'}

[timeouts]
base = 10
page_load = 30
script = 30

[proxies]
http =
https =

[others]
retry_times = 3
retry_interval = 2
```

---

## ✅️️ 文件位置

默认配置文件存放在 DrissionPage 库 `'_configs'` 文件夹下，文件名为 configs.ini。
用户可另存其它配置文件，或从另存的文件读取配置，但默认文件的位置和名称不会改变。

---

## ✅️️ 使用默认配置文件启动

### 📌 使用页面对象自动加载

这是默认 启动方式。

```python
from DrissionPage import Chromium

browser = Chromium()
```

---

### 📌 使用配置对象加载

这种方式一般用 于加载配置后需要进一步修改。

```python
from DrissionPage import ChromiumOptions, SessionOptions, Chromium

co = ChromiumOptions(ini_path=r'D:\setting.ini')
so = SessionOptions(ini_path=r'D:\setting.ini')

browser = Chromium(addr_or_opts=co, session_options=so)
```

---

## ✅️️ 保存/另存 ini 文件

```python
from DrissionPage import ChromiumOptions

co = ChromiumOptions()

# 修改一些设置
co.no_imgs()

# 保存到当前打开的ini文件
co.save()
# 保存到指定位置的配置文件
co.save(r'D:\config1.ini')
# 保存到默认配置文件
co.save_to_default()
```

---

## ✅️️ 在项目路径使用 ini 文件

默认 ini 文件存放在 DrissionPage 安装目录下，修改要通过代码进行，给调试带来不便。

因此，提供了一个便捷的方法把默认 ini 文件复制到当前项目文件夹，并且程序会优先使用项目文件夹下的 ini 文件进行初始化配置。

这样开发者可方便地手动更改配置。项目打包也可以直接打包而不会造成找不到文件问题。

复制到项目下的 ini 文件名为`'dp_configs.ini'`，程序会默认读取这个文件的配置。

### 📌 `configs_to_here()`

此方法放在 `DrissionPage.common` 路径中，用于把默认 ini 文件复制到当前路径，并命名为`'dp_configs.ini'`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `save_name` | `str` | `None` | 指定文件名，为`None`则命名为`'dp_configs.ini'` |

**返回：**`None`

**示例：**

在项目新建一个 py 文件，输入以下内容并运行

```python
from DrissionPage.common import configs_to_here

configs_to_here()
```

之后，项目文件夹会多出一个`'dp_configs.ini'`文件。页面对象初始化时会优先读取这个文件。

### 📌 用命令行复制

除了用`configs_to_here()`方法复制 ini 文件到项目文件夹，还可以用命令行方式复制。

在项目文件夹路径下运行以下命令即可：

```shell
dp --configs-to-here
```

效果和`configs_to_here()`一致，只是不能指定文件名。

<!-- https://www.drissionpage.cn/advance/settings -->

# ⚙️ 全局设置

有一些运行时的全局设置，可以控制程序某些行为。

## ✅️️ 使用方式

全局设置在`DrissionPage.common`路径中。

以`set_****()`的方式对属性进行设置。

设置方法会返回`Settings`类本身，所以支持链式操作。

使用方法：

```python
from DrissionPage.common import Settings

Settings.set_raise_when_wait_failed(True)  # 设置等待失败时抛出异常
Settings.set_language('en')  # 设置报错使用英文

Settings.set_raise_when_wait_failed(True).set_auto_handle_alert(True)  # 链式操作
```

---

## ✅️️ 设置项

### 📌 `set_raise_when_ele_not_found()`

设置找不到元素时，是否抛出异常。初始为`False`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | `True` | `bool`表示开或关 |

**返回：**`Settings`

---

### 📌 `set_raise_when_click_failed()`

设置点击失败时，是否抛出异常。初始为`False`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | `True` | `bool`表示开或关 |

**返回：**`Settings`

---

### 📌 `set_raise_when_wait_failed()`

设置等待失败时，是否抛出异常。初始为`False`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | `True` | `bool`表示开或关 |

**返回：**`Settings`

---

### 📌 `set_singleton_tab_obj()`

设置 Tab 对象是否使用单例模式。初始为`True`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | `True` | `bool`表示开或关 |

**返回：**`Settings`

---

### 📌 `set_cdp_timeout()`

设置 cdp 执行超时（秒），初始为`30`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `second` | `float` | 必填 | 秒数 |

**返回：**`Settings`

---

### 📌 `set_browser_connect_timeout()`

设置连接浏览器的超时时间（秒）。初始为`30`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `second` | `float` | 必填 | 秒数 |

**返回：**`Settings`

---

### 📌 `set_auto_handle_alert()`

全局的自动处理弹出设置。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `accept` | `bool` `None` | `True` | 为`None`时不自动处理，为`True`时自动接受，为`False`时自动取消。 |

**返回：**`Settings`

---

### 📌 `set_language()`

设置报错和提示信息语言。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `code` | `str` | 必填 | 可选`'zh_cn'`、`'en'` |

**返回：**`Settings`

---

### 📌 `set_suffixes_list()`

设置用于解析域名后缀的本地文件路径。

默认会连网获取，离线环境下使用内置文件，可对此属性赋值手动指定路径。

通常离线环境下打包使用时需要设置。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `path` | `str` `Path` | 必填 | 文件路径 |

**返回：**`Settings`

---

## ✅️️ 示例

此示例设置找不到元素时立刻抛出异常（如不设置返回`NoneElement`）。

可直接执行查看效果。

```python
from DrissionPage import SessionPage
from DrissionPage.common import Settings

Settings.set_raise_when_ele_not_found(True)

page = SessionPage()
page.get('https://www.baidu.com')
ele = page('#abcd')
```

**输出：**

```shell
...前面省略...
DrissionPage.errors.ElementNotFoundError:
没有找到元素。
method: ele()
args: {'locator': '#abcd'}
```

<!-- https://www.drissionpage.cn/advance/commands -->

# ⚙️ 命令行的使用

DrissionPage 提供一些便捷的命令行命令，用于基本设置，以取代有时需要的临时配置文件。

命令行主命令为`dp`，形式为：

```shell
dp 命令全称或缩写 <参数>
```

## ✅️️ 设置浏览器路径

| 全称 | 缩写 | 参数 | 说明 |
| --- | --- | --- | --- |
| --set-browser-path | -p | 浏览器路径 | 设 置配置文件中的浏览器路径 |

**示例：**

```shell
# 完整写法
dp --set-browser-path "D:\chrome\Chrome.exe"

# 简略写法
dp -p "D:\chrome\Chrome.exe"
```

## ✅️️ 设置用户数据路径

| 全称 | 缩写 | 参数 | 说明 |
| --- | --- | --- | --- |
| --set-user-path | -u | 用户数据文件夹路径 | 设置配置文件中的用户数据路径 |

**示例：**

```shell
# 完整写法
dp --set-user-path D:\chrome\user_data

# 简略写法
dp -u D:\chrome\user_data
```

## 文件到当前路径">✅️️ 复制默认 ini 文件到当前路径 | 全称 | 缩写 | 参数 | 说明 | | --- | --- | --- | --- | | --configs-to-here | -c | 无 | 复制默认配置文件到当前路径 | **示例：** ```shell # 完整写法 dp --configs-to-here # 简略写法 dp -c ``` ✅️️ 启动浏览器 此命令用于启动浏览器，等待程序接管。 | 全称 | 缩写 | 参数 | 说明 | | --- | --- | --- | --- | | --launch-browser | -l | 端口号 | 启动浏览器，传入端口号，0表示用配置文件中的值 | **示例：** ```shell # 完整写法 dp --launch-browser 9333 # 简略写法 dp -l 0 ```

<!-- https://www.drissionpage.cn/advance/errors -->

# ⚙️ 异常的使用

本节介绍 DrissionPage 中的自定义异常。

## ✅️️ 导入

各种异常放在`DrissionPage.errors`路径中。

```python
from DrissionPage.errors import *
```

## ✅️️ 异常介绍

### 📌 `ElementNotFoundError`

找不到元素时抛出。

---

### 📌 `AlertExistsError`

执行 JS 或调用通过 JS 实现的功能时，若存在未处理的弹出框则抛出。

---

### 📌 `ContextLostError`

页面被刷新后仍调用其中的元素时抛出。

---

### 📌 `ElementLostError`

元素因页面或自身被刷新而失效后，仍对其进行调用时抛出。

---

### 📌 `CDPError`

调用 cdp 方法产生异常时抛出。

---

### 📌 `PageDisconnectedError`

页面关闭或连接断开后仍调用其功能时抛出。

---

### 📌 `JavaScriptError`

JavaScript 运行错误时抛出。

---

### 📌 `NoRectError`

对没有大小和位置信息的元素获取这些信息时抛出。

---

### 📌 `BrowserConnectError`

连接浏览器出错时抛出。

---

### 📌 `NoResourceError`

浏览器元素`src()`和`save()`获取资源失败时抛出。

---

### 📌 `CanNotClickError`

---

点击元素时如元素不可点击，且设置允许抛出时抛出。

### 📌 `GetDocumentError`

获取页面文档失败时抛出

---

获取页面文档失败时抛出。

### 📌 `WaitTimeoutError`

自动等待失败，且设置允许抛出时抛出。

---

### 📌 `IncorrectURLError`

访问格式不正确的 url 时抛出。

---

### 📌 `StorageError`

操作数据时，如网站禁止操作则抛出。

---

### 📌 `CookieFormatError`

导入 cookie 时如格式不正确则抛出。

---

### 📌 `LocatorError`

传入的定位符格式不正确时抛出。

---

### 📌 `UnknownError`

发生未知错误时抛出。

<!-- https://www.drissionpage.cn/advance/accelerate -->

# ⚙️ 数据读取加速

本节演示一个能够大幅加快浏览器页面数据采集的黑科技。

## ✅️️ 示例

我们找一个比较大的页面来演示，比如网页首页：<https://www.163.com>

我们数一下这个网页内的`<a>`元素数量：

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('https://www.163.com')
print(len(tab('t:body').eles('t:a')))
```

**输出：**

```shell
1613
```

嗯，数量不少，可以看出效果。

假如现在我们的任务是打印所有链接的文本，常规做法是遍历所有元素，然后打印。

这里引入本库作者写的一个计时工具，可以标记一段代码运行时间。您也可以用其它方法计时。

```python
from DrissionPage import Chromium
from TimePinner import Pinner  # 导入计时工具

pinner = Pinner()  # 创建计时器对象
tab = Chromium().latest_tab
tab.get('https://www.163.com')

pinner.pin()  # 标记开始记录

# 获取所有链接对象并遍历
links = tab('t:body').eles('t:a')
for lnk in links:
    print(lnk.text)

pinner.pin('用时')  # 记录并打印时间
```

**输出：**

```shell
0.0

网络大过年_网易政务_网易网
网易首页
...中间省略...
不良信息举报 Complaint Center
廉正举报
用时：4.057772700001806
```

用时 4 秒。

现在，我们稍微修改一个小小的地方。

把`page('t:body').eles('t:a')`改成`page('t:body').s_eles('t:a')`，然后再执行一次。

```python
from DrissionPage import Chromium
from TimePinner import Pinner  # 导入计时工具

pinner = Pinner()  # 创建计时器对象
tab = Chromium().latest_tab
tab.get('https://www.163.com')

pinner.pin()  # 标记开始记录

# 获取所有链接对象并遍历
links = tab('t:body').s_eles('t:a')
for lnk in links:
    print(lnk.text)

pinner.pin('用时')  # 记录并打印时间
```

**输出：**

```shell
0.0

网络大过年_网易政务_网易网
网易首页
...中间省略...
不良信息举报 Complaint Center
廉正举报
用时：0.2797656000002462
```

神奇不？原来 4 秒的采集时间现在只需 0.28 秒。

---

## ✅️️ 解读

`s_eles()`与`eles()`的区别在于前者会把整个页面或动态元素转变成一个静态元素，再在其中获取下级元素或信息。

因为静态元素是纯文本的，没有各种属性、交互等消耗资源的部分，所以运行速度非常快。

作者曾经采集过一个非常复杂的页面，动态元素用时 30 秒，转静态元素就只要 0.X 秒，加速效果非常明显。

我们可以获取页面中内容容器（示例中的`<body>`），把它转换成静态元素，再在其中获取信息。

当然，静态元素没有交互功能，它只是副本，也不会影响原来的动态元素。

说明

一个页面中不用反复使用`s_ele()`，通常只要使用一次，获取最高级的容器元素或者页面对象本身的静态副本，然后在这个副本中查找元素。
反复使用的话会因为资源消耗较大导致不稳定和浪费时间。

<!-- https://www.drissionpage.cn/advance/packaging -->

# ⚙️ 打包程序

本节介绍打包程序需要注意的事项。

## ✅️️ 使用新的虚拟环境！

养成打包的良好习惯，使用新建的虚拟环境，只安装必要的库去打包，可以使打包出来的 exe 文件体积缩小。
在只安装 DrissionPage 的环境中打包出来的程序，大小约为 14M。

如果您打包出来的程序体积巨大，请尝试这个方法。

---

## ✅️️ 解决 ini 不存在报错

说明

从`v4.0.4.1`开始不存在这个报错，以下是此版本之前打包报错的解决方法。

因为程序用到 ini 文件，而打包时不会自动带上，因此直接打包是会导致运行出错。

解决办法：

- 手动带上 ini 文件，并在程序中指定路径
- 把配置信息写在程序中，不带 ini 文件

### 📌 带上 ini 文件

在程序中用相对路径方式指定 ini 文件，把 ini 文件复制到程序文件夹。

```python
from DrissionPage import Chromium, ChromiumOptions, SessionOptions

co = ChromiumOptions(ini_path=r'.\configs.ini')
so = SessionOptions(ini_path=r'.\configs.ini')
browser = Chromium(addr_or_opts=co, session_options=so)
```

可以使用`configs_to_here()`方法自动复制 ini 文件。

在项目新建一个 py 文件，输入以下内容并运行

```python
from DrissionPage.common import configs_to_here

configs_to_here()
```

之后，项目文件夹会多出一个`'dp_configs.ini'`文件。页面对象初始化时会优先读取这个文件。

把它和打包出来的可执行文件放在一起即可。

---

### 📌 不使用 ini

在程序中指定不使用 ini 文件，就不会报错。这种方法需把所有配置信息写到代码里。

```python
from DrissionPage import Chromium, ChromiumOptions, SessionOptions

co = ChromiumOptions(read_file=False)  # 不读取文件方式新建配置对象
co.set_browser_path(r'.\chrome.exe')  # 输入配置信息
so = SessionOptions(read_file=False)

browser = Chromium(addr_or_opts=co, session_options=so)
```

注意，这个时候 driver 和 session 两个参数都要输入内容，如果其中一个不需要设置可以输入`False`：

```python
browser = Chromium(addr_or_opts=co, session_or_options=False)
```

---

## ✅️️ 实用示例

通常，我会把一个绿色浏览器和打包后的 exe 文件放在一起，程序中用相对路径指向该浏览器，这样拿到别的电脑也可以正常使用。

```python
from DrissionPage import Chromium, ChromiumOptions

co = (ChromiumOptions(read_file=False)
      .set_local_port(9888)
      .set_cache_path(r'.\Chrome\chrome.exe')
      .set_user_data_path(r'.\Chrome\userData'))
browser = Chromium(addr_or_opts=co, session_options=False)
# 注意：session_or_options=False
tab = browser.latest_tab

tab.get('http://DrissionPage.cn')
```

注意以下两点，程序就会跳过读取 ini 文件：

- `ChromiumOptions()`里要设置`read_file=False`
- 如果不传入某个模式的配置（示例中为 s 模式），要在页面对象初始化时设置对应参数为`False`

<!-- https://www.drissionpage.cn/advance/tools -->

# ⚙️ 实用工具

`DrissionPage.common`路径可导入几个小工具。

## ✅️️ `make_session_ele()`

此方法用于获取页面对象、元素对象或 html 文本的静态版本，或以其为基准搜索元素。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `html_or_ele` | `str` `ChromiumElement` `ChromiumPage` `ChromiumTab` `WebPage` `MixTab` `ChromiumFrame` `ShdownRoot` | 必填 | html文本、元素或页面对象 |
| `loc` | `str` `Tuple[str, str]` | `None` | 定位元组或字符串，为`None`时不在下级查找，返回根元素 |
| `index` | `int` | `1` | 获取第几个元素，从`1`开始，可传入负数获取倒数第几个，`None`获取所有 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionElement` | `index`为数字时返回静态元素对象 |
| `SessionElementsList` | `index`为`None`时返回静态元素对象组成的列表 |

**示例：**

```python
from DrissionPage.common import make_session_ele

html = '''
<html><body><div>abc</div></body></html>
'''
ele = make_session_ele(html)
print(ele.text)
```

**输出：**

```shell
abc
```

---

## ✅️️ `get_blob()`

此方法用于获取指定 blob 资源内容。

注意

- 如果资源在异域`<iframe>`元素内，必须获取该`<iframe>`元素对象，再把该对象传入才能获取到
- 本方法只能用于获取静态的资源，流媒体不可以

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `page` | `ChromiumPage` `ChromiumTab` `WebPage` `MixTab` `ChromiumFrame` | 必填 | 该资源所在的页面对象 |
| `url` | `str` | 必填 | blob 资源 url |
| `as_bytes` | `bool` | `True` | 是否以`bytes`类型返回 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | `as_bytes`参数为`False`时以 base64 格式返回 |
| `bytes` | `as_bytes`参数为`True`时以字节数据返回 |

---

## ✅️️ `configs_to_here()`

此方法用于把默认 ini 文件复制到当前路径。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `save_name` | `str` | `None` | 指定文件名，为`None`则命名为`'dp_configs.ini'` |

**返回：** `None`

---

## ✅️️ `wait_until()`

此方法用于等待传入的方法返回值不为假。超时则抛出`TimeoutError`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `function` | `callable` | 必填 | 要执行的方法 |
| `kwargs` | `dict` | `None` | 方法参数 |
| `timeout` | `float` | `10` | 超时时间（秒） |

**返回：** `Any`

---

## ✅️️ `tree()`

此方法用于打印页面或元素结构。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `ele_or_page` | 所有页面和元素对象 | 必填 | 页面或元素对象 |
| `text` | `bool` | `False` | 是否打印元素文本 |
| `show_js` | `bool` | `False` | 打印文本时是否打印`<script>`标签内容 |
| `show_css` | `bool` | `False` | 打印文本时是否打印`<style>`标签内容 |

**返回：** `None`

---

## ✅️️ `Keys`

这是快速获取特殊按键和组合键的类。

---

## ✅️️ `By`

与 selenium 的`By`类一致，方便项目迁移。

<!-- https://www.drissionpage.cn/advance/docking -->

# ⚙️ 与其它项目对接

DrissionPage 提供 2 个小工具，用于与 selenium 和 playwright 项目对接。

可从旧项目对象中生成`ChromiumPage`对象。

注意

只支持 chromium 内核的浏览器。

## ✅️️ 与 selenium 对接

`from_selenium()`方法接收 selenium 的`WebDriver`对象，返回`ChromiumPage`对象。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `driver` | `WebDriver` | 必填 | selenium 的`WebDriver`对象 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumPage` | `ChromiumPage`对象 |

```python
from DrissionPage.common import from_selenium
from selenium.webdriver import Chrome

# 创建WebDriver对象
driver = Chrome()

# 从该WebDriver对象创建ChromiumPage对象
page = from_selenium(driver)

# 用ChromiumPage对象操作浏览器
page.get('http://DrissionPage.cn')
```

---

## ✅️️ 与 playwright 对 接

`from_playwright()`方法接收 playwright 的`Page`或`Browser`对象，返回`ChromiumPage`对象。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `page_or_browser` | `Page` `Browser` | 必填 | playwright 的`Page`或`Browser`对象 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumPage` | `ChromiumPage`对象 |

```python
from DrissionPage.common import from_playwright
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()  # 用playwright启动浏览器
    pw_page = browser.new_page()  # 创建一个新的页面

    # 从Page对象创建ChromiumPage对象
    page = from_playwright(pw_page)
    # 或 从Browser对象创建ChromiumPage对象
    page = from_playwright(browser)

    # 用ChromiumPage对象操作浏览器
    page.get("http://DrissionPage.cn")
```

<!-- https://www.drissionpage.cn/browser_control/connect_browser -->

# 🛰️ 连接浏览器

`Chromium`对象用于连接和管理浏览器。标签页的开关和获取、整体运行参数配置、浏览器信息获取等都由它进行。

根据不同的配置，可以接管已打开的浏览器，也可以启动新的浏览器。

每个浏览器只能有一个`Chromium`对象（同一进程中）。对同一个浏览器重复使用`Chromium()`获取的都是同一个对象。

Tips

程序结束时，被打开的浏览器不会主动关闭（VSCode 启动的除外），以便下次运行程序时使用。
新手在使用无头模式时需注意，程序关闭后其实浏览器进程还在，只是看不见。

## ✅️ `Chromium`初始化参数

| 初始化参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `addr_or_opts` | `str` `int` `ChromiumOptions` | `None` | 浏览器启动配置或接管信息。 传入 'ip: port' 字符串、浏览器 ws 地址、端口数字或`ChromiumOptions`对象时按配置启动或接管浏览器； 为`None`时使用配置文件配置启动浏览器 |
| `session_options` | `SessionOptions` `None` `False` | `None` | 使用双模 Tab 时使用的默认 Session 配置，为`None`使用 ini 文件配置，为`False`不从 ini 读取 |

---

## ✅️ 直接创建

### 📌 默认方式

这种方式代码最简洁，程序会使用默认配置，自动生成页面对象。

```python
from DrissionPage import Chromium

browser = Chromium()
```

创建`Chromium`对象时会在指定端口启动浏览器，或接管该端口已有浏览器。

默认情况下，程序使用 9222 端口，浏览器可执行文件路径为`'chrome'`。

如路径中没找到浏览器可执行文件，Windows 系统下程序会在注册表中查找路径。

如果都没找到，则要用下文介绍的手动配置方法。

直接创建时，程序默认读取 ini 文件配置，如 ini 文件不存在，会使用内置配置。

默认 ini 和内置配置信息详见“进阶使用->配置文件的使用”章节。

Tips

您可以修改配置文件中的配置，实现所有程序都按您的需要进行启动，详见”启动配置“章节。

---

### 📌 指定端口或地址

创建`Chromium`对象时向`addr_or_opts`参数传入端口号或地址，可接管指定端口浏览器，若端口空闲，使用默认配置在该端口启动一个浏览器。

传入端口时用`int`类型，传入地址时用`'ip:port'`格式，传入 ws 地址需为完整地址。

```python
from DrissionPage import Chromium

browser = Chromium(9333)  # 接管9333端口的浏览器，如该端口空闲，启动一个浏览器
browser = Chromium('127.0.0.1:9333')  # 与上一行一样
browser = Chromium('ws://127.0.0.1:8987/devtools/browser/3e590fc5-4587-47e1-8756-cf6784f2fef3')  # 指定ws连接
```

---

## ✅️ 通过配置信息创建

如果需要已指定方式启动浏览器，可使用`ChromiumOptions`。它是专门用于设置浏览器初始状态的类，内置了常用的配置。详细使用方法见“浏览器启动配置”一节。

### 📌 使用方法

`ChromiumOptions`用于管理创建浏览器时的配置，内置了常用的配置，并能实现链式操作。详细使用方法见“启动配置”一节。

| 初始化参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `read_file` | `bool` | `True` | 是否从 ini 文件中读取配置信息，如果为`False`则用默认配置创建 |
| `ini_path` | `str` | `None` | 文件路径，为`None`则读取默认 ini 文件 |

注意

- 配置对象只有在启动浏览器时生效。
- 浏览器创建后再修改这个配置是没有效果的。
- 接管已打开的浏览器配置也不会生效。

```python
# 导入 ChromiumOptions
from DrissionPage import Chromium, ChromiumOptions

# 创建浏览器配置对象，指定浏览器路径
co = ChromiumOptions().set_browser_path(r'D:\chrome.exe')
# 用该配置创建页面对象
browser = Chromium(addr_or_opts=co)
```

---

### 📌 使用指定 ini 文件创建

以上方法是使用默认 ini 文件中保存的配置信息创建对象，你可以保存一个 ini 文件到别的地方，并在创建对象时指定使用它。

```python
from DrissionPage import Chromium, ChromiumOptions

# 创建配置对象时指定要读取的ini文件路径
co = ChromiumOptions(ini_path=r'./config1.ini')
# 使用该配置对象创建页面
browser = Chromium(addr_or_opts=co)
```

---

## ✅️ 接管已打开的浏览器

页面对象创建时，只要指定的地址（'ip:port' 或 ws 地址）已有浏览器在运行，就会直接接管。无论浏览器是下面哪种方式启动的。

### 📌 用程序启动的浏览器

默认情况下，创建浏览器页面对象时会自动启动一个浏览器。只要这个浏览器不关闭，下次运行程序时会接管同一个浏览器继续操作（配置的 ip:port 信息不变）。

这种方式极大地方便了程序的调试，使程序不必每次重新开始，可以单独调试某个功能。

```python
from DrissionPage import Chromium

# 在9333端口启动浏览器同时创建对象，如果浏览器已经存在，则接管它
browser = Chromium(9333)
```

---

### 📌 手动打开的浏览器

如果需要手动打开浏览器再接管，可以这样做：

1. 右键点击浏览器图标，选择属性
2. 在“目标”路径后面加上 `--remote-debugging-port=端口号`（注意最前面有个空格）
3. 点击确定
4. 在程序中的浏览器配置中指定接管该端口浏览器

文件快捷方式的目标路径设置：

```text
"D:\chrome.exe" --remote-debugging-port=9333
```

程序代码：

```python
from DrissionPage import Chromium

browser = Chromium(9333)
```

注意

接管浏览器时只有`local_port`、`address`参数是有效的。

---

### 📌 bat 文件启动的浏览器

可以把上一种方式的目标路径设置写进 bat 文件（Windows系统），运行 bat 文件来启动浏览器，再用程序接管。

新建一个文本文件，在里面输入以下内容（路径改为自己电脑的）：

```shell
"D:\chrome.exe" --remote-debugging-port=9333
```

保存后把后缀改成 bat，然后双击运行就能在 9333 端口启动一个浏览器。程序代码则和上一个方法一致。

---

### 📌 用 ws 连接的远程浏览器

直接使用 ws 地址：

```python
from DrissionPage import Chromium

browser = Chromium('wss://****.com/ws?apiKey=5482a4cba773')
```

在`ChromiumOptions`设置 ws 地址：

```python
from DrissionPage import Chromium, ChromiumOptions

co = ChromiumOptions().set_address('wss://****.com/ws?apiKey=5482a4cba773')
browser = Chromium(co)
```

---

## ✅️ 多浏览器共存

如果想要同时操作多个浏览器，或者自己在使用其中一个上网，同时控制另外几个跑自动化，就需要给这些被程序控制的浏览器设置单独的 **端口** 和 **用户文件夹**，否则会造成冲突。

### 📌 指定独立端口和数据文件夹

每个要启动的浏览器使用一个独立的`ChromiumOptions`对象进行设置：

```python
from DrissionPage import Chromium, ChromiumOptions

# 创建多个配置对象，每个指定不同的端口号和用户文件夹路径
co1 = ChromiumOptions().set_local_port(9111).set_user_data_path(r'D:\data1')
co2 = ChromiumOptions().set_local_port(9222).set_user_data_path(r'D:\data2')

# 创建多个页面对象
tab1 = Chromium(addr_or_opts=co1).latest_tab
tab2 = Chromium(addr_or_opts=co2).latest_tab

# 每个页面对象控制一个浏览器
tab1.get('http://DrissionPage.cn')
tab2.get('https://www.baidu.com')
```

注意

每个浏览器都要设置独立的端口号和用户文件夹，二者缺一不可。

---

### 📌 `auto_port()`方法

`ChromiumOptions`对象的`auto_port()`方法，可以指定程序每次使用空闲的端口和临时用户文件夹创建浏览器。

使用`auto_port()`的配置对象可由多个`Chromium`对象共用，不会出现冲突。

这种方式创建的浏览器是全新不带任何数据的，并且运行数据会自动清除。

Tips

`auto_port()`支持多线程，多进程使用时由小概率出现端口冲突。
多进程使用时，可用`scope`参数指定每个进程使用的端口范围，以免发生冲突。

```python
from DrissionPage import Chromium, ChromiumOptions

co = ChromiumOptions().auto_port()

tab1 = Chromium(addr_or_opts=co).latest_tab
tab2 = Chromium(addr_or_opts=co).latest_tab

tab2.get('http://DrissionPage.cn')
tab1.get('https://www.baidu.com')
```

---

### 📌 在 ini 文件设置自动分配

可以把自动分配的配置记录到 ini 文件，这样无需创建`ChromiumOptions`，每次启动的浏览器都是独立的，不会冲突。但和`auto_port()`一样，这些浏览器也不能复用。

```python
from DrissionPage import ChromiumOptions

ChromiumOptions().auto_port(True).save()
```

这段代码把该配置记录到 ini 文件，只需运行一次，要关闭的话把参数换成`False`再执行一次即可。

```python
from DrissionPage import Chromium

tab1 = Chromium().latest_tab
tab2 = Chromium().latest_tab

tab1.get('http://DrissionPage.cn')
tab2.get('https://www.baidu.com')
```

---

## ✅️ 使用系统浏览器用户目录

初始默认配置下，程序会为每个使用的端口创建空的用户目录，并且每次接管都使用，这样可以有效避免浏览器冲突。

有些时候我们希望使用系统安装的浏览器的默认用户文件夹。以便复用用户信息和插件等。

我们可以这样设置：

### 📌 使用`ChromiumOptions`

用`ChromiumOptions`在每次启动时配置。

注意

使用这种方法时，需关闭已启动的系统浏览器，否则会连接失败。

```python
from DrissionPage import Chromium, ChromiumOptions

co = ChromiumOptions().use_system_user_path()
browser = Chromium(co)
```

---

### 📌 使用 ini 文件

把这个配置记录到 ini 文件，就不用每次使用都配置。

注意

使用这种方法时，需关闭已启动的系统浏览器，否则会连接失败。

```python
from DrissionPage import ChromiumOptions

ChromiumOptions().use_system_user_path().save()
```

---

### 📌 手动打开再接管

参考上文 “接管已打开浏览器” 的方法，手动为浏览器设置端口启动，再用 DrissionPage 接管。

```python
from DrissionPage import Chromium

browser = Chromium(9333)  # 已手动在9333端口启动浏览器
```

---

## ✅️ 创建全新的浏览器

默认情况下，程序会复用之前用过的浏览器用户数据，因此可能带有登录数据、历史记录等。

如果想打开全新的浏览器，可用以下方法：

### 📌 使用`auto_port()`

上文提过的`auto_port()`方法，会自动查找一个空闲的端口启动全新的浏览器。

示例见上文。

---

### 📌 使用`new_env()`

`ChromiumOptions`对象的`new_env()`方法，可指定启动全新的浏览器。

如果指定端口已有浏览器，会自动关闭再启动新的。

```python
from DrissionPage import Chromium, ChromiumOptions

co = ChromiumOptions().new_env()
browser = Chromium(co)
```

---

### 📌 手动指定端口和路径

给浏览器用户文件夹路径指定空的路径，以及指定一个空闲的端口，即可打开全新浏览器。

```python
from DrissionPage import Chromium, ChromiumOptions

co = ChromiumOptions().set_local_port(9333).set_user_data_path(r'C:\tmp')
browser = Chromium(co)
```

---

## ✅️ 用户文件夹位置

复用用户文件夹可使用已登录的状态、已安装的插件、已设置好的配置等。

以下不同配置下用户文件夹的存放位置。

### 📌 默认配置

默认配置下，由 DrissionPage 创建的浏览器，用户文件夹在系统临时文件夹的`DrissionPage\userData`文件夹内，以端口命名。

假如用 DrissionPage 默认配置在 9222 端口创建一个浏览器，那么用户数据就存放在`C:\Users\用户名\AppData\Local\Temp\DrissionPage\userData\9222`路径。

这个用户文件夹不会主动清除，下次再使用 9222 端口时，会继续使用。

如果使用`auto_port()`，会存放在系统临时文件夹的`DrissionPage\autoPortData`文件夹内，以端口命名。

如`C:\Users\用户名\AppData\Local\Temp\DrissionPage\autoPortData\21489`。

这个用户文件夹是临时的，用完会被主动清除。

---

### 📌 自定义位置

如果要指定用户文件夹存放位置，可用`ChromiumOptions`对象的`set_tmp_path()`方法。

也可以保持到 ini 文件，可省略每次设置。

示例：

```python
from DrissionPage import ChromiumOptions

ChromiumOptions().set_tmp_path(r'D:\tmp').save()  # 保存到ini文件
```

---

### 📌 单独指定某个用户文件夹

指定用户文件夹路径，或使用系统文件夹路径，请查看上文。

```python
from DrissionPage import Chromium, ChromiumOptions

co = ChromiumOptions().set_user_data_path(r'D:\tmp')
browser = Chromium(co)
```

```python
from DrissionPage import Chromium, ChromiumOptions

co = ChromiumOptions().use_system_user_path()
browser = Chromium(co)
```

<!-- https://www.drissionpage.cn/browser_control/browser_options -->

# 🛰️ 浏览器启动设置

浏览器的启动配置非常繁杂，本库使用`ChromiumOptions`类管理启动配置，并且内置了常用配置的设置接口。

注意

该对象只能用于浏览器的启动，浏览器启动后，再修改该配置没有任何效果。接管已打开的浏览器时，启动配置也是无效的。

## ✅️️ 创建对象

### 📌 导入

```python
from DrissionPage import ChromiumOptions
```

---

### 📌 初始化参数

`ChromiumOptions`对象用于管理浏览器初始化配置。可从配置文件中读取配置来进行初始化。

| 初始化参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `read_file` | `bool` | `True` | 是否从 ini 文件中读取配置信息，为`False`则用默认配置创建 |
| `ini_path` | `Path` `str` | `None` | 指定 ini 文件路径，为`None`则读取内置 ini 文件 |

创建配置对象：

```python
from DrissionPage import ChromiumOptions

co = ChromiumOptions()
```

默认情况下，`ChromiumOptions`对象会从 ini 文件中读取配置信息，当指定`read_file`参数为`False`时，则以默认配置创建。

提醒

对象创建时已带有默认设置，如要清除，可调用`clear_arguments()`、`clear_prefs()`等方法。

---

## ✅️️ 使用方法

创建配置对象后，可调整配置内容，然后在页面对象创建时以参数形式把配置对象传递进去，页面对象会根据配置对象的内容对浏览器进行初始化。

配置对象支持链式操作。

```python
from DrissionPage import Chromium, ChromiumOptions

# 创建配置对象（默认从 ini 文件中读取配置）
co = ChromiumOptions()
# 设置不加载图片、静音
co.no_imgs(True).mute(True)

# 以该配置创建页面对象
page = Chromium(addr_or_opts=co)
```

```python
from DrissionPage import  Chromium, ChromiumOptions

co = ChromiumOptions()
co.incognito()  # 匿名模式
co.headless()  # 无头模式
co.set_argument('--no-sandbox')  # 无沙盒模式
page = Chromium(co)
```

---

## ✅️️ 命令行参数设置

Chromium 内核浏览器有一系列的启动配置，以`--`开头，可在浏览器创建时传入，控制浏览器行为和初始状态。

启动参数非常多，详见：[List of Chromium Command Line Switches](https://peter.sh/experiments/chromium-command-line-switches/)

### 📌 `set_argument()`

此方法用于设置启动参数。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `arg` | `str` | 必填 | 启动参数名称 |
| `value` | `str` `None` `False` | `None` | 参数的值。带值的参数传入属性值，没有值的传入`None`。 如传入`False`，删除该 参数。 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

**示例：** 无值和有值的参数设置

```python
# 设置启动时最大化
co.set_argument('--start-maximized')
# 设置初始窗口大小
co.set_argument('--window-size', '800,600')
# 使用来宾模式打开浏览器
co.set_argument('--guest')
```

---

### 📌 `remove_argument()`

此方法用于在启动配置中删除一个启动参数，只要传入参数名称即可，不需要传入值。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `arg` | `str` | 必填 | 参数名称，有值的设置项传入设置名称即可 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象自身 |

**示例：** 删除无值和有值的参数设置

```python
# 删除--start-maximized参数
co.remove_argument('--start-maximized')
# 删除--window-size参数
co.remove_argument('--window-size')
```

---

### 📌 `clear_arguments()`

此方法用于清空已设置的`arguments`参数。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象自身 |

---

## ✅️️ 运行路径及端口

这部分是浏览器路径、用户文件夹路径和端口的设置。

### 📌 `set_browser_path()`

此方法用于设置浏览器可执行文件路径。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `path` | `str` `Path` | 必填 | 浏览器文件路径 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

如果传入的字符串不是浏览器可执行文件路径，则会转为使用默认路径。

---

### 📌 `set_tmp_path()`

此方法用于设置临时文件默认路径。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `path` | `str` `Path` | 必填 | 用户数据文件夹默认路径 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

---

### 📌 `set_local_port()`

此方法用于设置本地启动端口。

与`set_address()`、`auto_port()`互斥。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `port` | `str` `int` | 必填 | 端口号 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

---

### 📌 `set_address()`

此方法用于设置浏览器地址，支持 'ip:port' 格式和 ws 连接。

和`set_local_port()`、`auto_port()`互斥。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `address` | `str` | 必填 | 浏览器地址 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

---

### 📌 `auto_port()`

此方法用于设置是否使用自动分配的端口，启动一个全新的浏览器。

如果设置为`True`，程序会自动寻找一个可用端口，并在指定路径或系统临时文件夹创建一个文件夹，用于储存浏览器 数据。

由于端口和用户文件夹都是唯一的，所以用这种方式启动的浏览器不会产生冲突，但也无法多次启动程序时重复接管同一个浏览器。

`set_local_port()`、`set_address()`和`set_user_data_path()`方法，和`auto_port()`互斥，即以后调用的为准。

注意

`auto_port()`支持多线程，但不支持多进程。
多进程使用时，可用`scope`参数指定每个进程使用的端口范围，以免发生冲突。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | `True` | 是否开启自动分配端口和用户文件夹 |
| `scope` | `Tuple[int, int]` | `None` | 指定端口范围，不含最后的数字，为`None`则使用`[9600-19600)` |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

**示例：**

```python
co.auto_port(True)
```

注意

启用此功能后即会获取端口和新建临时用户数据文件夹，若此时用`save()`方法保存配置到 ini 文件，ini 文件中的设置会被该端口和文件夹路径覆盖。这个覆盖对使用并没有很大影响。

---

### 📌 `set_user_data_path()`

此方法用于设置用户文件夹路径。用户文件夹用于存储当前登陆浏览器的账号在使用浏览器时留下的痕迹，包括设置选项等。

一般来说用户文件夹的名称是 `User Data`。对于默认情况下的 Windows 中的 Chrome 浏览器来说，此文件夹位于 `%USERPROFILE%\AppData\Local\Google\Chrome\User Data\`，也就是当前系统登陆的用户目录的 `AppData` 内。实际情况可能有变，实际路径请在浏览器输入 `chrome://version/`，查阅其中的`个人资料路径`或者叫`用户配置路径`。若要使用独立的用户信息，可以将 `User Data` 目录整个复制到自定的其他位置，然后在代码中使用 `set_user_data_path()` 方法，参数填入自定义位置路径，这样便可使用独立的用户文件夹信息。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `path` | `str` `Path` | 必填 | 用户文件夹路径 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

---

### 📌 `use_system_user_path()`

此方法设置是否使用系统安装的浏览器默认用户文件夹

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | `True` | `bool`表示开关 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

---

### 📌 `set_cache_path()`

此方法用于设置缓存路径。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `path` | `str` `Path` | 必填 | 缓存路径 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

---

### 📌 `existing_only()`

此方法设置是否仅使用已 启动的浏览器，如连接目标浏览器失败，会抛出异常，不会启动新浏览器。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | `True` | `bool`表示开关 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

---

## ✅️️ 使用插件

`add_extension()`和`remove_extensions()`用于设置浏览器启动时要加载的插件。可以指定数量不限的插件。

### 📌 `add_extension()`

此方法用于添加一个插件到浏览器。

插件是临时方式加载，不会保留在用户文件夹。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `path` | `str` `Path` | 必填 | 插件路径 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

Tips

根据作者的经验，把插件文件解压到一个独立文件夹，然后把插件路径指向这个文件夹，会比较稳定。

**示例：**

```python
co.add_extension(r'D:\SwitchyOmega')
```

---

### 📌 `remove_extensions()`

此方法用于移除配置对象中保存的所有插件路径。如需移除部分插件，请移除全部后再重新添加需要的插件。

**参数：** 无

**返回：** 配置对象自身

```python
co.remove_extensions()
```

---

## ✅️️ 用户文件设置

除了启动参数，还有大量配置信息保存在浏览器的 `preferences` 文件中。

注意

`preferences` 文件是Chromium内核浏览器的配置信息文件，与 DrissionPage 的 `configs.ini` 完全不同。

以下方法用于对浏览器用户文件进行设置。

### 📌 `set_user()`

Chromium 浏览器支持多用户配置，我们可以选择使用哪一个。默认为`'Default'`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `user` | `str` | `'Default'` | 用户配置文件夹名 称 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

**示例：**

```python
co.set_user(user='Profile 1')
```

---

### 📌 `set_pref()`

此方法用于设置用户配置文件里的一个配置项。

在哪里可以查到所有的配置项？作者也没找到，知道的请告知。谢谢。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `arg` | `str` | 必填 | 设置项名称 |
| `value` | `str` | 必填 | 设置项值 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

**示例：**

```python
# 禁止所有弹出窗口
co.set_pref(arg='profile.default_content_settings.popups', value='0')
# 隐藏是否保存密码的提示
co.set_pref('credentials_enable_service', False)
```

---

### 📌 `remove_pref()`

此方法用于在当前配置对象中删除一个`pref`配置项。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `arg` | `str` | 必填 | 设置项名称 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

**示例：**

```python
co.remove_pref(arg='profile.default_content_settings.popups')
```

---

### 📌 `remove_pref_from_file()`

此方法用于在用户配置文件删除一个配置项。注意与上一个方法不一样，如果用户配置文件中已经存在某个项，用`remove_pref()`
是不能删除的，只能用`remove_pref_from_file()`删除。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `arg` | `str` | 必填 | 设置项名称 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

**示例：**

```python
co.remove_pref_from_file(arg='profile.default_content_settings.popups')
```

---

### 📌 `clear_prefs()`

此方法用于清空已设置的`prefs`参数。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象自身 |

---

## ✅️️ 运行参数设置

页面对象运行时需要用到的参数，也可以在`ChromiumOptions`中设置。

### 📌 `set_timeouts()`

此方法用于设置几种超时时间，单位为秒。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `base` | `float` | `None` | 默认超时时间，用于元素等待、alert 等待、`WebPage`的 s 模式连接等等，除以下两个参数的场景，都使用这个设置 |
| `page_load` | `float` | `None` | 页面加载超时时间 |
| `script` | `float` | `None` | JavaScript 运行超时时间 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

**示例：**

```python
co.set_timeouts(base=10)
```

---

### 📌 `set_retry()`

此方法用于设置页面连接超时时的重试次数和间隔。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `times` | `int` | `None` | 连接失败重试次数 |
| `interval` | `float` | `None` | 连接失败重试间隔（秒） |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

---

### 📌 `set_load_mode()`

此方法用于设置网页加载策略。

加载策略是指强制页面停止加载的时机，如加载完 DOM 即停止，不加载图片资源等，以提高自动化效率。

无论设置哪种策略，加载时间都不会超过`set_timeouts()`中`page_load`参数设置的时间。

加载策略：

- `'normal'`：阻塞进程，等待所有资源下载完成（默认）
- `'eager'`：DOM 就绪即停止加载
- `'none'`：网页连接成功即停止加载

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `value` | `str` | 必填 | 可接收`'normal'`、`'eager'`、`'none'` |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

**示例：**

```python
co.set_load_mode('eager')
```

---

### 📌 `set_proxy()`

该方法用于设置浏览器代理。

该设置在浏览器启动时一次性设置，设置后不能修改。且不支持带账号的代理。

如果需要运行时修改代理，或使用带账号的代理，可以用插件自行实现。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `proxy` | `str` | 必填 | 格式：协议://ip:port 当不指定协议时，默认使用 http 代理 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

**示例：**

```python
co.set_proxy('http://localhost:1080')
```

---

### 📌 `set_download_path()`

此方法用于设置下载文件保存路径。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `path` | `str` `Path` | 必填 | 下载路径 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

---

## ✅️️ 其它设置

作者将一些常用的配置封装成方法，可以直接调用。

### 📌 `headless()`

该方法用于设置是否以无界面模式启动浏览器。

如果指定端口已存在运行中的非无头浏览器，会先 关闭已有浏览器再启动新的。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | `True` | `True`和`False`表示开或关 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

**示例：**

```python
co.headless(True)
```

---

### 📌 `new_env()`

该方法用于设置是否使用全新环境创建浏览器。

如果指定端口已存在运行中的浏览器，会先关闭已有浏览器再启动新的。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | `True` | `True`和`False`表示开或关 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

---

### 📌 `set_flag()`

此方法用于设置实验项，即`'chrome://flags'`中的项目。

设置无值的项，无须设置`value`参数，否则在该参数传入要设置的值。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `flag` | `str` | 必填 | 设置项名称 |
| `value` | `str` | `None` | 设置项值 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

**示例：**

```python
from DrissionPage import ChromiumOptions

co = ChromiumOptions()
co.set_flag('temporary-unexpire-flags-m118', '1')  # 有值
co.set_flag('disable-accelerated-2d-canvas')  # 无值
```

---

### 📌 `clear_flags_in_file()`

此方法用于删除浏览器配置文件中已设置的实验项。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

---

### 📌 `clear_flags()`

此方法用于清空本对象中已设置的`flags`参数。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象自身 |

---

### 📌 `incognito()`

该方法用于设置是否以无痕模式启动浏览器。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | `True` | `True`和`False`表示开或关 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

---

### 📌 `ignore_certificate_errors()`

该方法用于设置是否忽略证书错误。可以解决访问网页时出现的“您的连接不是私密连接”、“你的连接不是专用连接”等问题。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | `True` | `True`和`False`表示开或关 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

---

### 📌 `no_imgs()`

该方法用于设置是否禁止加载图片。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | `True` | `True`和`False`表示开或关 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

**示例：**

```python
co.no_imgs(True)
```

---

### 📌 `no_js()`

该方法用于设置是否禁用 JavaScript。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | `True` | `True`和`False`表示开或关 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

**示例：**

```python
co.no_js(True)
```

---

### 📌 `mute()`

该方法用于设置是否静音。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | `True` | `True`和`False`表示开或关 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

**示例：**

```python
co.mute(True)
```

---

### 📌 `set_user_agent()`

该方法用于设置 user agent。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `user_agent` | `str` | 必填 | user agent文本 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumOptions` | 配置对象本身 |

**示例：**

```python
co.set_user_agent(user_agent='Mozilla/5.0 (Macintos.....')
```

---

## ✅️️ 保存设置到文件

ini 文件是 DrissionPage 的配置文件，持久化记载一些配置参数。您可以把不同的配置保存到各自的 ini 文件，以便适应不同的场景。

### 📌 `save()`

此方法用于保存配置项到一个 ini 文件。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `path` | `str` `Path` | `None` | ini 文件的路径， 传入`None`保存 到当前读取的配置文件 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 保存的 ini 文件绝对路径 |

**示例：**

```python
# 保存当前读取的ini文件
co.save()

# 把当前配置保存到指定的路径
co.save(path=r'D:\tmp\settings.ini')
```

---

### 📌 `save_to_default()`

此方法用于保存配置项到固定的默认 ini 文件。默认 ini 文件是指随 DrissionPage 内置的那个。

默认 ini 文件默认的路径是 Python 安装目录中的 `Lib\site-packages\DrissionPage\_configs\configs.ini`。

ini 文件初始内容点[这里](http://DrissionPage.cn/advance/ini)。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `str` | 保存的 ini 文件绝对路径 |

**示例：**

```python
co.save_to_default()
```

---

## ✅️️ `ChromiumOptions`属性

### 📌 `address`

该属性为要控制的浏览器地址，格式为 ip:port，默认为`'127.0.0.1:9222'`。

**类型：**`str`

---

### 📌 `browser_path`

该属性返回浏览器可执行文件的路径。

**类型：**`str`

---

### 📌 `user_data_path`

该属性返回用户数据文件夹路径。

**类型：**`str`

---

### 📌 `tmp_path`

该属性返回临时文件夹路径，可用于保存自动分配的用户文件夹路径。

**类型：**`str`

---

### 📌 `download_path`

该属性返回默认下载路径文件路径。

**类型：**`str`

---

### 📌 `user`

该属性返回用户配置文件夹名称。

**类型：**`str`

---

### 📌 `load_mode`

该属性返回页面加载策略。有`'normal'`、`'eager'`、`'none'`三种

**类型：**`str`

---

### 📌 `timeouts`

该属性返回超时设置。包括三种：`'base'`、`'page_load'`、`'script'`。

**类型：**`dict`

```python
print(co.timeouts)
```

**输出：**

```shell
{
    'base': 10,
    'page_load': 30,
    'script': 30
}
```

---

### 📌 `retry_times`

该属性返回连接失败时的重试次数。

**类型：**`int`

---

### 📌 `retry_interval`

该属性返回连接失败时的重试间隔（秒）。

**类型：**`float`

---

### 📌 `proxy`

该属性返回代理设置。

**类型：**`str`

---

### 📌 `arguments`

该属性以`list`形式返回浏览器启动参数。

**类型：**`list`

---

### 📌 `extensions`

该属性以`list`形式返回要加载的插件路径。

**类型：**`list`

---

### 📌 `preferences`

该属性返回用户首选项配置。

**类型：**`dict`

---

### 📌 `system_user_path`

该属性返回是否使用系统按照的浏览器的用户文件夹。

**类型：**`bool`

---

### 📌 `is_existing_only`

该属性返回是否仅使用已打开的浏览器。

**类型：**`bool`

---

### 📌 `is_auto_port`

该属性返回是否仅使用自动分配端口和用户文件夹路径。

**类型：**`bool`

---

### 📌 `is_headless`

该属性返回是否以无头模式启动浏览器。

**类型：**`bool`

<!-- https://www.drissionpage.cn/browser_control/browser_object -->

# 🛰️ 浏览器对象

我们已经了解如何创建浏览器对象，本节介绍浏览器对象的功能。

说明

文中的 “Tab 对象” 是`ChromiumTab`和`MixTab`的统称。

## ✅️️ 获取标签页对象或信息

### 📌 `get_tab()`

此方法用于获取一个标签页对象或它的 id。

`id_or_num`不为`None`时，获取`id_or_num`指定的标签页。后面几个参数无效。

`id_or_num`为`None`时，根据后面几个参数指定的条件查找标签页（与关系）。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `id_or_num` | `str` `int` | `None` | 要获取的标签页 id 或序号，序号从`1`开始，可传入负数获取倒数第几个，不是视觉排列顺序，而是激活顺序 |
| `title` | `str` | `None` | 要匹配 title 的文本，模糊匹配，为`None`则匹配所有 |
| `url` | `str` | `None` | 要匹配 url 的文本，模糊匹配，为`None`则匹配所有 |
| `tab_type` | `str` `list` `tuple` | `'page'` | 标签页类型，可用列表输入多个，如`'page'`、`'iframe'`等，为`None`则匹配所有 |
| `as_id` | `bool` | `False` | 是否返回标签页 id 而不是标签页对象 |

| 返回类型 | 说明 |
| --- | --- |
| `MixTab` | `as_id`为`False`时返回获取到的标签页对象 |
| `str` | `as_id`为`True`时返回获取到的标签页的 id |

```python
from DrissionPage import Chromium

browser = Chromium()
tab = browser.get_tab()
```

---

### 📌 `get_tabs()`

此方法用于获取多个符合条件的`MixTab`对象或它们的 id组成的列表。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `title` | `str` | `None` | 要匹配 title 的文本，模糊匹配，为`None`则匹配所有 |
| `url` | `str` | `None` | 要匹配 url 的文本，模糊匹配，为`None`则匹配所有 |
| `tab_type` | `str` `list` `tuple` | `'page'` | 标签页类型，可用列表输入多个，如`'page'`、`'iframe'`等，为`None`则匹配所有 |
| `as_id` | `bool` | `False` | 是否返回标签页 id 而不是标签页对象 |

| 返回类型 | 说明 |
| --- | --- |
| `List[MixTab]` | `as_id`为`False`时返回获取到的标签页对象组成的列表 |
| `List[str]` | `as_id`为`True`时返回获取到的标签页的 id 组成的列表 |

---

### 📌 `latest_tab`

此属性返回最新的标签页对象或 id。

- 控制本地浏览器时，返回最后激活的标签页
- 控制远程浏览器时，返回最后创建的标签页

如果关闭单例模式，即当`Settings.singleton_tab_obj`为`False`时，返回标签页的 id。

| 返回类型 | 说明 |
| --- | --- |
| `MixTab` | 单例模式时返回标签页对象 |
| `str` | 非单例模式时返回标签页 id |

---

### 📌 `tabs_count`

此属性返回标签页数量，只统计普通标签页（即`'page'`、`'webview'`类型）。

**类型：**`int`

---

### 📌 `tab_ids`

此属性返回所有标签页 id 组成的列表，只统计普通标签页（即`'page'`、`'webview'`类型）。

**类型：**`List[str]`

---

## ✅️️ 标签页操作

### 📌 `new_tab()`

此方法用于新建标签页，并返回标签页对象。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `url` | `str` | `None` | 新标签页跳转到的网址，为`None`时新建空标签页 |
| `new_window` | `bool` | `False` | 是否在新窗口打开标签页，隐身模式下无效 |
| `background` | `bool` | `False` | 是否不激活新标签页，隐身模式和访客模式及`new_window`为`True`时无效 |
| `new_context` | `bool` | `False` | 是否创建独立环境，隐身模式和访客模式下无效 |

| 返回类型 | 说明 |
| --- | --- |
| `MixTab` | 标签页对象 |

---

### 📌 `activate_tab()`

此方法用于使一个标签页显示到前端。可传入 Tab 对象、标签页 id、标签页序号。

注意标签页序号不是视觉顺序，而是激活顺序。

说明

标签页没有焦点的概念，多个标签页可以并行操作，这个方法不会对所谓焦点产生什么影响。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `id_ind_tab` | `str` `int` `ChromiumTab` `MixTab` | 必填 | 标签页 id（`str`）、Tab 对象或标签页序号（`int`），序号从`1`开始 |

**返回：**`None`

---

### 📌 `close_tabs()`

此方法用于关闭标签页。可指定多个，可关闭指定标签页以外的。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `tabs_or_ids` | `str` `ChromiumTab` `MixTab` `List|Tuple[ChromiumTab|MixTab|str]` | 必填 | 指定的标签页对象或 id，可用列表或元组传入多个 |
| `others` | `bool` | `False` | 是否关闭指定标签页之外的 |

**返回：**`None`

---

### 📌 单例模式说明

默认设置下，一个标签页只有一个 Tab 对象。

对同一个标签页反复使用`get_tab()`获取到的是同一个对象。

如上文所述，`latest_tab`获取的也是曾经生成过的 Tab 对象。

如果需要多个 Tab 对象共同管理一个标签页，可关闭单例模式：

```python
from DrissionPage.common import Settings

Settings.set_singleton_tab_obj(False)
```

关闭后，每次`get_tab()`都会创建新的 Tab 对象，`latest_tab`改成返回 Tab 对象的 id。

```python
from DrissionPage import Chromium
from DrissionPage.common import Settings

Settings.set_singleton_tab_obj(False)
browser = Chromium()
tab1 = browser.get_tab()
tab2 = browser.get_tab()
print(tab1.title, id(tab1))
print(tab2.title, id(tab2))
```

**输出：**

```shell
新标签页 2500121968848
新标签页 2500125672272
```

---

## ✅️️ 浏览器运行参数

浏览器运行设置是一些总体的运行参数。

新标签页对象会继承浏览器的运行设置，但标签页对象后再修改浏览器设置，已生成的设置也不会改变。

设置优先级：Tab 对象设置 > `Chromium`对象设置 > `Settings`设置

### 📌 `user_data_path`

此参数返回浏览器返回用户文件夹路径。

**类型：**`str`

---

### 📌 `download_path`

此参数返回浏览器返回默认下载路径。

**类型：**`str`

---

### 📌 几种超时参数

此参数返回所有超时设置，单位为秒，有`base`、`page_load`、`script`三种。

- `timeouts.base`：各种等待的基础超时设置
- `timeouts.page_load`：页面文档加载的超时设置
- `timeouts.script`：JavaScript 运行超时设置

**类型：**`float`

---

### 📌 `timeout`

此参数返回基础超时设置，单位为秒，即`timeouts.base`。

**类型：**`float`

---

### 📌 `load_mode`

此参数返回页面加载模式，包括`'none'`、`'normal'`、`'eager'`三种。

**类型：**`str`

---

## ✅️️ 浏览器运行设置

### 📌 `set.timeouts()`

此方法用于设置运行时的各种超时时间，单位为秒。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `base` | `float` | `None` | 各种等待的默认超时时间，为`None`则不修改 |
| `page_load` | `float` | `None` | 页面文档加载超时时间，为`None`则不修改 |
| `script` | `float` | `None` | 脚本运行超时时间，为`None`则不修改 |

**返回：**`None`

---

### 📌 加载模式设置

此方法用于设置页面加载模式。具体使用方法详见访问网页章节。

- `set.load_mode.normal()`：等待所有资源加载完毕的模式
- `set.load_mode.eager()`：等待文档加载完即停止加载的模式
- `set.load_mode.none()`：不会主动停止加载的模式

**返回：**`None`

---

### 📌 `set.retry_times()`

此方法用于设置页面连接失败重连次数。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `times` | `int` | 必填 | 重连次数 |

**返回：**`None`

---

### 📌 `set.retry_interval()`

此方法用于设置连接失败重连间隔（秒）。

| 参数名称 | 类 型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `interval` | `float` | 必填 | 重连间隔 |

**返回：**`None`

---

### 📌 `set.cookies()`

此方法用于设置一个或多个 cookie。

注意

用这个方法设置 cookies 记得带上`domain`属性。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `cookies` | `CookieJar` `Cookie` `list` `tuple` `str` `dict` | 必填 | 支持多种格式的 cookies 信息，一个或多个都可以 |

**返回：**`None`

---

### 📌 `set.cookies.clear()`

此方法用于清除浏览器所有 cookies。

**参数：** 无

**返回：**`None`

---

### 📌 `set.auto_handle_alert()`

此方法用于设置是否启用自动处理 alert 弹窗。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | `True` | `bool`表示开或关，传入`None`表示使用`Settings`设置 |
| `accept` | `bool` | `True` | 处理 alert 的方式，确定还是取消 |

**返回：**`None`

---

### 📌 `set.download_path()`

此方法用于设置下载文件默认保存路径。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `path` | `Path` `str` `None` | 必填 | 文件夹路径，传入`None`表示当前文件夹 |

**返回：**`None`

---

### 📌 `set.download_file_name()`

此方法用于设置下一个被下载文件的名称。

有些下载是从临时闪现的标签页触发的，这种需要由浏览器对象去捕捉和设置下载信息。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | `None` | 文件名，可不含后缀，会自动使用远程文件后缀，为`None`使用远程文件名 |
| `suffix` | `str` | `None` | 后缀名，显式设置后缀名，不使用远程文件后缀 |

**返回：**`None`

---

### 📌 `set.when_download_file_exists()`

此方法用于设置当存在同名文件时的处理方式。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `mode` | `str` | 必填 | 可在`'rename'`、`'overwrite'`、`'skip'`、`'r'`、`'o'`、`'s'`中选择 |

- `'rename'`或`'r'`：自动重命名，在文件名后加序号，如`'_1'`
- `'overwrit'`或`'o'`：覆盖已有文件
- `'skip'`或`'s'`：跳过，不下载

**返回：**`None`

---

### 📌 `set.NoneElement_value()`

此方法用于设置查找元素失败时返回的空元素是否返回设定值。详见元素查找行为章节。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `value` | `Any` | `None` | 设置的设定值 |
| `on_off` | `bool` | `True` | 是否启用 |

**返回：**`None`

---

## ✅️️ 浏览器信息

### 📌 `cookies()`

此方法以列表形式返回浏览器所有域名的 cookies，cookie 是`dict`格式。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `all_info` | `bool` | `False` | 是否返回所有内容，`False`则只返回`'name'`、`'value'`、`'domain'`三个属性 |

**返回：**`CookiesList`

除列表格式，还能以其它格式返回：

- `cookies().as_str`：以`str`格式返回，只包含`name`和`value`字段，`'name1=value1; name2=value2'`格式
- `cookies().as_dict`：以`dict`格式返回，只包含`name`和`value`字段，`{'name1': 'value1', 'name2': 'value1'}`格式
- `cookies().as_json`：把列表转换为 json 返回

---

### 📌 `process_id`

此属性返回浏览器进程 pid。

**类型：**`int`

---

### 📌 `states.is_alive`

此属性返回浏览器是否仍可用。

**类型：**`bool`

---

### 📌 `states.is_existed`

此属性返回浏览器是否接管的，而非本程序创建的。

**类型：**`bool`

---

### 📌 `states.is_headless`

此属性返回浏览器是否无头模式。

**类型：**`bool`

---

### 📌 `states.is_incognito`

此属性返回浏览器是否无痕模式。

**类型：**`bool`

---

## ✅️️ 其它浏览器行为

### 📌 `wait()`

此方法用于等待若干秒。
`scope`为`None`时，效果与`time.sleep()`没有区别，等待指定秒数。
`scope`不为`None`时，获取两个参数 之间的一个随机值，等待这个数值的秒数。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `second` | `float` | 必填 | 要等待的秒数，`scope`不为`None`时表示随机数范围起始值 |
| `scope` | `float` | `None` | 随机数范围结束值 |

| 返回类型 | 说明 |
| --- | --- |
| `Chromium` | 浏览器对象自身 |

---

### 📌 `wait.new_tab()`

此方法用于等待新标签页出现。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`则使用对象`timeout`属性 |
| `curr_tab` | `str` `ChromiumTab` `MixTab` | `None` | 指定当前最新的 Tab 对象或标签页 id，用于判断新标签页出现，为`None`自动获取 |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 等待成功返回新标签页 id |
| `False` | 等待失败返回`False` |

---

### 📌 `wait.download_begin()`

此方法用于等待浏览器下载开始。

有些下载是从临时闪现的标签页触发的，这种需要由浏览器对象去捕捉。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 超时时间（秒），`None`使用页面对象超时时间 |
| `cancel_it` | `bool` | `False` | 是否取消该任务 |

| 返回类型 | 说明 |
| --- | --- |
| `DownloadMission` | 等待成功返回下载任务对象 |
| `False` | 等待失败返回`False` |

---

### 📌 `wait.downloads_done()`

此方法用于等待所有浏览器下载任务结束。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`时无限等待 |
| `cancel_if_timeout` | `bool` | `True` | 超时时是否取消剩余任务 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否等待成功 |

---

### 📌 `clear_cache()`

此方法用于清除缓存。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `cache` | `bool` | `True` | 是否清除缓存 |
| `cookies` | `bool` | `True` | 是否清除 cookies |

**返回：**`None`

---

### 📌 `reconnect()`

此方法用于关闭与浏览器连接，并重新创建连接。

**参数：** 无

**返回：**`None`

---

### 📌 `quit()`

此方法用于关闭浏览器。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `5` | 等待浏览器关闭超时时间（秒） |
| `force` | `bool` | `False` | 是否立刻强制终止进程 |
| `del_data` | `bool` | `False` | 是否删除用户文件夹 |

**返回：**`None`

<!-- https://www.drissionpage.cn/browser_control/tabs -->

# 🛰️ 标签页管理

浏览器的标签页由 Tab 对象（`ChromiumTab`和`MixTab`）控制。

与网页的交互都由标签页对象进行。

默认情况下，一个标签页由一个 Tab 对象控制。

多个 Tab 对象可以同时操作，不需要切换焦点，也不需要激活到前台。

提醒

当禁用单例模式后，一个标签页也可以被多个 Tab 对象同时控制。

## ✅️️ 获取标签页对象

### 📌 获取最后激活的标签页

`Chromium`对象的`latest_tab`属性返回最后激活的标签页对象。

说明

如`Settings.singleton_tab_obj`为`True`，此属性返回标签页对象的 tab id。

```python
from DrissionPage import Chromium

browser = Chromium()
tab = browser.latest_tab  # 获取最新标签页对象
```

---

### 📌 获取指定标签页

`Chromium`对象的`get_tab()`和`get_tabs()`方法用于获取指定的标签页对象。

可指定标签页序号、id、标题、url、类型等条件用于检索。api 详见 “浏览器对象” 章节。

说明

- 当`id_or_num`不为`None`时，其它参数无效
- `title`、`url`和`tab_type`三个参数是与关系
- 如传入序号，序号与标签页视觉排序不一定一致，而是按照激活顺序排列。

```python
from DrissionPage import Chromium

browser = Chromium()
tab1 = browser.get_tab(1)  # 获取列表中第一个标签页的对象
tab2 = browser.get_tab('5399F4ADFE3A27503FFAA56390344EE5')  # 获取指定id的标签页对象
tab3 = browser.get_tab(url='DrissionPage.cn')  # 获取第一个url中带 'DrissionPage.cn' 的标签页对象
tabs = browser.get_tabs(url='DrissionPage.cn')  # 获取所有url中带 'DrissionPage.cn' 的标签页对象
```

注意

Tab 对象默认为单例，即一个实体标签页只有一个`MixTab`对象。`get_tab()`返回的标签页可能是同一个。

---

### 📌 新建标签页并获取对象

`Chromium`对象的`new_tab()`方法用于新建一个标签页，返回其对象。

```python
from DrissionPage import Chromium

browser = Chromium()
browser.new_tab(url='http://DrissionPage.cn')
```

说明

当传入`url`参数时，程序会根据`load_mode`设置访问页面，除了`none`模式，都将等待页面加载完毕。
如果新建多个标签页不想等待，可批量新建不传入`url`参数的标签页，再遍历使用`get()`。

---

### 📌 获取点击后出现的标签页

在预期点击元素会出现新标签页时，可用元素的`click.for_new_tab()`方法实行点击，点击后会返回新标签页对象 。

具体参数见元素交互章节。

可直接运行以下示例：

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('https://DrissionPage.cn')
ele = tab.ele('.wwads-cn wwads-horizontal').ele('tag:img')
if ele:
    tab2 = ele.click.for_new_tab()  # 点击并获取新tab对象
    tab2.set.activate()
    ele2 = tab2.ele('确认访问', timeout=5)
    if ele2:
        ele2.wait(.5).click()
else:
    print('支持开源作者，请关闭广告屏蔽功能，谢谢。')
```

元素对象的`click.middle()`方法可用中键点击`<a>`元素，可强制在新标签页打开链接，并返回新标签页对象。

可直接运行以下示例：

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('https://DrissionPage.cn')
ele = tab.ele('.wwads-cn wwads-horizontal').ele('tag:img')
if ele:
    tab2 = ele.click.middle()  # 中键点击元素，并获取新tab对象
    tab2.set.activate()
    ele2 = tab2.ele('确认访问', timeout=5)
    if ele2:
        ele2.wait(.5).click()
else:
    print('支持开源作者，请关闭广告屏蔽功能，谢谢。')
```

---

## ✅️️ 多标签页协同

这个示例在一个标签页中遍历列表元素，点击打开新标签页，获取信息后关闭。

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('https://gitee.com/explore/all')

links = tab.eles('t:h3')
for link in links[:-1]:
    # 点击链接并获取新标签页对象
    new_tab = link.click.for_new_tab()
    # 等待新标签页加载
    new_tab.wait.load_start()
    # 打印标签页标题
    print(new_tab.title)
    # 关闭新打开的标签页
    new_tab.close()
```

## ✅️️ 使用多例

默认情况下，Tab 对象是单例的，即一个标签页只有一个对象，即使重复使用`get_tab()`，获取的都是同一个对象。

这主要是防止新手不理解机制，反复创建多个连接导致资源耗费。

实际上允许多个 Tab 对象同时操作一个标签页，每个负责不同的工作。比如 一个执行主逻辑流程，另外的监视页面，处理各种弹窗。

要允许多例，可用`Settings`设置：

```python
from DrissionPage.common import Settings

Settings.set_singleton_tab_obj(False)
```

**示例**

```python
from DrissionPage import Chromium
from DrissionPage.common import Settings

browser = Chromium()
browser.new_tab()
browser.new_tab()

# 未启用多例：
tab1 = browser.get_tab(1)
tab2 = browser.get_tab(1)
print(id(tab1), id(tab2))

# 启用多例：
Settings.set_singleton_tab_obj(False)
tab1 = browser.get_tab(1)
tab2 = browser.get_tab(1)
print(id(tab1), id(tab2))
```

**输出：**

```shell
2347582903056 2347582903056
2347588741840 2347588877712
```

可见第一次输出两个 Tab 对象是同一个，第二次输出是独立的。

<!-- https://www.drissionpage.cn/browser_control/visit -->

# 🛰️ 访问网页

本节介绍 Tab 对象访问网页的相关内容。

## ✅️️ 连接方法

### 📌 `get()`

该方法用于跳转到一个网址。当连接失败时，程序会进行重试。

可指定本地文件路径。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `url` | `str` | 必填 | 目标 url，可指向本地文件路径 |
| `show_errmsg` | `bool` | `False` | 连接出错时是否显示和抛出异常 |
| `retry` | `int` | `None` | 重试次数，为`None`时使用页面参数，默认`3` |
| `interval` | `float` | `None` | 重试间隔（秒），为`None`时使用页面参数，默认`2` |
| `timeout` | `float` | `None` | 加载超时时间（秒） |
| ------- | ------- | --- | ------ 以下参数仅 s 模式有效 ------ |
| `params` | `dict` | `None` | url 请求参数 |
| `data` | `dict` `str` | `None` | 携带的数据 |
| `json` | `dict` `str` | `None` | 要发送的 JSON 数据，会自动设置 Content-Type 为`'application/json'` |
| `headers` | `dict` | `None` | 请求头 |
| `cookies` | `dict` `CookieJar` | `None` | cookies 信息 |
| `files` | `Any` | `None` | 要上传的文件，可以是一个字典，其中键是文件名，值是文件对象或文件路径 |
| `auth` | `Any` | `None` | 身份认证信息 |
| `allow_redirects` | `bool` | `True` | 是否允许重定向 |
| `proxies` | `dict` | `None` | 代理信息 |
| `hooks` | `Any` | `None` | 回调方法 |
| `stream` | `bool` | `None` | 是否使用流式传输 |
| `verify` | `bool` `str` | `None` | 是否验证 SSL 证书 |
| `cert` | `str` `Tuple[str, str]` | `None` | SSL 客户端证书文件的路径(.pem 格式)，或('cert', 'key')元组 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 访问是否成功 |

**示例：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('http://DrissionPage.cn')
```

---

### 📌 `post()`

此方法用内置的`Session`对象以 POST 方式发送请求。

因为`post()`是使用`requests`的`post()`方法发 送请求，参数和用法与`requests`一致。

此方法返回请求结果`Response`对象。

s 模式时，`post()`后结果还可用页面对象的`html`或`json`属性获取。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `url` | `str` | 必填 | 目标 url，可指向本地文件路径 |
| `show_errmsg` | `bool` | `False` | 连接出错时是否显示和抛出异常 |
| `retry` | `int` | `None` | 重试次数，为`None`时使用页面参数，默认`3` |
| `interval` | `float` | `None` | 重试间隔（秒），为`None`时使用页面参数，默认`2` |
| `timeout` | `float` | `None` | 加载超时时间（秒） |
| `params` | `dict` | `None` | url 请求参数 |
| `data` | `dict` `str` | `None` | 携带的数据 |
| `json` | `dict` `str` | `None` | 要发送的 JSON 数据，会自动设置 Content-Type 为`'application/json'` |
| `headers` | `dict` | `None` | 请求头 |
| `cookies` | `dict` `CookieJar` | `None` | cookies 信息 |
| `files` | `Any` | `None` | 要上传的文件，可以是一个字典，其中键是文件名，值是文件对象或文件路径 |
| `auth` | `Any` | `None` | 身份认证信息 |
| `allow_redirects` | `bool` | `True` | 是否允许重定向 |
| `proxies` | `dict` | `None` | 代理信息 |
| `hooks` | `Any` | `None` | 回调方法 |
| `stream` | `bool` | `None` | 是否使用流式传输 |
| `verify` | `bool` `str` | `None` | 是否验证 SSL 证书 |
| `cert` | `str` `Tuple[str, str]` | `None` | SSL 客户端证书文件的路径(.pem 格式)，或('cert', 'key')元组 |

| 返回类型 | 说明 |
| --- | --- |
| `Response` | 获取到的`Response`对象 |

---

## ✅️️ 设置超时和重试

网络不稳定时，访问页面不一定成功，`get()`方法内置了超时和重试功能。通过`retry`、`interval`、`timeout`三个参数进行设置。
其中，如不指定`timeout`参数，该参数会使用`ChromiumPage`的`timeouts`属性的`page_load`参数中的值。

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('http://DrissionPage.cn', retry=1, interval=1, timeout=1.5)
```

---

## ✅️️ 加载模式

### 📌 概述

加载模式是指 d 模式下程序在页面加载阶段的行为模式，有以下三种：

- `normal()`：常规模式，会等待页面加载完毕，超时自动重试或停止，默认使用此模式
- `eager()`：加载完 DOM 或超时即停止加载，不加载页面资源
- `none()`：超时也不会自动停止，除非加载完成

前两种模式下，页面加载过程会阻塞程序，直到加载完毕才执行后面的操作。

`none()`模式下，只在连接阶段阻塞程序，加载阶段可自行根据情况执行`stop_loading()`停止加载。

这样提供给用户非常大的自由度，可等到关键数据包或元素出现就主动停止页面加载，大幅提升执行效率。

注意

加载完成是指主文档完成，并不包括由 js 触发的加载和重定向的加载。
当文档加载完成，程序就判断加载完毕，此后发生的重定向或 js 加载数据需用其它逻辑处理。

**示例：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.set.load_mode.eager()  # 设置为eager模式
tab.get('http://DrissionPage.cn')
```

---

### 📌 模式设置

可通过 ini 文件、`ChromiumOptions`对象和页面对象的`set.load_mode.****()`方法进行设置。

运行时可随时动态设置。

**配置对象中设置**

```python
from DrissionPage import ChromiumOptions, Chromium

co = ChromiumOptions().set_load_mode('none')
browser = Chromium(co)
```

**运行中设置**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.set.load_mode.none()
```

---

### 📌 `none`模式技巧

**示例 1，配合监听器**

跟监听器配合，可在获取到需要的数据包时，主动停止加载。

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.set.load_mode.none()  # 设置加载模式为none

tab.listen.start('api/getkeydata')  # 指定监听目标并启动监听
tab.get('http://www.hao123.com/')  # 访问网站
packet = tab.listen.wait()  # 等待数据包
tab.stop_loading()  # 主动停止加载
print(packet.response.body)  # 打印数据包正文
```

**示例 2，配合元素查找**

跟元素查找配合，可在获取到某个指定元素时，主动停止加载。

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.set.load_mode.none()  # 设置加载模式为none

tab.get('http://www.hao123.com/')  # 访问网站
ele = tab.ele('中国日报')  # 查找text包含“中国日报”的元素
tab.stop_loading()  # 主动停止加载
print(ele.text)  # 打印元素text
```

**示例 2，配合页面特征**

可等待到页面到达某种状态时，主动停止加载。比如多级跳转的登录，可等待 title 变化到最终目标网址时停止。

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.set.load_mode.none()  # 设置加载模式为none

tab.get('http://www.hao123.com/')  # 访问网站
tab.wait.title_change('hao123')  # 等待title变化出现目标文本
tab.stop_loading()  # 主动停止加载
```

<!-- https://www.drissionpage.cn/browser_control/page_operation -->

# 🛰️ 页面交互

本节介绍浏览器页面交互功能。

一个 Tab 对象控制一个浏览器的标签页，是页面控制的主要单位。

## ✅️️ 页面跳转

### 📌 `get()`

详见 “访问网页” 章节。

---

### 📌 `back()`

此方法用于在浏览历史中后退若干步。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `steps` | `int` | `1` | 后退步数 |

**返回：**`None`

**示例：**

```python
tab.back(2)  # 后退两个网页
```

---

### 📌 `forward()`

此方法用于在浏览历史中前进若干步。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `steps` | `int` | `1` | 前进步数 |

**返回：**`None`

```python
tab.forward(2)  # 前进两步
```

---

### 📌 `refresh()`

此方法用于刷新当前页面。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `ignore_cache` | `bool` | `False` | 刷新时是否忽略缓存 |

**返回：**`None`

**示例：**

```python
tab.refresh()  # 刷新页面
```

---

### 📌 `stop_loading()`

此方法用于强制停止当前页面加载。

**参数：** 无

**返回：**`None`

---

### 📌 `set.blocked_urls()`

此方法用于设置忽略的连接。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `urls` | `str` `list` `tuple` `None` | 必填 | 要忽略的 url，可传入多个，可用`'*'`通配符，传入`None`时清空已设置的项 |

**返回：**`None`

**示例：**

```python
tab.set.blocked_urls('*.css*')  # 设置不加载css文件
```

---

## ✅️️ 元素管理

### 📌 `add_ele()`

此方法用于创建一个元素。可选择是否插入到 DOM。

`html_or_info`传入元素完整 html 文本时，会插入到 DOM。如`insert_to`参数为`None`，插入到`body`元素。

传入元素信息（格式：`(tag, {name: value})`）时，如`insert_to`参数为`None`，不插入到 DOM。此时返回的元素需用 js 方式点击。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `html_or_info` | `str` `Tuple[str, dict]` | 必填 | 新元素的 html 文本或信息；为`tuple`可新建不加入到 DOM 的元素 |
| `insert_to` | `str` `ChromiumElement` `Tuple[str, str]` | `None` | 插入到哪个元素中，可接收元素对象和定位符；如为`None`，`html_or_info`是`str`时添加到 body，否则不添加到 DOM |
| `before` | `str` `ChromiumElement` `Tuple[str, str]` | `None` | 在哪个子节点前面插入，可接收对象和定位符，为`None`插入到父元素末尾 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 新建的元素对象 |

**添加一个可见的元素：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('https://www.baidu.com')
html = '<a href="http://DrissionPage.cn" target="blank">DrissionPage </a> '
ele = tab.add_ele(html, '#s-top-left', '新闻')  # 插入到导航栏
ele.click()
```

**添加一个不可见的元素：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
info = ('a', {'innerText': 'DrissionPage', 'href': 'http://DrissionPage.cn', 'target': 'blank'})
ele = tab.add_ele(info)
ele.click('js')  # 需用js点击
```

---

### 📌 `remove_ele()`

此方法用于从页面上删除一个元素。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `loc_or_ele` | `str` `Tuple[str, str]` `ChromiumElement` | 必填 | 要删除的元素，可以是元素或定位符 |

**返回：**`None`

**示例：**

```python
# 删除一个已获得的元素
ele = tab('tag:a')
tab.remove_ele(ele)

# 删除用定位符找到的元素
tab.remove_ele('tag:a')
```

---

## ✅️️ 执行脚本或命令

### 📌 `run_js()`

此方法用于执行 js 脚本。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `script` | `str` | 必填 | js 脚本文本或脚本文件路径 |
| `*args` | - | 无 | 传入的参数，按顺序在js文本中对应`arguments[0]`、`arguments[1]`... |
| `as_expr` | `bool` | `False` | 是否作为表达式运行，为`True`时`args`参数无效 |
| `timetout` | `float` | `None` | js 超时时间（秒），为`None`则使用页面`timeouts.script`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `Any` | 脚本执行结果 |

**示例：**

```python
# 用传入参数的方式执行 js 脚本显示弹出框显示 Hello world!
tab.run_js('alert(arguments[0]+arguments[1]);', 'Hello', ' world!')
```

注意

- 如果`as_expr`为`True`，脚本应是返回一个结果的形式，并且不能有`return`
- 如果`as_expr`不为`True'，脚本应尽量写成一个方法。

---

### 📌 `run_js_loaded()`

此方法用于运行 js 脚本，执行前等待页面加载完毕。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `script` | `str` | 必填 | js 脚本文本 |
| `*args` | - | 无 | 传入的参数，按顺序在js文本中对应`arguments[0]`、`arguments[1]`... |
| `as_expr` | `bool` | `False` | 是否作为表达式运行，为`True`时`args`参数无效 |
| `timetout` | `float` | `None` | js 超时时间（秒），为`None`则使用页面`timeouts.script`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `Any` | 脚本执行结果 |

---

### 📌 `run_async_js()`

此方法用于以异步方式执行 js 代码。

**参数：**

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `script` | `str` | 必填 | js 脚本文本 |
| `*args` | - | 无 | 传入的参数，按顺序在js文本中对应`arguments[0]`、`arguments[1]`... |
| `as_expr` | `bool` | `False` | 是否作为表达式运行，为`True`时`args`参数无效 |

**返回：**`None`

---

### 📌 `run_cdp()`

此方法用于执行 Chrome DevTools Protocol 语句。

cdp 用法详见 [Chrome DevTools Protocol](https://chromedevtools.github.io/devtools-protocol/)。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `cmd` | `str` | 必填 | 协议项目 |
| `**cmd_args` | - | 无 | 项目参数 |

| 返回类型 | 说明 |
| --- | --- |
| `dict` | 执行返回的结果 |

**示例：**

```python
# 停止页面加载
tab.run_cdp('Page.stopLoading')
```

---

### 📌 `run_cdp_loaded()`

此方法用于执行 Chrome DevTools Protocol 语句，执行前先确保页面加载完毕。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `cmd` | `str` | 必填 | 协议项目 |
| `**cmd_args` | - | 无 | 项目参数 |

| 返回类型 | 说明 |
| --- | --- |
| `dict` | 执行返回的结果 |

---

## ✅️️ cookies 及缓存

### 📌 `set.cookies()`

此方法用于设置 cookie。可设置一个或多个。

设置一个 cookie 支持的格式：

- `Cookie`：单个`Cookie`对象
- `str`：`'name=value; domain=****; ...'`或`'name=****; value=****; domain=****; ...'`格式，只支持用`';'`分隔
- `dict`：`{'name': '****', 'value': '****', 'domain': '****', ...}`或`{name: value, 'domain': '****', ...}`格式

设置多个 cookie 支持的格式：

- `list`或`tuple`：上面几种形式的单个 cookie 放到列表中传入即可
- `dict`：`{name1: value1, name2: value2, ..., 'domain': '****', ...}`格式
- `str`：`'name1=value1; name2=value2; ... domain=****; ...'`格式，多个 cookie 之间只能用`';'`分隔
- `CookieJar`：单个`CookieJar`对象

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `cookies` | `Cookie` `CookieJar` `list` `tuple` `str` `dict` | 必填 | cookies 信息 |

**返回：**`None`

**示例：**

```python
# 可以接受多种类型的参数
cookies1 = ['name1=value1', 'name2=value2']
cookies2 = 'name1=value1; name2=value2; path=/; domain=.example.com;'
cookies3 = {'name1': 'value1', 'name2': 'value2', 'domain': '.example.com'}
tab.set.cookies(cookies1)
```

---

### 📌 `set.cookies.clear()`

此方法用于清除所有 cookie。

**参数：** 无

**返回：**`None`

---

### 📌 `set.cookies.remove()`

此方法用于删除一个 cookie。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | cookie 的 name 字段 |
| `url` | `str` | `None` | cookie 的 url 字段 |
| `domain` | `str` | `None` | cookie 的 domain 字段 |
| `path` | `str` | `None` | cookie 的 path 字段 |

**返回：**`None`

---

### 📌 `set.session_storage()`

此方法用于设置或删除某项 sessionStorage 信息。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `item` | `str` | 必填 | 要设置的项 |
| `value` | `str` `False` | 必填 | 为`False`时，删除该项 |

**返回：**`None`

**示例：**

```python
tab.set.session_storage(item='abc', value='123')
```

---

### 📌 `set.local_storage()`

此方法用于设置或删除某项 localStorage 信息。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `item` | `str` | 必填 | 要设置的项 |
| `value` | `str` `False` | 必填 | 为`False`时，删除该项 |

**返回：**`None`

---

### 📌 `clear_cache()`

此方法用于清除缓存，可选择要清除的项。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `session_storage` | `bool` | `True` | 是否清除 sessionstorage |
| `local_storage` | `bool` | `True` | 是否清除 localStorage |
| `cache` | `bool` | `True` | 是否清除 cache |
| `cookies` | `bool` | `True` | 是否清除 cookies |

**返回：**`None`

**示例：**

```python
tab.clear_cache(cookies=False)  # 除了 cookies，其它都清除
```

---

## ✅️️ 运行参数设置

各种设置功能藏在`set`属性中。

### 📌 `set.retry_times()`

此方法用于设置连接失败时重连次数。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `times` | `int` | 必填 | 次数 |

**返回：**`None`

### 📌 `set.retry_interval()`

此方法用于设置连接失败时重连间隔。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `interval` | `float` | 必填 | 秒数 |

**返回：**`None`

### 📌 `set.timeouts()`

此方法用于设置三种超时时间，单位为秒。可单独设置，为`None`表示不改变原来设置。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `base` | `float` | `None` | 整体超时时间 |
| `page_load` | `float` | `None` | 页面加载超时时间 |
| `script` | `float` | `None` | 脚本运行超时时间 |

**返回：**`None`

**示例：**

```python
tab.set.timeouts(base=10, page_load=30)
```

---

### 📌 `set.load_mode`

此属性用于设置页面加载策略，调用其方法选择某种策略。

| 方法名称 | 参数 | 说明 |
| --- | --- | --- |
| `normal()` | 无 | 等待页面完全加载完成，为默认状态 |
| `eager()` | 无 | 等待文档加载完成就结束，不等待资源加载 |
| `none()` | 无 | 页面连接完成就结束 |

**示例：**

```python
tab.set.load_mode.normal()
tab.set.load_mode.eager()
tab.set.load_mode.none()
```

---

### 📌 `set.user_agent()`

此方法用于为浏览器当前标签页设置 user agent。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `ua` | `str` | 必填 | user agent 字符串 |
| `platform` | `str` | `None` | 平台类型，如`'android'` |

**返回：**`None`

---

### 📌 `set.headers()`

此方法用于设置额外添加到当前页面请求 headers 的参数。

headers 可以是`dict`格式的，也可以是文本格式。

文本格式不同字段用`\n`分隔，字段 key 和 value 用`': '`分隔，即从浏览器直接复制的格式。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `headers` | `dict` `str` | 必填 | headers 信息 |

**返回：**`None`

**示例：**

```python
# dict格式
h = {'connection': 'keep-alive', 'accept-charset': 'GB2312,utf-8;q=0.7,*;q=0.7'}
tab.set.headers(headers=h)

# 文本格式
h = '''
connection: keep-alive
accept-charset: GB2312,utf-8;q=0.7,*;q=0.7
'''
tab.set.headers(headers=h)
```

---

## ✅️️ 窗口管理

窗口管理功能藏在`set.window`属性中。

### 📌 `set.window.max()`

此方法用于使窗口最大化。

**参数：** 无

**返回：**`None`

**示例：**

```python
tab.set.window.max()
```

---

### 📌 `set.window.mini()`

此方法用于使窗口最小化。

**参数：** 无

**返回：**`None`

---

### 📌 `set.window.full()`

此方法用于使窗口切换到全屏模式。

**参数：** 无

**返回：**`None`

---

### 📌 `set.window.normal()`

此方法用于使窗口切换到普通模式。

**参数：** 无

**返回：**`None`

---

### 📌 `set.window.size()`

此方法用于设置窗口大小。只传入一个参数时另一个参数不会变化。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `width` | `int` | `None` | 窗口宽度 |
| `height` | `int` | `None` | 窗口高度 |

**返回：**`None`

**示例：**

```python
tab.set.window.size(500, 500)
```

---

### 📌 `set.window.location()`

此方法用于设置窗口位置。只传入一个参数时另一个参数不会变化。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `x` | `int` | `None` | 距离顶部距离 |
| `y` | `int` | `None` | 距离左边距离 |

**返回 ：**`None`

**示例：**

```python
tab.set.window.location(500, 500)
```

---

### 📌 `set.window.hide()`

此 方法用于隐藏浏览器窗口。

与 headless 模式不一样，这个方法是直接隐藏浏览器进程。在任务栏上也会消失。只支持 Windows 系统，并且必需已安装 pypiwin32 库才可使用。

不过，窗口隐藏后，如果有新窗口出现，整个浏览器又会显现出来。

**参数：** 无

**返回：**`None`

**示例：**

```python
tab.set.window.hide()
```

注意

- 浏览器隐藏后并没有关闭，下次运行程序还会接管已隐藏的浏览器
- 浏览器隐藏后，如果有新建标签页，会自行显示出来

---

### 📌 `set.window.show()`

此方法用于显示当前浏览器窗口。

**参数：** 无

**返回：**`None`

---

## ✅️️ 页面滚动

页面滚动的功能藏在`scroll`属性中。

### 📌 `scroll()`或`scroll.down()`

这两个方法效果是一样的，用于使页面向下滚动若干像素，水平位置不变。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `pixel` | `int` | 必填 | 滚动的像素 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumTab` | `ChromiumTab`执行滚动时返回页面对象自身 |
| `MixTab` | `MixTab`执行滚动时返回页面对象自身 |
| `ChromiumFrame` | `ChromiumFrame`执行滚动时返回页面对象自身 |

---

### 📌 `scroll.up()`

此方法用于使页面向上滚动若干像素，水平位置不变。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `pixel` | `int` | 必填 | 滚动的像素 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumTab` | `ChromiumTab`执行滚动时返回页面对象自身 |
| `MixTab` | `MixTab`执行滚动时返回页面对象自身 |
| `ChromiumFrame` | `ChromiumFrame`执行滚动时返回页面对象自身 |

**示例：**

```python
tab.scroll.up(30)
```

---

### 📌 `scroll.right()`

此方法用于使页面向右滚动若干像素，垂直位置不变。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `pixel` | `int` | 必填 | 滚动的像素 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumTab` | `ChromiumTab`执行滚动时返回页面对象自身 |
| `MixTab` | `MixTab`执行滚动时返回页面对象自身 |
| `ChromiumFrame` | `ChromiumFrame`执行滚动时返回页面对象自身 |

---

### 📌 `scroll.left()`

此方法用于使页面向左滚动若干像素，垂直位置不变。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `pixel` | `int` | 必填 | 滚动的像素 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumTab` | `ChromiumTab`执行滚动时返回页面对象自身 |
| `MixTab` | `MixTab`执行滚动时返回页面对象自身 |
| `ChromiumFrame` | `ChromiumFrame`执行滚动时返回页面对象自身 |

---

### 📌 `scroll.to_top()`

此方法用于滚动页面到顶部，水平位置不变。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumTab` | `ChromiumTab`执行滚动时返回页面对象自身 |
| `MixTab` | `MixTab`执行滚动时返回页面对象自身 |
| `ChromiumFrame` | `ChromiumFrame`执行滚动时返回页面对象自身 |

**示例：**

```python
tab.scroll.to_top()
```

---

### 📌 `scroll.to_bottom()`

此方法用于滚动页面到底部，水平位置不变。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumTab` | `ChromiumTab`执行滚动时返回页面对象自身 |
| `MixTab` | `MixTab`执行滚动时返回页面对象自身 |
| `ChromiumFrame` | `ChromiumFrame`执行滚动时返回页面对象自身 |

---

### 📌 `scroll.to_half()`

此方法用于滚动页面到垂直中间位置，水平位置不变。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumTab` | `ChromiumTab`执行滚动时返回页面对象自身 |
| `MixTab` | `MixTab`执行滚动时返回页面对象自身 |
| `ChromiumFrame` | `ChromiumFrame`执行滚动时返回页面对象自身 |

---

### 📌 `scroll.to_rightmost()`

此方法用于滚动页面到最右边，垂直位置不变。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumTab` | `ChromiumTab`执行滚动时返回页面对象自身 |
| `MixTab` | `MixTab`执行滚动时返回页面对象自身 |
| `ChromiumFrame` | `ChromiumFrame`执行滚动时返回页面对象自身 |

---

### 📌 `scroll.to_leftmost()`

此方法用于滚动页面到最左边，垂直位置不变。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumTab` | `ChromiumTab`执行滚动时返回页面对象自身 |
| `MixTab` | `MixTab`执行滚动时返回页面对象自身 |
| `ChromiumFrame` | `ChromiumFrame`执行滚动时返回页面对象自身 |

---

### 📌 `scroll.to_location()`

此方法用于滚动页面到滚动到指定位置。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `x` | `int` | 必填 | 水平位置，单位是像素 |
| `y` | `int` | 必填 | 垂直位置，单位是像素 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumTab` | `ChromiumTab`执行滚动时返回页面对象自身 |
| `MixTab` | `MixTab`执行滚动时返回页面对象自身 |
| `ChromiumFrame` | `ChromiumFrame`执行滚动时返回页面对象自身 |

**示例：**

```python
tab.scroll.to_location(300, 50)
```

---

### 📌 `scroll.to_see()`

此方法用于滚动页面直到元素可见。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `loc_or_ele` | `str` `tuple` `ChromiumElement` | 必填 | 元素的定位信息，可以是元素、定位符 |
| `center` | `bool` `None` | `None` | 是否尽量滚动到页面正中，为`None`时如果被遮挡，则滚动到页面正中 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumTab` | `ChromiumTab`执行滚动时返回页面对象自身 |
| `MixTab` | `MixTab`执行滚动时返回页面对象自身 |
| `ChromiumFrame` | `ChromiumFrame`执行滚动时返回页面对象自身 |

**示例：**

```python
# 滚动到某个已获取到的元素
ele = tab.ele('tag:div')
tab.scroll.to_see(ele)

# 滚动到按定位符查找到的元素
tab.scroll.to_see('tag:div')
```

---

## ✅️️ 滚动设置

页面滚动有两种方式，一种是滚动时直接跳到目标位置，第二种是平滑滚动，需要一定时间。后者滚动时间难以确定，容易导致程序不稳定，点击不准确的问题。

一些网站会在 css 设置中指定网站使用平滑滚动，这是我们不希望的，但本着让开发者拥有充分选择权利的原则，本库没有强制修改，而是提供两项设置供开发者选择。

### 📌 `set.scroll.smooth()`

此方法设置网站是否 开启平滑滚动。建议用此方法为网页关闭平滑滚动。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | `True` | `bool`表示开或关 |

**返回：**`None`

**示例：**

```python
tab.set.scroll.smooth(on_off=False)
```

---

### 📌 `set.scroll.wait_complete()`

此方法用于设置滚动后是否等待滚动结束。在不想关闭网页平滑滚动功能时，可开启此设置以保障滚动结束后才执行后面的步骤

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | `True` | `bool`表示开或关 |

**返回：**`None`

**示例：**

```python
tab.set.scroll.wait_complete(on_off=True)
```

---

## ✅️️ 弹出消息处理

### 📌 `handle_alert()`

此方法用于处理提示框。
它能够设置等待时间，等待提示框出现才进行处理，若超时没等到提示框，返回`False`。
也可只获取提示框文本而不处理提示框。
还可以处理下一个出现的提示框，这在处理离开页面时触发的弹窗非常有用。

注意

程序无法接管一个已经弹 出了提示框的浏览器或标签页。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `accept` | `bool` `None` | `True` | `True`表示确认，`False`表示取消，`None`不会按按钮但依然返回文本值 |
| `send` | `str` | `None` | 处理 prompt 提示框时可输入文本 |
| `timeout` | `float` | `None` | 等待提示框出现的超时时间（秒），为`None`时使用页面整体超时时间 |
| `next_one` | `bool` | `False` | 是否处理下一个出现的弹窗，为`True`时`timeout`参数无效 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 提示框内容文本 |
| `False` | 未等到提示框则返回`False` |

**示例：**

```python
# 确认提示框并获取提示框文本
txt = tab.handle_alert()

# 点击取消
tab.handle_alert(accept=False)

# 给 prompt 提示框输入文本并点击确定
tab.handle_alert(accept=True, send='some text')

# 不处理提示框，只获取提示框文本
txt = tab.handle_alert(accept=None)
```

---

### 📌 自动处理

标签页对象可使用`set.auto_handle_alert()`方法设置自动处理该 tab 的提示框，使提示框不会弹窗而直接被处理掉。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | `True` | 开或关 |
| `accept` | `bool` | `True` | 确定还是取消 |

**返回：**`None`

**示例：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.set.auto_handle_alert()  # 这之后出现的弹窗都会自动确认
```

---

### 📌 全局自动处理

如果需要设置所有标签页都自动处理 alert，可用`Chromium`对象进行设置。

```python
from DrissionPage import Chromium

browser = Chromium()
browser.set.auto_handle_alert()
```

或者

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.browser.set.auto_handle_alert()
```

---

## ✅️️ 关闭及重连

### 📌 `disconnect()`

此方法用于页面对象断开与页面的连接，但不关闭标签页。断开后，对象不能对标签页进行操作。

Tab 和`ChromiumFrame`对象都有此方法。

**参数：** 无

**返回：**`None`

---

### 📌 `reconnect()`

此方法用于关闭与页面连接，然后重建一个新连接。

这主要用于应付长期运行导致内存占用过高，断开连接可释放内存，然后重连继续控制浏览器。

Tab 和`ChromiumFrame`对象都有此方法。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `wait` | `float` | `0` | 关闭后等待多少秒再连接 |

**返回：**`None`

---

### 📌 `close()`

此方法用于关闭标签页。可关闭自己或自己以外的。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `others` | `bool` | `False` | 是否关闭自己以外的标签页 |
| `session` | `bool` | `False` | 是否同时关闭内置`Session`对象，只对自己有效 |

**返回：**`None`

<!-- https://www.drissionpage.cn/browser_control/get_page_info -->

# 🛰️ 获取网页信息

成功访问网页后，可使用 Tab 对象属性和方法获取页面信息。

## ✅️️ 页面信息

### 📌 `html`

此属性返回当前页面 html 文本。

注意

html 文本不包含`<iframe>`元素内容。

**返回类型：**`str`

---

### 📌 `json`

此属性把请求内容解析成 json。

假如用浏览器访问会返回 `*.json` 文件的 url，浏览器会把 json 数据显示出来，这个参数可以把这些数据转换为`dict`格式。

**返回类型：**`dict`

---

### 📌 `title`

此属性返回当前页面`title`文本。

**返回类型：**`str`

---

### 📌 `user_agent`

此属性返回当前页面 user agent 信息。

**返回类型：**`str`

---

### 📌 `save()`

把当前页面保存为文件，同时返回保存的内容。

如果`path`和`name`参数都为`None`，只返回内容，不保存文件。

Page 对象和 Tab 对象有这个方法。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `path` | `str` `Path` | `None` | 保存路径，为`None`且`name`不为`None`时保存到当前路径 |
| `name` | `str` | `None` | 保存的文件名，为`None`且`path`不为`None`时使用 title 值 |
| `as_pdf` | `bool` | `False` | 为`Ture`保存为 pdf，否则保存为 mhtml 且忽略`kwargs`参数 |
| `**kwargs` | 多种 | 无 | pdf 生成参数 |

pdf 生成参数包括：`landscape`, `displayHeaderFooter`, `printBackground`, `scale`, `paperWidth`, `paperHeight`, `marginTop`, `marginBottom`, `marginLeft`, `marginRight`, `pageRanges`, `headerTemplate`, `footerTemplate`, `preferCSSPageSize`, `generateTaggedPDF`, `generateDocumentOutline`

| 返回类型 | 说明 |
| --- | --- |
| `str` | `as_pdf`为`False`时返回 mhtml 文本 |
| `bytes` | `as_pdf`为`True`时返回文件字节数据 |

---

## ✅️️ 运行状态信息

### 📌 `url`

此属性返回当前访问的 url。

**返回类型：**`str`

---

### 📌 `tab_id`

**返回类型：**`str`

此属性返回当前标签页的 id。

---

### 📌 `states.is_loading`

此属性返回页面是否正在加载状态。

**返回类型：**`bool`

---

### 📌 `states.is_alive`

此属性返回页面是否仍然可用，标签页已关闭则返回`False`。

**返回类型：**`bool`

---

### 📌 `states.ready_state`

此属性返回页面当前加载状态，有 4 种：

- `'connecting'`： 网页连接中
- `'loading'`：表示文档还在加载中
- `'interactive'`：DOM 已加载，但资源未加载完成
- `'complete'`：所有内容已完成加载

**返回类型：**`str`

---

### 📌 `url_available`

此属性以布尔值返回当前链接是否可用。

**返回类型：**`bool`

---

### 📌 `states.has_alert`

此属性以布尔值返回页面是否存在弹出框。

**返回类型：**`bool`

---

## ✅️️ 窗口信息

### 📌 `rect.size`

以`tuple`返回页面大小，格式：(宽, 高)。

**返回类型：**`Tuple[int, int]`

---

### 📌 `rect.window_size`

此属性以`tuple`返回窗口大小，格式：(宽, 高)。

**返回类型：**`Tuple[int, int]`

---

### 📌 `rect.window_location`

此属性以`tuple`返回窗口在屏幕上的坐标，左上角为(0, 0)。

**返回类型：**`Tuple[int, int]`

---

### 📌 `rect.window_state`

此属性以返回窗口当前状态，有`'normal'`、`'fullscreen'`、`'maximized'`、 `'minimized'`几种。

**返回类型：**`str`

---

### 📌 `rect.viewport_size`

此属性以`tuple`返回视口大小，不含滚动条，格式：(宽, 高)。

**返回类型：**`Tuple[int, int]`

---

### 📌 `rect.viewport_size_with_scrollbar`

此属性以`tuple`返回浏览器窗口大小，含滚动条，格式：(宽, 高)。

**返回类型：**`Tuple[int, int]`

---

### 📌 `rect.page_location`

此属性以`tuple`返回页面左上角在屏幕中坐标，左上角为(0, 0)。

**返回类型：**`Tuple[int, int]`

---

### 📌 `rect.viewport_location`

此属性以`tuple`返回视口在屏幕中坐标，左上角为(0, 0)。

**返回类型：**`Tuple[int, int]`

---

### 📌 `rect.scroll_position`

此属性返回页面滚动条位置，格式：(x, y)。

**类型：**`Tuple[float, float]`

---

## ✅️️ 配置参数信息

### 📌 `timeout`

此属性为整体默认超时时间（秒），包括元素查找、点击、处理提示框、列表选择等需要用到超时设置的地方，都以这个数据为默认值。默认为`10`。

**返回类型：**`int`、`float`

---

### 📌 `timeouts`

此属性以字典方式返回三种超时时间（秒）。

- `'base'`：与`timeout`属性是同一个值
- `'page_load'`：用于等待页面加载
- `'script'`：用于等待脚本执行

**返回类型：**`dict`

```python
print(tab.timeouts)
```

**输出：**

```text
{'base': 10, 'page_load': 30.0, 'script': 30.0}
```

---

### 📌 `retry_times`

此属性为网络连接失败时的重试次数，默认为`3`。

**返回类型：**`int`

---

### 📌 `retry_interval`

此属性为网络连接失败时的重试等待间隔秒数，默认为`2`。

**返回类型：**`int`、`float`

---

### 📌 `load_mode`

此属性返回页面加载策略，有 3 种：

- `'normal'`：等待页面所有资源完成加载
- `'eager'`：DOM 加载完成即停止
- `'none'`：页面完成连接即停止

**返回类型：**`str`

---

## ✅️️ cookies 和缓存信息

### 📌 `cookies()`

此方法以列表方式返回 cookies 信息。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `all_domains` | `bool` | `False` | 是否返回所有 cookies，为`False`只返回当前 url 的 |
| `all_info` | `bool` | `False` | 返回的 cookies 是否包含所有信息，`False`时只包含`name`、`value`、`domain`信息 |

| 返回类型 | 说明 |
| --- | --- |
| `CookiesList` | cookies 组成的列表 |

**示例：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('https://www.baidu.com')

for i in tab.cookies():
    print(i)
```

**输出：**

```text
{'domain': '.baidu.com', 'domain_specified': True, ......}
......
```

---

### 📌 指定返回类型

`cookies()`方法返回的列表可转换为其它指定格式。

- `cookies().as_str()`：`'name1=value1; name2=value2'`格式的字符串
- `cookies().as_dict()`：`{name1: value1, name2: value2}`格式的字典
- `cookies().as_json()`：json 格式的字符串

说明

`as_str()`和`as_dict()`都只会保留`'name'`和`'value'`字段。

---

### 📌 `session_storage()`

此方法用于获取 sessionStorage 信息，可获取全部或单个项。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `item` | `str` | `None` | 要获取的项目，为`None`则返回全部项目组成的字典 |

| 返回类型 | 说明 |
| --- | --- |
| `dict` | `item`参数为`None`时返回所有项目 |
| `str` | 指定`item`时返回该项目内容 |

---

### 📌 `local_storage()`

此方法用于获取 localStorage 信息，可获取全部或单个项。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `item` | `str` | `None` | 要获取的项目，为`None`则返回全部项目组成的字典 |

| 返回类型 | 说明 |
| --- | --- |
| `dict` | `item`参数为`None`时返回所有项目 |
| `str` | 指定`item`时返回该项目内容 |

---

<!-- https://www.drissionpage.cn/browser_control/get_elements/intro -->

# 🔦 概述

定位元素是自动化重中之重的技能。
虽然可在开发者工具直接复制绝对路径，但这样做有几个缺点：

- 代码冗长，可读性低
- 动态页面容易导致元素失效
- 无法使用相对定位
- 网页稍有改动或者出现临时元素就不能用，容错性低
- 无法跨`<iframe>`查找元素

因此作者极不建议使用右键复制的元素路径。

本库提供一套简洁易用的语法，用于快速定位元素，并且内置等待功能、支持链式查找，减少了代码的复杂性。
同时也兼容 css selector、xpath 和 selenium 原生的 loc 元组。

## ✅️️ 基本用法

所有页面对象和元素对象（包括`<iframe>`和 shadow-root），都可以在自己内部查找元素。

元素对象还能以自己为基准，相对定位其它元素。

定位元素大致有以下几种方法，将在后续小节中详细说明。

- 在页面或元素内查找子元素
- 根据 DOM 结构相对定位
- 根据视觉位置相对定位

所有的查找元素方法，都可以使用本库自创的查找语法、xpath、css selector和 selenium 的定位符元组，去查找元素。

---

## ✅️️ 示例

### 📌 简单示例

假设有 这样一个页面：

```html
<html>
<body>
<div id="one">
    <p class="p_cls" name="row1">第一行</p>
    <p class="p_cls" name="row2">第二行</p>
    <p class="p_cls">第三行</p>
</div>
<div id="two">
    第二个div
</div>
</body>
</html>
```

我们可以用页面对象去获取其中的元素：

```python
div1 = tab.ele('#one')  # 获取 id 为 one 的元素
p1 = tab.ele('@name=row1')  # 获取 name 属性为 row1 的元素
div2 = tab.ele('第二个div')  # 获取包含“第二个div”文本的元素
div_list = tab.eles('tag:div')  # 获取所有div元素
```

也可以获取到一个元素，然后在它里面或周围查找元素：

```python
div1 = tab.ele('#one')  # 获取到一个元素div1
p_list = div1.eles('tag:p')  # 在div1内查找所有p元素
div2 = div1.next()  # 获取div1后面一个元素
```

---

### 📌 实际示例

复制此代码可直接运行查看结果。

```python
from DrissionPage import SessionPage

page = SessionPage()
page.get('https://gitee.com/explore')

# 获取包含“全部推荐项目”文本的 ul 元素
ul_ele = page.ele('tag:ul@text():全部推荐项目')

# 获取该 ul 元素下所有 a 元素
titles = ul_ele.eles('tag:a')

# 遍历列表，打印每个 a 元素的文本
for i in titles:
    print(i.text)
```

**输出：**

```shell
全部推荐项目
前沿技术
智能硬件
IOT/物联网/边缘计算
车载应用
...
```

<!-- https://www.drissionpage.cn/browser_control/ele_operation -->

# 🛰️ 元素交互

本节介绍与浏览器元素的交互。浏览器元素对象为`ChromiumElement`。

## ✅️️ 点击元素

### 📌 `click()`和`click.left()`

这两个方法作用是一样的，用于左键点击元素。可选择模拟点击或 js 点击。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `by_js` | `bool` | `False` | 指定点击行为方式。 为`None`时，如不被遮挡，用模拟点击，否则用 js 点击 为`True`时直接用 js 点击； 为`False`时强制模拟点击，被遮挡也会进行点击 |
| `timeout` | `float` | `1.5` | 模拟点击的超时时间（秒），等待元素可见、可用、进入视口 |
| `wait_stop` | `bool` | `True` | 点击前是否等待元素停止运动 |

| 返回值 | 说明 |
| --- | --- |
| `False` | `by_js`为`False`，且元素不可用、不可见时，返回`False` |
| `True` | 除以上情况，其余情况都返回`True` |

**示例：**

```python
# 对ele元素进行模拟点击，如判断被遮挡也会点击
ele.click()

# 用js方式点击ele元素，无视遮罩层
ele.click(by_js=True)

# 如元素不被遮挡，用模拟点击，否则用js点击
ele.click(by_js=None)
```

默认情况下，`by_js`为`None`，优先用模拟方式点击，如遇遮挡、元素不可用、不可见、无法自动进入视口，等待直到超时后自动改用 js
方式点击。

`by_js`为`False`，程序会强制使用模拟点击，即使被遮挡也会点击元素位置。如果 元素不可见、不可用，会返回`False`。如元素无法自动滚动到视口，会改用
js 点击。

`by_js`为`True`时，则可无视任何遮挡，只要元素在 DOM 内，就能点击得到，但元素是否响应点击视网页所用架构而定。

可以根据需要灵活地对元素进行操作。

在模拟点击前，程序会先尝试把元素滚动到视口中。

默认情况下，如无法进行模拟点击（元素无法进入视口、不可用、隐藏）时，左键单击会返回`False`。但也可以通过全局设置使其抛出异常：

```python
from DrissionPage.common import Settings

Settings.set_raise_click_failed(True)
ele.click()  # 如无法点击则抛出异常
```

---

### 📌 `click.right()`

此方法实现右键单击元素。

**参数：** 无

**返回：**`None`

**示例：**

```python
ele.click.right()
```

---

### 📌 `click.middle()`

此方法实现中键单击元素。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `get_tab` | `bool` | `True` | 是否返回新出现的 Tab 对象 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumTab` | 如`get_tab`参数为`True`，元素在`ChromiumTab`返回对象 |
| `MixTab` | 如`get_tab`参数为`True`，元素在`MixTab`里时返回的对象 |
| `None` | `get_tab`参数为`False`时 |

**示例：**

```python
tab = ele.click.middle()
print(tab.title)
```

---

### 📌 `click.multi()`

此方法实现左键多次点击元素。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `times` | `int` | `2` | 点击次数 |

**返回：**`None`

---

### 📌 `click.at()`

此方法用于带偏移量点击元素，偏移量相对于元素左上角坐标。不传入`offset_x`和`offset_y`时点击元素中间点。
点击的目标不一定在元素上，可以传入负值，或大于元素大小的值，点击元素附近的区域。向右和向下为正值，向左和向上为负值。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `offset_x` | `float` | `None` | 相对元素左上角坐标的 x 轴偏移量，向下向右为正 |
| `offset_y` | `float` | `None` | 相对元素左上角坐标的 y 轴偏移量，向下向右为正 |
| `button` | `str` | `'left'` | 要点击的键，传入`'left'`、`'right'`、`'middle'`、`'back'`、`'forward'` |
| `count` | `int` | `1` | 点击次数 |

**返回：**`None`

**示例：**

```python
# 点击元素右上方 50*50 的位置
ele.click.at(50, -50)

# 点击元素上中部，x相对左上角向右偏移50，y保持在元素中点
ele.click.at(offset_x=50)

# 和click()一致，但没有重试功能
ele.click.at()
```

---

### 📌 `click.to_upload()`

此方法用于点击元素，触发文件选择框并把指定的文件路径添加到网页，详见“文件上传”章节。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `file_paths` | `str` `Path` `list` `tuple` | 必填 | 文件路径，如果上传框支持多文件，可传入列表或字符串，字符串时多个文件用`\n`分隔 |
| `by_js` | `bool` | `False` | 是否用 js 方式点击，逻辑与`click()`一致 |

**返回：**`None`

---

### 📌 `click.to_download()`

此方法用于点击元素触发下载，并返回下载任务对象。用法详见“文件下载”章节。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `save_path` | `str` `Path` | 必填 | 保存路径，为`None`保存在原来设置的，如未设置保存到当前路径 |
| `rename` | `str` | `None` | 重命名文件名，为`None`则不修改 |
| `suffix` | `str` | `'left'` | 指定文件后缀，为`None`则不修改 |
| `new_tab` | `bool` | `1` | 该下载是否在新 tab 中触发 |
| `by_js` | `bool` | `False` | 是否用 js 方式点击，逻辑与`click()`一致 |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`时使用页面对象默认超时时间 |

| 返回类型 | 说明 |
| --- | --- |
| `DownloadMission` | 下载任务对象 |

---

### 📌 `click.for_new_tab()`

在预期点击后会出现新 tab 的时候，可用此方法 点击，会等待并返回新 tab 对象。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `by_js` | `bool` | `False` | 是否用 js 方式点击，逻辑与`click()`一致 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumTab` | 元素在`ChromiumTab`里时返回 |
| `MixTab` | 元素在`MixTab`里时返回 |

---

## ✅️️ 输入内容

### 📌 `clear()`

此方法用于清空元素文本，可选择模拟按键或 js 方式。

模拟按键方式会自动输入`ctrl-a-del`组合键来清除文本框，js 方式则直接把元素`value`属性设置为`''`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `by_js` | `bool` | `False` | 是否用 js 方式清空 |

**返回：**`None`

**示例：**

```python
ele.clear()
```

---

### 📌 `input()`

此方法用于向元素输入文本或组合键，也可用于输入文件路径到上传控件。可选择输入前是否清空元素。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `vals` | `Any` | `False` | 文本值或按键组合 对文件上传控件时输入路径字符串或其组成的列表 |
| `clear` | `bool` | `False` | 输入前是否清空文本框 |
| `by_js` | `bool` | `False` | 是否用 js 方式输入，为`True`时不能输入组合键 |

**返回：**`None`

Tips

- 有些文本框可以接收回车代替点击按钮，可以直接在文本末尾加上`'\n'`。
- 会自动把非`str`数据转换为`str`。

**示例：**

```python
# 输入文本
ele.input('Hello world!')

# 输入文本并回车
ele.input('Hello world!\n')
```

---

### 📌 输入组合键

使用组合键或要传入特殊按键前，先要导入按键类`Keys`。

```python
from DrissionPage.common import Keys
```

然后将组合键放在一个`tuple`中传入`input()`即可。

```python
ele.input((Keys.CTRL, 'a', Keys.DEL))  # ctrl+a+del
```

`Keys`内置了 5 个常用组合键，分别为`CTRL_A`、`CTRL_C`、`CTRL_X`、`CTRL_V`、`CTRL_Z`、`CTRL_Y`。

```python
ele.input(Keys.CTRL_A)  # 全选
```

---

### 📌 `focus()`

此方法用于使元素获取焦点。

**参数：** 无

**返回：** `None`

---

## ✅️️ 拖拽和悬停

Tips

除了以下方法，本库还提供更灵活的动作链功能，详见后面章节。

### 📌 `drag()`

此方法用于拖拽元素到相对于当前的一个新位置，可以设置速度。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `offset_x` | `int` | `0` | x 轴偏移量，向下向右为正 |
| `offset_y` | `int` | `0` | y 轴偏移量，向下向右为正 |
| `duration` | `float` | `0.5` | 用时，单位秒，传入`0`即瞬间到达 |

**返回：**`None`

**示例：**

```python
# 拖动当前元素到距离50*50的位置，用时1秒
ele.drag(50, 50, 1)
```

---

### 📌 `drag_to()`

此方法用于拖拽元素到另一个元素上或一个坐标上。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `ele_or_loc` | `ChromiumElement` `Tuple[int, int]` | 必填 | 另一个元素对象或坐标元组 |
| `duration` | `float` | `0.5` | 用时，单位秒，传入`0`即瞬间到达 |

**返回：**`None`

**示例：**

```python
# 把 ele1 拖拽到 ele2 上
ele1 = page.ele('#div1')
ele2 = page.ele('#div2')
ele1.drag_to(ele2)

# 把 ele1 拖拽到网页 50, 50 的位置
ele1.drag_to((50, 50))
```

---

### 📌 `hover()`

此方法用于模拟鼠标悬停在元素上，可接受偏移量，偏移量相对于元素左上角坐标。不传入`offset_x`和`offset_y`值时悬停在元素中点。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `offset_x` | `int` | `None` | 相对元素左上角坐标的 x 轴偏移量，向下向右为正 |
| `offset_y` | `int` | `None` | 相对元素左上角坐标的 y 轴偏移量，向下向右为正 |

**返回：**`None`

**示例：**

```python
# 悬停在元素右上方 50*50 的位置
ele.hover(50, -50)

# 悬停在元素上中部，x 相对左上角向右偏移50，y 保持在元素中点
ele.hover(offset_x=50)

# 悬停在元素中点
ele.hover()
```

---

## ✅️️ 修改元素

### 📌 `set.innerHTML()`

此方法用于设置元素的 innerHTML 内容。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `html` | `str` | 必填 | html文本 |

**返回：**`None`

---

### 📌 `set.property()`

此方法用于设置元素`property`属性。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 属性名 |
| `value` | `str` | 必填 | 属性值 |

**返回：**`None`

**示例：**

```python
ele.set.property('value', 'Hello world!')
```

---

### 📌 `set.style()`

此方法用于设置元素样式。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 属性名 |
| `value` | `str` | 必填 | 属性值 |

**返回：**`None`

---

### 📌 `set.attr()`

此方法用于设置元素 attribute 属性。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 属性名 |
| `value` | `str` | 必填 | 属性值 |

**返回：**`None`

**示例：**

```python
ele.set.attr('href', 'http://DrissionPage.cn')
```

---

### 📌 `remove_attr()`

此方法用于删除元素 attribute 属性。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 属性名 |

**返回：**`None`

**示例：**

```python
ele.remove_attr('href')
```

---

### 📌 `set.value()`

此方法用于设置元素`value`值。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `value` | `str` | 必填 | 属性值 |

**返回：**`None`

---

### 📌 `check()`

此方法用于选中或取消选中元素。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `uncheck` | `bool` | `False` | 是否取消选中 |
| `by_js` | `bool` | `False` | 是否用 js 方式选择 |

**返回：**`None`

---

## ✅️️ 执行 js 脚本

### 📌 `run_js()`

此方法用于对元素执行 js 代码，代码中用`this`表示元素自己。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `script` | `str` | 必填 | js 脚本文本或脚本文件路径 |
| `*args` | - | 无 | 传入的参数，按顺序在js文本中对应`arguments[0]`、`arguments[1]`... |
| `as_expr` | `bool` | `False` | 是否作为表达式运行，为`True`时`args`参数无效 |
| `timetout` | `float` | `None` | js 超时时间（秒），为`None`则使用页面`timeouts.script`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `Any` | 脚本执行结果 |

注意

要获取 js 结果记得写上`return`。

**示例：**

```python
# 用执行 js 的方式点击元素
ele.run_js('this.click();')

# 用 js 获取元素高度
height = ele.run_js('return this.offsetHeight;')
```

---

### 📌 `run_async_js()`

此方法用于以异步方式执行 js 代码，代码中用`this`表示元素自己。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `script` | `str` | 必填 | js 脚本文本 |
| `*args` | - | 无 | 传入的参数，按顺序在js文本中对应`arguments[0]`、`arguments[1]`... |
| `as_expr` | `bool` | `False` | 是否作为表达式运行，为`True`时`args`参数无效 |

**返回：**`None`

---

### 📌 `add_init_js()`

此方法用于添加初始化脚本，在页面加载任何脚本前执行。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `script` | `str` | 必填 | js 脚本文本 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 添加的脚本的 id |

---

### 📌 `remove_init_js()`

此方法用于删除初始化脚本，`script_id`传入`None`时删除所有。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `script_id` | `str` | `None` | 脚本的id，传入`None`时删除所有 |

**返回：**`None`

---

## ✅️️ 元素滚动

元素滚动功能藏在`scroll`属性中。用于使可滚动的容器元素内部进行滚动，或使 元素本身滚动到可见。

```python
# 滚动到底部
ele.scroll.to_bottom()

# 滚动到最右边
ele.scroll.to_rightmost()

# 向下滚动 200 像素
ele.scroll.down(200)

# 滚动到指定位置
ele.scroll.to_location(100, 300)

# 滚动页面使自己可见
ele.scroll.to_see()
```

### 📌 `scroll()`或`scroll.down()`

这两个方法效果是一样的，用于使元素向下滚动若干像素，水平位置不变。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `pixel` | `int` | 必填 | 滚动的像素 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 执行滚动的元 素自身 |

```python
# 向下滚动30像素
ele.scroll(30)
ele.scroll.down(30)
```

---

### 📌 `scroll.up()`

此方法用于使元素向上滚动若干像素，水平位置不变。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `pixel` | `int` | 必填 | 滚动的像素 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 执行滚动的元素自身 |

**示例：**

```python
page.scroll.up(30)
```

---

### 📌 `scroll.right()`

此方法用于使元素内滚动条向右滚动若干像素，垂直位置不变。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `pixel` | `int` | 必填 | 滚动的像素 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 执行滚动的元素自身 |

---

### 📌 `scroll.left()`

此方法用于使元素内滚动条向左滚动若干像素，垂直位置不变。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `pixel` | `int` | 必填 | 滚动的像素 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 执行滚动的元素自身 |

---

### 📌 `scroll.to_top()`

此方法用于滚动到元素顶部，水平位置不变。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 执行滚动的元素自身 |

**示例：**

```python
page.scroll.to_top()
```

---

### 📌 `scroll.to_bottom()`

此方法用于滚动到元素底部，水平位置不变。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 执行滚动的元素自身 |

---

### 📌 `scroll.to_half()`

此方法用于滚动到元素垂直中间位置，水平位置不变。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 执行滚动的元素自身 |

---

### 📌 `scroll.to_rightmost()`

此方法用于滚动到元素最右边，垂直位置不变。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 执行滚动的元素自身 |

---

### 📌 `scroll.to_leftmost()`

此方法用于滚动到元素最左边，垂直位置不变。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 执行滚动的元素自身 |

---

### 📌 `scroll.to_location()`

此方法用于滚动到元素滚动到指定位置。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `x` | `int` | 必填 | 水平位置 |
| `y` | `int` | 必填 | 垂直位置 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 执行滚动的元素自身 |

**示例：**

```python
page.scroll.to_location(300, 50)
```

---

### 📌 `scroll.to_see()`

此方法用于滚动页面直到元素可见。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `center` | `bool` `None` | `None` | 是否尽量滚动到页面正中，为`None`时如果被遮挡，则滚动到页面正中 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 执行滚动的元素自身 |

---

### 📌 `scroll.to_center()`

此方法用于尽量把元素滚动到视口正中。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 执行滚动的元素自身 |

---

## ✅️️ 列表选择

`<select>`下拉列表元素功能在`select`属性中。可自动等待列表项出现再实施选择。

此属性用于对`<select>`元素的操作。非`<select>`元素此属性为`None`。

假设有以下`<select>`元素，下面示例以此为基础：

```html
<select id='s' multiple>
    <option value='value1'>text1</option>
    <option value='value2'>text2</option>
    <option value='value3'>text3</option>
</select>
```

### 📌 点击列表项元素进行选取

可以获取`<option>`元素，进行选取或取消选择。

**示例：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
ele = tab('t:select')('t:option')
ele.click()
```

---

### 📌 `select()`和`select.by_text()`

这两个方法功能一样，用于按文本选择列表项。如为多选列表，可多选。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `text` | `str` `list` `tuple` | 必填 | 作为选择条件的文本，传入`list`或`tuple`可选择多项 |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`默认使用页面超时时间 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否选择成功 |

---

### 📌 `select.by_value()`

此方法用于按`value`属性选择列表项。如为多选列表，可多选。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `value` | `str` `list` `tuple` | 必填 | 作为选择条件的`value`值，传入`list`或`tuple`可选择多项 |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`默认使用页面超时时间 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否选择成功 |

---

### 📌 `select.by_index()`

此方法用于按序号选择列表项，从`1`开始。如为多选列表，可多选。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `index` | `int` `list` `tuple` | 必填 | 选择第几项，传入`list`或`tuple`可选择多项 |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`默认使用页面超时时间 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否选择成功 |

---

### 📌 `select.by_locator()`

此方法可用定位符筛选选项元素。如为多选列表，可多选。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `list` `tuple` | 必填 | 定位符，传入`list`或`tuple`可选择多项 |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`默认使用页面超时时间 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否选择成功 |

---

### 📌 `select.by_option()`

此方法用于选中单个或多个列表项元素。如为多选列表，可多选。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `option` | `ChromiumElement` `List[ChromiumElement]` | 必填 | `<option>`元素或它们组成的列表 |

**返回：**`None`

**示例：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
select = tab('t:select')
option = select('t:option')
select.select.by_option(option)
```

---

### 📌 `select.cancel_by_text()`

此方法用于按文本取消选择列表项。如为多选列表，可取消多项。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `text` | `str` `list` `tuple` | 必填 | 作为选择条件的文本，传入`list`或`tuple`可选择多项 |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`默认使用页面超时时间 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否选择成功 |

---

### 📌 `select.cancel_by_value()`

此方法用于按`value`属性取消选择列表项。如为多选列表，可取消多项。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `value` | `str` `list` `tuple` | 必填 | 作为选择条件的`value`值，传入`list`或`tuple`可选择多项 |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`默认使用页面超时时间 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否选择成功 |

---

### 📌 `select.cancel_by_index()`

此方法用于按序号取消选择列表项，从`1`开始。如为多选列表，可取消多项。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `index` | `int` `list` `tuple` | 必填 | 选择第几项，传入`list`或`tuple`可选择多项 |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`默认使用页面超时时间 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否选择成功 |

---

### 📌 `select.cancel_by_locator()`

此方法可用定位符筛选选项元素。如为多选列表，可取消多项。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `list` `tuple` | 必填 | 定位符，传入`list`或`tuple`可选择多项 |
| `timeout` | `float` | `None` | 超时时间，为`None`默认使用页面超时时间 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否选择成功 |

---

### 📌 `select.cancel_by_option()`

此方法用于取消选中单个或多个列表项元素。如为多选列表，可多选。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `option` | `ChromiumElement` `List[ChromiumElement]` | 必填 | `<option>`元素或它们组成的列表 |

**返回：**`None`

---

### 📌 `select.all()`

此方法用于全选所有项。多选列表才有效。

**参数：** 无

**返回：**`None`

---

### 📌 `select.clear()`

此方法用于取消所有项选中状态。多选列表才有效。

**参数：** 无

**返回：**`None`

---

### 📌 `select.invert()`

此方法用于反选。多选列表才有效。

**参数：** 无

**返回：**`None`

---

### 📌 `select.is_multi`

此属性返回当前元素是否多选列表。

**返回类型：**`bool`

---

### 📌 `select.options`

此属性返回当前列表元素所有选项元素对象。

**返回类型：**`ChromiumElement`

---

### 📌 `select.selected_option`

此属性返回当前元素选中的选项（单选列表）。

**返回类型：**`ChromiumElement`

---

### 📌 `select.selected_options`

此属性返回当前元素所有选中的选项（多选列表）。

**返回类型：**`List[ChromiumElement]`

<!-- https://www.drissionpage.cn/browser_control/get_ele_info -->

# 🛰️ 获取元素信息

浏览器元素对应的对象是`ChromiumElement`和`ShadowRoot`，本节介绍如何获取元素信息。

## ✅️️ 内容和属性

### 📌 `tag`

此属性返回元素的标签名。

**返回类型：**`str`

---

### 📌 `html`

此属性返回元素的`outerHTML`文本。

**返回类型：**`str`

---

### 📌 `inner_html`

此属性返回元素的`innerHTML`文本。

**返回类型：**`str`

---

### 📌 `text`

此属性返回元素内所有文本组合成的字符串。
该字符串已格式化，即已转码，已去除多余换行符，符合人读取习惯，便于直接使用。

**返回类 型：**`str`

---

### 📌 `raw_text`

此属性返回元素内未经处理的原始文本。

**返回类型：**`str`

---

### 📌 `texts()`

此方法返回元素内所有**直接**子节点的文本，包括元素和文本节点。 它有一个参数`text_node_only`，为`True`时则只获取只返回不被包裹的文本节点。这个方法适用于获取文本节点和元素节点混排的情况。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `text_node_only` | `bool` | `False` | 是否只返回文本节点 |

| 返回类型 | 说明 |
| --- | --- |
| `List[str]` | 文本列表 |

---

### 📌 `comments`

此属性以列表形式返回元素内的注释。

**返回类型：**`List[str]`

---

### 📌 `attrs`

此 属性以字典形式返回元素所有属性及值。

**返回类型：**`dict`

---

### 📌 `attr()`

此方法返回元素某个 attribute 属性值。它接收一个字符串参数，返回该属性值文本，无该属性时返回`None`。
此属性返回的`src`、`href`属性为已补充完整的路径。`text`属性为已格式化文本。
如果要获取未补充完整路径的`src`或`href`属性，可以用`attrs['src']`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 属性名称 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 属性值文本 |
| `None` | 没有该属性返回`None` |

---

### 📌 `property()`

此方法返回`property`属性值。它接收一个字符串参数，返回该参数的属性值。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 属性名称 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 属性值 |

---

### 📌 `value`

此方法返回元素的`value`值。

**返回类型：**`str`

---

### 📌 `link`

此方法返回元素的`href`属性或`src`属性，没有这两个属性则返回`None`。

**返回类型：**`str`

---

### 📌 `pseudo.before`

此属性以文本形式返回当前元素的`::before`伪元素内容。

**类型：**`str`

---

### 📌 `pseudo.after`

此属性以文本形式返回当前元素的`::after`伪元素内容。

**类型：**`str`

---

### 📌 `style()`

该方法返回元素 css 样式属性值，可获取伪元素的属性。它有两个参数，`style`参数输入样式属性名称，`pseudo_ele`
参数输入伪元素名称，省略则获取普通元素的 css 样式属性。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `style` | `str` | 必填 | 样式名称 |
| `pseudo_ele` | `str` | `''` | 伪元素名称（如有） |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 样式属性值 |

---

### 📌 `shadow_root`

此属性返回元素内的 shadow-root 对象，没有的返回`None`。

**类型：**`ShadowRoot`

---

### 📌 `child_count`

此属性返回元素内第一级子元素个数。

**类型：**`int`

---

## ✅️️ 大小和位置

### 📌 `rect.size`

此属性以元组形式返回元素的大小。

**类型：**`Tuple[float, float]`

```python
size = ele.rect.size
# 返回：(50, 50)
```

---

### 📌 `rect.location`

此属性以元组形式返回元素**左上角**在**整个页面**中的坐标。

**类型：**`Tuple[float, float]`

```python
loc = ele.rect.location
# 返回：(50, 50)
```

---

### 📌 `rect.midpoint`

此属性以元组形式返回元素**中点**在**整个页面**中的坐标。

**类型：**`Tuple[float, float]`

```python
loc = ele.rect.midpoint
# 返回：(55, 55)
```

---

### 📌 `rect.click_point`

此属性以元组形式返回元素**点击点**在**整个页面**中的坐标。

点击点是指`click()`方法点击时的位置，位于元素中上部。

**类型：**`Tuple[float, float]`

---

### 📌 `rect.corners`

此属性以列表形式返回元素四个角在页面中的坐标，顺序：左上、右上、右下、左下。

**类型：**`((float, float), (float, float), (float, float), (float, float),)`

---

### 📌 `rect.viewport_corners`

此属性以列表形式返回元素四个角在视口中的坐标，顺序：左上、右上、右下、左下。

**类型：**`list[(float, float), (float, float), (float, float), (float, float)]`

---

### 📌 `rect.viewport_location`

此属性以元组形式返回元素**左上角**在**当前视口**中的坐标。

**类型：**`Tuple[float, float]`

---

### 📌 `rect.viewport_midpoint`

此属性以元组形式返回元素**中点**在**当前视口**中的坐标。

**类型：**`Tuple[floatt, float]`

---

### 📌 `rect.viewport_click_point`

此属性以元组形式返回元素**点击点**在**当前视口**中的坐标。

**类型：**`Tuple[float, float]`

---

### 📌 `rect.screen_location`

此属性以元组形式返回元素**左上角**在**屏幕**中的坐标。

**类型：**`Tuple[float, float]`

---

### 📌 `rect.screen_midpoint`

此属性以元组形式返回元素**中点**在**屏幕**中的坐标。

**类型：**`Tuple[float, float]`

---

### 📌 `rect.screen_click_point`

此属性以元组形式返回元素**点击点**在**屏幕**中的坐标。

**类型：**`Tuple[float, float]`

---

### 📌 `rect.scroll_position`

此属性返回元素内滚动条位置，格式：(x, y)。

**类型：**`Tuple[float, float]`

---

### 📌 `xpath`

此属性返回当前元素在页面中 xpath 的绝对路径。

**返回类型：**`str`

---

### 📌 `css_path`

此属性返回当前元素在页面中 css selector 的绝对路径。

**返回类型：**`str`

---

## ✅️️ 元素列表中批量获取信息

`eles()`等返回的元素列表，自带`get`属性，可用于获取指定信息。

### 📌 示例

```python
from DrissionPage import SessionPage

page = SessionPage()
page.get('https://www.baidu.com')
eles = page('#s-top-left').eles('t:a')
print(eles.get.texts())  # 获取所有元素的文本
```

**输出：**

```shell
['新闻', 'hao123', '地图', '贴吧', '视频', '图片', '网盘', '文库', '更多', '翻译', '学术', '百科', '知道', '健康', '营销推广', '直播', '音乐', '橙篇', '查看全部百度产品 >']
```

### 📌 `get.attrs()`

此方法用于返回所有元素指定的 attribute 属性组成的列表。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 属性名称 |

| 返回类型 | 说明 |
| --- | --- |
| `List[str]` | 属性文本组成的列表 |

---

### 📌 `get.links()`

此方法用于返回所有元素的`link`属性组成的列表。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `List[str]` | 链接文本组成的列表 |

---

### 📌 `get.texts()`

此方法用于返回所有元素的`text`属性组成的列表。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `List[str]` | 元素文本组成的列表 |

---

## ✅️️ 状态信息

### 📌`timeout`

此属性返回获取内部或相对定位元素的超时时间，实际上是元素所在页面的超时设置。

**类型：**`float`

---

### 📌`states.is_in_viewport`

此属性以布尔值方式返回元素是否在视口中，以元素可以接受点击的点为判断。

**类型：**`bool`

---

### 📌`states.is_whole_in_viewport`

此属性以布尔值方 式返回元素是否整个在视口中。

**类型：**`bool`

---

### 📌`states.is_alive`

此属性以布尔值形式返回当前元素是否仍可用。用于判断 d 模式下是否因页面刷新而导致元素失效。

**类型：**`bool`

---

### 📌 `states.is_checked`

此属性以布尔值返回表单单选或多选元素是否选中。

**类型：**`bool`

---

### 📌 `states.is_selected`

此属性以布尔值返回`<select>`元素中的项是否选中。

**类型：**`bool`

---

### 📌 `states.is_enabled`

此属性以布尔值返回元素是否可用。

**类型：**`bool`

---

### 📌 `states.is_displayed`

此属性以布尔值返回元素是否可见。

**类型：**`bool`

---

### 📌 `states.is_covered`

此属性返回元素是否被其它元素覆盖。如被覆盖，返回覆盖元素的 id，否则返回`False`

| 返回类型 | 说明 |
| --- | --- |
| `False` | 未被覆盖，返回`False` |
| `int` | 被覆盖时返回覆盖元素的 id |

---

### 📌 `states.is_clickable`

此属性返回元素是否可被模拟点击，从是否有大小、是否可用、是否显示、是否响应点击判断，不判断是否被遮挡。

**类型：**`bool`

---

### 📌 `states.has_rect`

此属性返回元素是否拥有大小和位置信息，有则返回四个角在页面上的坐标组成的列表，没有则返回`False`。

| 返回类型 | 说明 |
| --- | --- |
| `list` | 存在大小和位置信息时，以[(int, int), ...] 格式返回元素四个角的坐标，顺序：左上、右上、右下、左下 |
| `False` | 不存在时返回`False` |

---

## ✅️️ 保存元素

保存功能是本库一个特色功能，可以直接读取浏览器缓存，无需依赖另外的 ui 库或重新下载就可以保存页面资源。

作为对比，selenium 无法自身实现图片另存，往往需要通过使用 ui 工具进行辅助，不仅效率和可靠性低，还占用键鼠资源。

### 📌 `src()`

此方法用于返回元素`src`属性所使用的资源。base64 的可转为`bytes`返回，其它的以`str`返回。无资源的返回`None`。

例如，可获取页面上图片字节数据，用于识别内容，或保存到文件。`<script>`和`<link>`标签也可获取文件内容。

注意

获取`<script>`或`<link>`文件内容时，视网站情况不一定会成功。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 等待资源加载超时时间（秒），为`None`时使用元素所在页面`timeout`属性 |
| `base64_to_bytes` | `bool` | `True` | 为`True`时，如果是 base64 数据，转换为`bytes`格式 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 资源字符串 |
| `None` | 无资源的返回`None` |

**示例：**

```python
img = page('tag:img')
src = img.src()
```

---

### 📌 `save()`

此方法用于保存`src()`方法获取到的资源到文件。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `path` | `str` `Path` | `None` | 文件保存路径，为`None`时保存到当前文件夹 |
| `name` | `str` | `None` | 文件名称，需包含后缀，为`None`时从资源 url 获取 |
| `timeout` | `float` | `None` | 等待资源加载超时时间（秒），为`None`时使用元素所在页面`timeout`属性 |
| `rename` | `bool` | `True` | 遇到重名文件时是否自动重命名 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 保存路径 |

**示例：**

```python
img = page('tag:img')
img.save('D:\\img.png')
```

---

## ✅️️ 比较元素

两个元素对象可以用`==`来比较，以判断它们是否指向同一个元素。

**示例：**

```python
ele1 = page('t:div')
ele2 = page('t:div')
print(ele1==ele2)  # 输出True
```

<!-- https://www.drissionpage.cn/browser_control/iframe -->

# 🛰️ iframe 操作

`<iframe>`元素是一种特殊的元素，它既是元素，也是页面。

DrissionPage 无需切入切出即可处理`<iframe>`元素。
可实现跨级元素查找、元素内部单独跳转、同时操作`<iframe>`内外元素、多线程控制多个`<iframe>`等操作。

## ✅️ 获取`<iframe>`对象

获取`<iframe>`对象的方法有两种，可用获取普通元素的方式获取，或者用`get_frame()`方法获取。

推荐优先使用`get_frame()`方法，因为当作普通元素获取时，IDE 无法正确识别获取到的是`<iframe>`元素。

### 📌 `get_frame()`

此方法用于获取页面中一个`<frame>`或`<iframe>`对象。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `loc_ind_ele` | `str` `int` `ChromiumFrame` | 必填 | 定位符 `<iframe>`元素序号（从`1`开始，负数表示倒数） `ChromiumFrame对象` `id`属性内容 `name`属性内容 |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`时使用页面超时时间 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumFrame` | `<frame>`或`<iframe>`元素对象 |
| `NoneElement` | 找不到时返回`NoneElement` |

注意

需要特别注意的是，如果页面中有嵌套的`<iframe>`，用序号获取的方式会存在不准确。
比如，用`get_frames()`可获取到 6 个元素，但用`get_frame(6)`却获取不到最后一个。
这是因为有两个`<iframe>`是嵌套关系，导致获取不准确。

**示例：**

```python
# 使用定位符获取
iframe = tab.get_frame('t:iframe')

# 获取第1个iframe
iframe = tab.get_frame(1)
```

---

### 📌 `get_frames()`

此方法用于获取页面中多个符合条件的`<frame>`或`<iframe>`对象。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` | `None` | 定位符，为`None`时返回所有 |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`时使用页面超时时间 |

| 返回类型 | 说明 |
| --- | --- |
| `List[ChromiumFrame]` | `<frame>`或`<iframe>`元素对象组成的列表 |

提醒

获取所有`<iframe>`会很慢，而且浪费资源，一般使用获取需要用到的就好。

---

### 📌 普通元素方式

可以用获取普通元素的方式获取`<iframe>`对象：

```python
iframe = tab('t:iframe')
```

这个`ChromiumFrame`对象既是页面也是元素。由于 IDE 不会提示`<iframe>`
元素对象相关的属性和方法，因此用这种方式获取时建议再用`get_frame()`包装一下：

```python
iframe = tab('t:iframe')
iframe = tab.get_frame(iframe)
```

---

## ✅️ 查找`<iframe>`内元素

当`<iframe>`与标签页是同域的，我们并不需要先切入`<iframe>`，就可以获取到里面的元素。

如果是异域的，则先要获取这个标签页的`ChromiumFrame`对象，再用这个对象在自己内部搜索。

### 📌 页面跨`<iframe>`查找

如果`<iframe>`元素的网址和主页面是同域的，我们可以直接用页面对象查找`<iframe>`内部元素，而无需先获取`ChromiumFrame`对象。

以下示例页面中有一个`<iframe>`元素，和标签页是同域的，可直接通过 Tab 对象查找它内部的元素。

只要是同域名的，无论跨多少层`<iframe>`都能用页面对象直接获取。

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('http://DrissionPage.cn/demos/iframe_same_domain.html')
ele = tab('概述')
print(ele)
```

**输出：**

```shell
<ChromiumElement h2 class='anchor anchorWithStickyNavbar_LWe7' id='️-概述'>
```

---

### 📌 在`<iframe>`内查找

如果`<iframe>`跟当前标签页是不同域名的，不能使用页面对象直接查找其中元素，只能先获取其`ChromiumFrame`元素对象，再在这个对象中查找。

即使是同域的，也可以通过这种方法查找。

但创建`ChromiumFrame`对象会增加系统资源的使用，一般建议异域的才创建对象。

以下示例页面中有一个`<iframe>`元素，和标签页是不同域的，需要先获取`ChromiumFrame`对象，再在里面找元素。

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('http://DrissionPage.cn/demos/iframe_diff_domain.html')
iframe = tab.get_frame('t:iframe')
ele = iframe('网易首页')
print(ele)
```

**输出：**

```shell
<ChromiumElement a class='ntes-nav-index-title ntes-nav-entry-wide c-fl' href='https://www.163.com/' title='网易首页'>
```

---

## ✅️ 方法和属性

正如上面所说，`ChromiumFrame`既是元素也是页面，它可以获取自身元素方面的属性或执行操作。

详见相关章节。

```python
iframe.tag
iframe.html
iframe.remove_attr()
iframe.states.is_alive
iframe.get()
iframe.get_screenshot()
# 等等
```

<!-- https://www.drissionpage.cn/browser_control/actions -->

# 🛰️ 动作链

动作链可以在浏览器上完成一系列交互行为，如鼠标移动、鼠标点击、键盘输入等。

浏览器页面对象都支持使用动作链。

可以链式操作，也可以分开执行，每个动作执行即生效，无需`perform()`。

这些操作皆为模拟，真正的鼠标不会移动，因此可以多个标签页同时操作。

## ✅️ 使用方法

可以用上述对象内置的`actions`属性调用动作链，也可以主动创建一个动作链对象，将页面对象传入使用。

这两种方式唯一区别是，前者会等待页面加载完毕再执行，后者不会。

### 📌 使用内置`actions`属性

说明

这种方式会等到页面框架文档（不包括 js 数据）加载完成再执行动作。

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('https://www.baidu.com')
tab.actions.move_to('#kw').click().type('DrissionPage')
tab.actions.move_to('#su').click()
```

---

### 📌 使用新对象

使用`from DrissionPage.common import Actions`导入动作链。

只要把`WebPage`对象或`ChromiumPage`对象传入即可。动作链只在这个页面上生效。

| 初始化参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `page` | `ChromiumPage` `WebPage` `ChromiumTab` | 必填 | 动作链要操作的浏览器页面 |

说明

这种方式**不会**等到页面框架文档（不包括 js 数据）加载完成再执行动作。

**示例：**

```python
from DrissionPage import Chromium
from DrissionPage.common import Actions

tab = Chromium().latest_tab
ac = Actions(tab)
tab.get('https://www.baidu.com')
ac.move_to('#kw').click().type('DrissionPage')
ac.move_to('#su').click()
```

---

### 📌 操作方式

多个动作可以用链式模式操作：

```python
tab.actions.move_to(ele).click().type('some text')
```

也可以多个操作分开执行：

```python
tab.actions.move_to(ele)
tab.actions.click()
tab.actions.type('some text')
```

这两种方式效果是一样的，每个动作总会依次执行。

---

## ✅️ 移动鼠标

### 📌 `move_to()`

此方法用于移动鼠标到元素中点，或页面上的某个 绝对坐标。

当`offset_x`和`offset_y`都为`None`时，移动到元素中间点。

当传入偏移量时，偏移量相对于元素左上角坐标。

| 初始化参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `ele_or_loc` | `ChrmoiumElement` `str` `Tuple[int, int]` | 必填 | 元素对象、文本定位符或绝对坐标，坐标为`tuple`(int, int) 形式 |
| `offset_x` | `int` | `None` | x 轴偏移量，向右为正，向左为负 |
| `offset_y` | `int` | `None` | y 轴偏移量，向下为正，向上为负 |
| `duration` | `float` | `0.5` | 拖动用时，传入`0`即瞬间到达 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

**示例：** 使鼠标移动到 ele 元素上

```python
ele = tab('tag:a')
tab.actions.move_to(ele_or_loc=ele)
```

---

### 📌 `move()`

此方法用于使鼠标相对当前位置移动若干距离。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `offset_x` | `int` | `0` | x 轴偏移量，向右为正，向左为负 |
| `offset_y` | `int` | `0` | y 轴偏移量，向下为正，向上为负 |
| `duration` | `float` | `0.5` | 拖动用时，传入`0`即瞬间到达 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

**示例：** 鼠标向右移动 300 像素

```python
tab.actions.move(300, 0)
```

---

### 📌 `up()`

此方法用于使鼠标相对当前位置向上移动若干距离。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `pixel` | `int` | 必填 | 鼠标移动的像素值 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

**示例：** 鼠标向上移动 50 像素

```python
tab.actions.up(50)
```

---

### 📌 `down()`

此方法用于使鼠标相对当前位置向下移动若干距离。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `pixel` | `int` | 必填 | 鼠标移动的像素值 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

**示例：**

```python
tab.actions.down(50)
```

---

### 📌 `left()`

此方法用于使鼠标相对当前位置向左移动若干距离。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `pixel` | `int` | 必填 | 鼠标移动的像素值 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

**示例：**

```python
tab.actions.left(50)
```

---

### 📌 `right()`

此方法用于使鼠标相对当前位置向右移动若干距离。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `pixel` | `int` | 必填 | 鼠标移动的像素值 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

**示例：**

```python
tab.actions.right(50)
```

---

## ✅️ 鼠标按键

### 📌 `click()`

此方法用于单击鼠标左键，单击前可先移动到元素上。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_ele` | `ChromiumElement` `str` | `None` | 要点击的元素对象或文本定位符 |
| `times` | `int` | `1` | 点击次数 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

**示例：**

```python
tab.actions.click('#div1')
```

---

### 📌 `r_click()`

此方法用于单击鼠标右键，单击前可先移动到元素上。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_ele` | `ChromiumElement` `str` | `None` | 要点击的元素对象或文本定位符 |
| `times` | `int` | `1` | 点击次数 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

**示例：**

```python
tab.actions.r_click('#div1')
```

---

### 📌 `m_click()`

此方法用于单击鼠标中键，单击前可先移动到元素上。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_ele` | `ChromiumElement` `str` | `None` | 要点击的元素对象或文本定位符 |
| `times` | `int` | `1` | 点击次数 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

**示例：**

```python
tab.actions.m_click('#div1')
```

---

### 📌 `hold()`

此方法用于按住鼠标左键不放，按住前可先移动到元素上。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_ele` | `ChromiumElement` `str` | `None` | 要按住的元素对象或文本定位符 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

**示例：**

```python
tab.actions.hold('#div1')
```

---

### 📌 `release()`

此方法用于释放鼠标左键，释放前可先移动到元素上。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_ele` | `ChromiumElement` `str` | `None` | 要释放的元素对象或文本定位符 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

**示例：** 移动到某元素上然后释放鼠标左键

```python
tab.actions.release('#div1')
```

---

### 📌 `r_hold()`

此方法用于按住鼠标右键不放，按住前可先移动到元素上。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_ele` | `ChromiumElement` `str` | `None` | 要按住的元素对象或文本定位符 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

---

### 📌 `r_release()`

此方法用于释放鼠标右键，释放前可先移动到元素上。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_ele` | `ChromiumElement` `str` | `None` | 要释放的元素对象或文本定位符 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

---

### 📌 `m_hold()`

此方法用于按住鼠标中键不放，按住前可先移动到元素上。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_ele` | `ChromiumElement` `str` | `None` | 要按住的元素对象或文本定位符 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

---

### 📌 `m_release()`

此方法用于释放鼠标中键，释放前可先移动到元素上。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_ele` | `ChromiumElement` `str` | `None` | 要释放的元素对象或文本定位符 |

| 类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

---

## ✅️ 滚动滚轮

### 📌 `scroll()`

此方法用于滚动鼠标滚轮，滚动前可先移动到元素上。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `delta_y` | `int` | `0` | 滚轮 y 轴变化值，向下为正，向上为负 |
| `delta_x` | `int` | `0` | 滚轮 x 轴变化值，向右为正，向左为负 |
| `on_ele` | `ChromiumElement` `str` | `None` | 要滚动的元素对象或文本定位符 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

---

## ✅️ 键盘按键和文本输入

### 📌 `key_down()`

此方法用于按下键盘按键。非字符串按键（如 ENTER）可输入其名称，也可以用 Keys 类获取。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `key` | `str` | 必填 | 按键名称，或从`Keys`类获取的键值 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

**示例：** 按下 ENTER 键

```python
from DrissionPage.common import Keys

tab.actions.key_down('ENTER')  # 输入按键名称
tab.actions.key_down(Keys.ENTER)  # 从Keys获取按键
```

---

### 📌 `key_up()`

此方法用于提起键盘按键。非字符串按键（如 ENTER）可输入其名称，也可以用 Keys 类获取。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `key` | `str` | 必填 | 按键名称，或从`Keys`类获取的键值 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

**示例：** 提起 ENTER 键

```python
from DrissionPage.common import Keys

tab.actions.key_up('ENTER')  # 输入按键名称
tab.actions.key_up(Keys.ENTER)  # 从Keys获取按键
```

---

### 📌 `input()`

此方法用于输入一段文本或多段文本，也可输入组合键。

多段文本或组合键用列表传入。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `text` | `str` `list` `tuple` | 必填 | 要输入的文本或按键，多段文本或组合键可用`list`或`tuple`传入 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

**示例：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('https://www.baidu.com')
tab.actions.click('#kw').input('DrissionPage')
```

---

### 📌 `type()`

此方法用于以按键盘的方式输入一段或多段文本。也可输入组合键。

`type()`与`input()`区别在于前者模拟按键输入，逐个字符按下和提起，后者直接输入一整段文本。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `keys` | `str` `list` `tuple` | 必填 | 要输入的文本或按键，多段文本或组合键可用`list`或`tuple`传入 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

**示例：**

```python
# 键入一段文本
tab.actions.type('text')

# 键入多段文本
tab.actions.type(('ab', 'cd'))

# 光标向左移动一位再键入文本
tab.actions.type((Keys.LEFT, 'abc'))

# 输入快捷键
tab.actions.type(Keys.CTRL_A)
```

---

## ✅️ 拖入文件和文本

### 📌 `drag_in()`

此方法用于模拟从浏览器外部拖入文件或文本。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `ele_or_loc` | `str` `ChromiumElement` | 必填 | 接收拖动动作的元素定位符 |
| `files` | `str` `list` `tuple` | `None` | 要拖入文件路径，可多个，不为`None`时下面参数无效 |
| `text` | `str` | `None` | 要拖入的文本，`files`参数为`None`时才生效 |
| `title` | `str` | `None` | 如果`text`是超链接，可在此设置`title`，与`baseURL`互斥 |
| `baseURL` | `str` | `None` | 如果`text`是`html`，可在此设置`baseUrl`，与`title`互斥 |

| 返回类型 | 说明 |
| --- | --- |
| `Actions` | 动作链对象本身 |

---

## ✅️ 等待

### 📌 `wait()`

此方法用于等待若干秒。

`scope`为`None`时，效果与`time.sleep()`没有区别，等待指定秒数。

`scope`不为`None`时，获取两个参数之间的一个随机值，等待这个数值的秒数。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `second` | `float` | 必填 | 要等待的秒数，`scope`不为`None`时表示随机数范围起始值 |
| `scope` | `float` | `None` | 随机数范围结束值 |

**返回：**`None`

---

## ✅️ 属性

### 📌 `owner`

此属性返回使用此动作链的页面对象。

**类型：**`ChromiumBase`

---

### 📌 `curr_x`

此属性返回当前光标位置的 x 坐标。

**类型：**`int`

---

### 📌 `curr_y`

此属性返回当前光标位置的 y 坐标。

**类型：**`int`

---

## ✅️ 示例

### 📌 模拟输入 ctrl+a

```python
from DrissionPage import Chromium
from DrissionPage.common import Keys

# 创建页面对象
tab = Chromium().latest_tab

#  鼠标移动到<input>元素上
tab.actions.move_to('tag:input')
# 点击鼠标，使光标落到元素中
tab.actions.click()
# 按下 ctrl 键
tab.actions.key_down(Keys.CTRL)
# 输入 a
tab.actions.type('a')
# 提起 ctrl 键
tab.actions.key_up(Keys.CTRL)
```

链式写法：

```python
tab.actions.click('tag:input').key_down(Keys.CTRL).type('a').key_up(Keys.CTRL)
```

更简单的写法：

```python
tab.actions.click('tag:input').type(Keys.CTRL_A)
```

---

### 📌 拖拽元素

把一个元素向右拖拽 300 像素：

```python
from DrissionPage import Chromium

# 创建页面
tab = Chromium().latest_tab

# 左键按住元素
tab.actions.hold('#div1')
# 向右移动鼠标300像素
tab.actions.right(300)
# 释放左键
tab.actions.release()
```

把一个元素拖拽到另一个元素上：

```python
tab.actions.hold('#div1').release('#div2')
```

<!-- https://www.drissionpage.cn/browser_control/mode_change -->

# 🛰️ 模式切换

`MixTab`和`WebPage`有两种模式，d 模式用于控制浏览器，s 模式使用`requests`收发数据包。

两种模式访问页面和提取数据的逻辑是一致的，使用同一套 api。

每个标签页对象创建时都处于 d 模式。

使用`change_mode()`方法进行切换。模式切换的时候会同步登录信息。

s 模式下仍然可以控制浏览器，但因为共用 api，`ele()`等两种模式共用的方法，查找对象是`requests`的结果，而非浏览器。

因此 s 模式下要控制浏览器，只能调用 d 模式独有的功能。

在切换模式前已获取的元素对象则可继续操作。

Tips

切换到 s 模式后，如不再需要浏览器，可以用`close()`或`quit()`方法关闭标签页或浏览器。标签页对象继续用于收发数据包。

## ✅️️ 示例

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('http://DrissionPage.cn')
print(tab.title)  # 打印d模式下网页title
tab.change_mode()  # 切换到s模式，切换时会自动访问d模式的url
print(tab.title)  # 打印s模式下网页title
```

**输出：**

```shell
DrissionPage官网
DrissionPage官网
```

---

## ✅️️ 相关属性和方法

### 📌️ `mode`

此属性返回当前模式。`'d'`或`'s'`。

**类型：**`str`

---

### 📌 `change_mode()`

此方法用于切换运行模式。

切换模式时默认复制当前 cookies 到目标模式，且使用当前 url 进行跳转。

注意

切换模式时只同步 cookies，不同步 headers，如果网站要求特定的 headers 才能访问，就会卡住直到超时。
这时可以设置`go`为`False`，切换 s 模式后再自己构造 headers 访问。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `mode` | `str` `None` | `None` | 接收`'s'`或`'d'`，以切换到指定模式 接收`None`则切换到与当前相对的另一个模式 |
| `go` | `bool` | `True` | 目标模式是否跳转到原模式的 url |
| `copy_cookies` | `bool` | `True` | 切换时是否复制 cookies 到目标模式 |

**返回：**`None`

---

### 📌 `cookies_to_session()`

此方法用于复制浏览器当前页面的 cookies 到`Session`对象。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `copy_user_agent` | `bool` | `True` | 是否复制 user agent 信息 |

**返回：**`None`

### 📌 `cookies_to_browser()`

此方法用于把`Session`对象的 cookies 复制到浏览器。

**参数：** 无

**返回：**`None`

---

## ✅️️ 说明

- 主要的 api 两种模式是共用的，如`get()`，d 模式下控制浏览跳转，s 模式下控制`Session`对象跳转
- s 模式下获取的元素对象为`SessionElement`，d 模式下为`ChromiumElement`等
- `post()`方法无论在哪种模式下都能使用
- s 模式下也能控制浏览器，但只能使用 d 模式独有功能控制

---

<!-- https://www.drissionpage.cn/browser_control/waiting -->

# 🛰️ 等待

网络环境不稳定，页面 js 运行时间也难以确定，自动化过程中经常遇到需要等待的情况。

如果总是用`sleep()`，显得不太优雅，等待多了浪费时间，等待不够会导致报错。

因此，程序能够智能等待是非常重要的，DrissionPage 内置了一些等待方法，可以提高程序稳定性和效率。

它们藏在页面对象和元素对象的`wait`属性里。

等待方法均有`timeout`参数，可自行设得超时时间，也可以设置超时后返回`False`还是抛出异常。

## ✅️️ 浏览器对象的等待方法

### 📌 `wait.new_tab()`

此方法用于等待新标签页出现。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`时使用页面`timeout`设置 |
| `curr_tab` | `str` `ChromiumTab` `MixTab` | `None` | 指定当前最新的 Tab 对象或标签页 id，用于判断新标签页出现，为`None`自动获取 |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 等待成返回新标签页 id |
| `False` | 等待失败返回`False` |

---

### 📌 `wait.download_begin()`

此方法用于等待浏览器一个下载任务开始，详见下载功能章节。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`时使用页面`timeout`设置 |
| `cancel_it` | `bool` | `False` | 是否取消该任务 |

| 返回类型 | 说明 |
| --- | --- |
| `DownloadMission` | 等待成功返回下载任务对象 |
| `False` | 等待失败 |

**示例：**

```python
tab('#download_btn').click()  # 点击按钮触发下载
tab.wait.download_begin()  # 等待下载开始
```

---

### 📌 `wait.downloads_done()`

此方法用于等待浏览器所有下载任务完成，详见下载功能章节。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`时无限等待 |
| `cancel_if_timeout` | `bool` | `True` | 超时时是否取消剩余任务 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否等待成功 |

---

## ✅️️ 页面对象的等待方法

页面对象指`ChromiumTab`、`MixTab`和`ChromiumFrame`。

**用法：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('http://DrissionPage.cn')
tab.wait.ele_displayed('tag:div')
```

### 📌 `wait.load_start()`

此方法用于等待页面进入加载状态。
我们经常会通过点击元素进入下一个网页，并立刻获取新页面的元素。
但若跳转前的页面拥有和跳转后页面相同定位符的元素，会导致过早获取元素，跳转后失效的问题。
使用此方法，会阻塞程序，等待页面开始加载后再继续，从而避免上述问题。
我们通常只需等待页面加载开始，程序会自动等待加载结束。

注意

`get()`已内置等待加载开始，后无须跟`wait.load_start()`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` `None` `True` | `None` | 超时时间（秒），为`None`或`Ture`时使用页面`timeout`设置 为数字时等待相应时间 |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 等待结束时是否进入加载状态 |

**示例：**

```python
ele.click()  # 点击某个元素
tab.wait.load_start()  # 等待页面进入加载状态
# 执行在新页面的操作
print(page.title)
```

---

### 📌 `wait.doc_loaded()`

此方法用于等待页面文档加载完成。
一般来说都无需开发者使用，程序大部分动作都会自动等待加载完成再执行。

注意

- 此功能仅用于等待页面主 document 加载，不能用于等待 js 加载的变化。
- 除非`load_mode`为`None`，`get()`方法已内置等待加载完成，后面无须添加等待。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` `None` `True` | `None` | 超时时间（秒），为`None`或`Ture`时使用页面`timeout`设置 为数字时等待相应时间 |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 等待结束时是否完成加载完成 |

---

### 📌 `wait.eles_loaded()`

此方法用于等待元素被加载到 DOM，可等待全部或任意一个加载。
有时一个元素的正常出现是下一步操作的前提，用此方法可以防止一些元素加载速度慢于程序动作速度导致的误操作。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` `list` | 必填 | 要等待的元素，定位符 |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`时使用页面`timeout`设置 |
| `any_one` | `bool` | `False` | 是否等待到一个就返回 |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否等待成功 |

**示例：**

```python
ele1.click()  # 点击某个元素
page.wait.eles_loaded('#div1')  # 等待 id 为 div1 的元素加载
ele2.click()  # div1 加载完成后再执行下一步操作
```

---

### 📌 `wait.ele_displayed()`

此方法用于等待一个元素变成显示状态。
如果当前 DOM 中查找不到指定元素，则会自动等待元素加载，再等待它显示。
元素隐藏是指元素在 DOM 内，但处于隐藏状态（即使在视口内且不被遮挡）。
父元素隐藏时子元素也是隐藏的。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `loc_or_ele` | `str` `Tuple[str, str]` `ChromiumElement` | 必填 | 要等待的元素，可以是元素或定位符 |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`时使用页面`timeout`设置 |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否等待成功 |

**示例：**

```python
# 等待 id 为 div1 的元素显示，超时使用页面设置
tab.wait.ele_displayed('#div1')

# 等待 id 为 div1 的元素显示，设置超时3秒
tab.wait.ele_displayed('#div1', timeout=3)

# 等待已获取到的元素被显示
ele = tab.ele('#div1')
tab.wait.ele_displayed(ele)
```

---

### 📌 `wait.ele_hidden()`

此方法用于等待一个元素变成隐藏状态。
如果当前 DOM 中查找不到指定元素，则会自动等待元素加载，再等待它隐藏。
元素隐藏是指元素在 DOM 内，但处于隐藏状态（即使在视口内且不被遮挡）。
父元素隐藏时子元素也是隐藏的。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `loc_or_ele` | `str` `Tuple[str, str]` `ChromiumElement` | 必填 | 要等待的元素，可以是元素或定位符 |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`时使用页面`timeout`设置 |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否等待成功 |

---

### 📌 `wait.ele_deleted()`

此方法用于等待一个元素被从 DOM 中删除。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `loc_or_ele` | `str` `Tuple[str, str]` `ChromiumElement` | 必填 | 要等待的元素，可以是元素或定位符 |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`时使用页面`timeout`设置 |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否等待成功 |

---

### 📌 `wait.download_begin()`

此方法用于等待下载开始，详见下载功能章节。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`时使用页面`timeout`设置 |
| `cancel_it` | `bool` | `False` | 是否取消该任务 |

| 返回类型 | 说明 |
| --- | --- |
| `DownloadMission` | 等待成功返回下载任务对象 |
| `False` | 等待失败 |

**示例：**

```python
tab('#download_btn').click()  # 点击按钮触发下载
tab.wait.download_begin()  # 等待下载开始
```

---

### 📌 `wait.downloads_done()`

此方法用于等待本标签页所有下载任务完成，详见下载功能章节。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`时无限等待 |
| `cancel_if_timeout` | `bool` | `True` | 超时时是否取消剩余任务 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumTab` | `ChromiumTab`对象等待成功返回自己 |
| `MixTab` | `MixTab`对象等待成功返回自己 |
| `False` | 等待失败 |

---

### 📌 `wait.upload_paths_inputted()`

此方法用于等待自动填写上传文件路径。详见文件上传章节。

**参数：** 无

**返回：**`None`

**示例：**

```python
# 设置要上传的文件路径
tab.set.upload_files('demo.txt')
# 点击触发文件选择框按钮
btn_ele.click()
# 等待路径填入
tab.wait.upload_paths_inputted()
```

---

### 📌 `wait.title_change()`

此方法用于等待 title 变成包含或不包含指定文本。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `text` | `str` | 必填 | 用于识别的文本 |
| `exclude` | `bool` | `False` | 是否排除，为`True`时当 title 不包含`text`指定文本时返回`True` |
| `timeout` | `bool` | `float` | 超时时间（秒） |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumTab` | 等待成功`ChromiumTab`对象返回自身 |
| `MixTab` | 等待成功`MixTab`对象返回自身 |
| `ChromiumFrame` | `<iframe>`元素的等待返回对象自身 |
| `False` | 等待失败 |

---

### 📌 `wait.url_change()`

此方法用于等待 url 变成包含或不包含指定文本。
比如有些网站登录时会进行多重跳转，url 发生多次变化，可用此功能等待到达最终需要的页面。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `text` | `str` | 必填 | 用于识别的文本 |
| `exclude` | `bool` | `False` | 是否排除，为`True`时当 url 不包含`text`指定文本时返回`True` |
| `timeout` | `bool` | `float` | 超时时间（秒） |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返 回类型 | 说明 |
| --- | --- |
| `ChromiumTab` | 等待成功`ChromiumTab`对象返回自身 |
| `MixTab` | 等待成功`MixTab`对象返回自身 |
| `ChromiumFrame` | `<iframe>`元素的等待返回对象自身 |
| `False` | 等待失败 |

**示例：**

```python
# 访问网站
tab.get('https://www.*****.cn/login/')  # 访问登录页面
tab.ele('#username').input('***')  # 执行登录逻辑
tab.ele('#password').input('***\n')

tab.wait.url_change('https://www.*****.cn/center/')  # 等待url变成后台url
```

---

### 📌 `wait.alert_closed()`

此方法用于等待弹出框被关闭。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `bool` | `float` | 超时时间（秒），为`None`无限等待 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumTab` | 等待成功`ChromiumTab`对象返回自身 |
| `MixTab` | 等待成功`MixTab`对象返回自身 |
| `False` | 等待失败 |

---

---

## ✅️️ 元素对象的等待方法

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('http://DrissionPage.cn')
ele = tab('tag:div')
ele.wait.covered()
```

### 📌 `wait.displayed()`

此方法用于等待元素从隐藏状态变成显示状态。
元素隐藏是指元素在 DOM 内，但处于隐藏状态（即使在视口内且不被遮挡）。父元素隐藏时子元素也是隐藏的。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 等待超时时间（秒），为`None`则使用元素所在页面超时时间 |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 元素对象自身 |
| `ChromiumFrame` | `<iframe>`元素的等待返回对象自身 |
| `False` | 等待失败 |

**示例：**

```python
# 等待元素显示，超时使用ele所在页面设置
ele.wait.displayed()
```

---

### 📌 `wait.hidden()`

此方法用于等待元素从显示状态变成隐藏状态。
元素隐藏是指元素在 DOM 内，但处于隐藏状态（即使在视口内且不被遮挡）。父元素隐藏时子元素也是隐藏的。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 等待超时时间（秒），为`None`则使用元素所在页面超时时间 |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 元素对象自身 |
| `ChromiumFrame` | `<iframe>`元素的等待返回对象自身 |
| `False` | 等待失败 |

**示例：**

```python
# 等待元素不显示，超时为3秒
ele.wait.hidden(timeout=3)
```

---

### 📌 `wait.deleted()`

此方法用于等待元素被从 DOM 删除。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 等待超时时间（秒），为`None`则使用元素所在页面超时时间 |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 元素对象自身 |
| `ChromiumFrame` | `<iframe>`元素的等待返回对象自身 |
| `False` | 等待失败 |

**示例：**

```python
# 等待元素显示，超时使用ele所在页面设置
ele.wait.deleted()
```

---

### 📌 `wait.has_rect()`

此方法用于等待元素被赋予大小。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 等待超时时间（秒），为`None`则使用元素所在页面超时时间 |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 元素对象自身 |
| `ChromiumFrame` | `<iframe>`元素的等待返回对象自身 |
| `False` | 等待失败 |

---

### 📌 `wait.covered()`

此方法用于等待元素被其它元素覆盖。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 等待超时时间（秒），为`None`则使用元素所在页面超时时间 |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 元素对象自身 |
| `ChromiumFrame` | `<iframe>`元素的等待返回对象自身 |
| `False` | 等待失败 |

---

### 📌 `wait.not_covered()`

此方法用于等待元素不被其它元素覆盖。
可用于等待遮挡被操作元素的“加载中”遮罩消失。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 等待超时时间（秒），为`None`则使用元素所在页面超时时间 |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 元素对象自身 |
| `ChromiumFrame` | `<iframe>`元素的等待返回对象自身 |
| `False` | 等待失败 |

---

### 📌 `wait.enabled()`

此方法用于等待元素变为可用状态。
不可用状态的元素仍然在 DOM 内，`disabled`属性为`False`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 等待超时时间（秒），为`None`则使用元素所在页面超时时间 |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 元素对象自身 |
| `ChromiumFrame` | `<iframe>`元素的等待返回对象自身 |
| `False` | 等待失败 |

---

### 📌 `wait.disabled()`

此方法用于等待元素变为不可用状态。
不可用状态的元素仍然在 DOM 内，`disabled`属性为`True`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 等待超时时间（秒），为`None`则使用元素所在页面超时时间 |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 元素对象自身 |
| `ChromiumFrame` | `<iframe>`元素的等待返回对象自身 |
| `False` | 等待失败 |

---

### 📌 `wait.stop_moving()`

此方法用于等待元素运动结束。如果元素没有大小和位置信息，会在超时时抛出`NoRectError`异常。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 等待超时时间（秒），为`None`则使用元素所在页面超时时间 |
| `gap` | `float` | `0.1` | 检测运动的间隔时间 |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 元素对象自身 |
| `ChromiumFrame` | `<iframe>`元素的等待返回对象自身 |
| `False` | 等待失败 |

```python
# 等待元素稳定
tab.ele('#button1').wait.stop_moving()
# 点击元素
tab.ele('#button1').click()
```

---

### 📌 `wait.clickable()`

此方法用于等待元素可被点击。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `wait_moved` | `bool` | `True` | 是否等待元素运动结束 |
| `timeout` | `float` | `None` | 等待超时时间（秒），为`None`则使用元素所在页面超时时间 |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 元素对象自身 |
| `ChromiumFrame` | `<iframe>`元素的等待返回对象自身 |
| `False` | 等待失败 |

---

### 📌 `wait.disabled_or_deleted()`

此方法用于等待元素变为不可用或被删除。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 等待超时时间（秒），为`None`则使用元素所在页面超时时间 |
| `raise_err` | `bool` | `None` | 等待失败时是否报错，为`None`时根据`Settings`设置 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否等待成功 |

---

## ✅️️ 共有的等待方法

### 📌 `wait()`

此方法用于等待若干秒。所有对象的等待都可使用这个方法。
`scope`为`None`时，效果与`time.sleep()`没有区别，等待指定秒数。
`scope`不为`None`时，获取两个参数之间的一个随机值，等待这个数值的秒数。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `second` | `float` | 必填 | 要等待的秒数，`scope`不为`None`时表示随机数范围起始值 |
| `scope` | `float` | `None` | 随机数范围结束值 |

**返回：** 调用者自身

**示例：**

```python
from DrissionPage import Chromium

browser = Chromium()

# 强制等待1秒
browser.wait(1)

# 获取3.5至8.5之间的一个随机数，等待这个数值的秒数
browser.wait(3.5, 8.5)
```

<!-- https://www.drissionpage.cn/browser_control/listener -->

# 🛰️ 监听网络数据

许多网页的数据来自接口，在网站使用过程中动态加载，如使用 JS 加载内容的翻页列表。

这些数据通常以 json 形式发送，浏览器接收后，对其进行解析，再加载到 DOM 相应位置。

做数据采集的时候，我们往往从 DOM 中去获取解析后数据的，可能存在数据不全、加载响应不及时、难以判断加载完成等问题。

如果我们可以拿到浏览器收发的数据包，根据数据包状态判断下一步操作，甚至直接获取数据，岂不是爽爆了？

DrissionPage 每个页面对象（包括 Tab 和 Frame 对象）内置了一个监听器，专门用于抓取浏览器数据包。

可以提供等待和捕获指定数据包，实时返回指定数据包功能。

## ✅️ 示例

先看两个示例了解监听器工作方式。

注意

要先启动监听，再执行动作，`listen.start()`之前的数据包是获取不到的。

### 📌 等待并获取

点击下一页，等待数据包，再点击下一页，循环。

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('https://gitee.com/explore/all')  # 访问网  址，这行产生的数据包不监听

tab.listen.start('gitee.com/explore')  # 开始监听，指定获取包含该文本的数据包
for _ in range(5):
    tab('@rel=next').click()  # 点击下一页
    res = tab.listen.wait()  # 等待并获取一个数据包
    print(res.url)  # 打印数据包url
```

**输出：**

```shell
https://gitee.com/explore/all?page=2
https://gitee.com/explore/all?page=3
https://gitee.com/explore/all?page=4
https://gitee.com/explore/all?page=5
https://gitee.com/explore/all?page=6
```

---

### 📌 实时获取

跟上一个示例做同样的事情，不过换一种方式。

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.listen.start('gitee.com/explore')  # 开始监听，指定获取包含该文本的数据包
tab.get('https://gitee.com/explore/all')  # 访问网址

i = 0
for packet in tab.listen.steps():
    print(packet.url)  # 打印数据包url
    tab('@rel=next').click()  # 点击下一页
    i += 1
    if i == 5:
        break
```

---

## ✅️ 设置目标和启动监听

### 📌 `listen.start()`

此方法用于启动监听器，启动同时可设置获取的目标特征。

可设置多个特征，符合条件的数据包会被获取。

如果监听未停止时调用这个方法，可清除已抓取的队列。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `targets` | `str` `list` `tuple` `set` | `None` | 要匹配的数据包 url 特征，可用列表指定多个，为`True`时获取所有 |
| `is_regex` | `bool` | `None` | 设置的 target 是否正则 表达式，为`None`时保持原来设置 |
| `method` | `str` `list` `tuple` `set` | `None` | 设置监听的请求类型，可指定多个，默认`('GET', 'POST')`，为`True`时监听所有，为`None`时保持原来设置 |
| `res_type` | `str` `list` `tuple` `set` | `None` | 设置监听的 ResourceType 类型，可指定多个，为`True`时监听所有，为`None`时保持原来设置 |

**返回：** `None`

注意

当`targets`不为`None`，`is_regex`会自动设为`False`。
即如要使用正则，每次设置`targets`时需显式指定`is_regex=True`。

---

### 📌 `listen.set_targets()`

此方法可在监听过程中修改监听目标，也可在监听开 始前设置。

如监听未启动，不会启动监听。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `targets` | `str` `list` `tuple` `set` | `True` | 要匹配的数据包 url 特征，可用列表指定多个，为`True`时获取所有 |
| `is_regex` | `bool` | `False` | 设置的 target 是否正则表达式 |
| `method` | `str` `list` `tuple` `set` | `('GET', 'POST')` | 设置监听的请求类型，可指定多个，默认`('GET', 'POST')`，为`True`时监听所有 |
| `res_type` | `str` `list` `tuple` `set` | `True` | 设置监听的 ResourceType 类型，可指定多个，为`True`时监听所有 |

**返回：** `None`

---

## ✅️ 等待和获取数据包

### 📌 `listen.wait()`

此方法用于等待符合要求的数据包到达指定数量。

所有符合条件的数据包都会存储到队列，`wait()`实际上是逐个从队列中取结果，不用担心页面已刷走而丢包。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `count` | `int` | `1` | 需要捕捉的数据包数量 |
| `timeout` | `float` `None` | `None` | 超时时间（秒），为`None`无限等待 |
| `fit_count` | `bool` | `True` | 是否必需满足总数要求，如超时，为`True`返回`False`，为`False`返回已捕捉到的数据包 |
| `raise_err` | `bool` | `None` | 超时时是否抛出错误，为`None`时根据`Settings`设置，如不抛出，超时返回`False` |

| 返回类型 | 说明 |
| --- | --- |
| `DataPacket` | `count`为`1`且未超时，返回一个数据包对象 |
| `List[DataPacket]` | `count`大于`1`，未超时或`fit_count`为`False`，返回数据包对象组成的列表 |
| `False` | 超时且`fit_count`为`True`时 |

---

### 📌 `listen.steps()`

此方法返回一个可迭代对象，用于`for`循环，每次循环可从中获取到的数据包。

可实现实时获取并返回数据包。

如果`timeout`超时，会中断循环。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `count` | `int` | `None` | 需捕获的数据包总数，为`None`表示无限 |
| `timeout` | `float` `None` | `None` | 每个数据包等待时间（秒），为`None`表示无限等待 |
| `gap` | `int` | `1` | 每接收到多少个数据包返回一次数据 |

| 返回类型 | 说明 |
| --- | --- |
| `DataPacket` | `gap`为`1`时，返回一个数据包对象 |
| `List[DataPacket]` | `gap`大于`1`，返回数据包对象组成的列表 |

---

### 📌 `listen.wait_silent()`

此方法用于等待所有指定的请求完成。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` `None` | `None` | 等待时间（秒），为`None`表示无限等待 |
| `targets_only` | `bool` | `False` | 是否只等待`targets`指定的请求结束 |
| `limit` | `int` | `0` | 剩下多少个连接时视为结束 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否等待成功 |

---

## ✅️ 暂停和恢复

### 📌 `listen.pause()`

此方法用于暂停监听。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `clear` | `bool` | `True` | 是否清空已获取队列 |

**返回：** `None`

---

### 📌 `listen.resume()`

此方法用于继续暂停的监听。

**参数：** 无

**返回：**`None`

---

### 📌 `listen.stop()`

此方法用于终止监听器的运行，会清空已获取的队列，不清空 targets。

**参数：** 无

**返回：**`None`

---

## ✅️ `DataPacket`对象

`DataPacket`对象是获取到的数据包结果对象，包含了数据包各种信息。

### 📌 `对象属性`

| 属性名称 | 数据类型 | 说明 |
| --- | --- | --- |
| `tab_id` | `str` | 产生这个请求的标签页的 id |
| `frameId` | `str` | 产生这个请求的框架 id |
| `target` | `str` | 产生这个请求的监听目标 |
| `url` | `str` | 数据包请求网址 |
| `method` | `str` | 请求类型 |
| `is_failed` | `bool` | 是否连接失败 |
| `resourceType` | `str` | 资源类型 |
| `request` | `Request` | 保存请求信息的对象 |
| `response` | `Response` | 保存响应信息的对象 |
| `fail_info` | `FailInof` | 保存连接失败信息的对象 |

### 📌 `wait_extra_info()`

有些数据包有`extra_info`数据，但这些数据可能会迟于数据包返回，用这个方法可以等待这些数据加载到数据包对象。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` `None` | `None` | 超时时间（秒），`None`为无限等待 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否等待成功 |

### 📌 `Request`对象

`Request`对象是`DataPacket`对象内用于保存请求信息的对象，有以下属性：

| 属性名称 | 数据类型 | 说明 |
| --- | --- | --- |
| `url` | `str` | 请求的网址 |
| `method` | `str` | 请求类型 |
| `params` | `dict` | 以`dict`格式返回 url 中的参数 |
| `headers` | `CaseInsensitiveDict` | 以大小写不敏感字典返回 headers 数据 |
| `cookies` | `List[dict]` | 返回发送的 cookies |
| `postData` | `str` `dict` | post 类型的请求所提交的数据，json 以`dict`格式返回 |

除以上常用属性，还有以下属 性，自行体会：

urlFragment、hasPostData、postDataEntries、mixedContentType、initialPriority、referrerPolicy、isLinkPreload、trustTokenParams、isSameSite

---

### 📌 `Response`对象

`Response`对象是`DataPacket`对象内用于保存响应信息的对象，有以下属性：

| 属性名称 | 数据类型 | 说明 |
| --- | --- | --- |
| `url` | `str` | 请求的网址 |
| `headers` | `CaseInsensitiveDict` | 以大小写不敏感字典返回 headers 数据 |
| `body` | `str` `bytes` `dict` | 如果是 json 格式，转换为`dict`；如果是 base64 格式，转换为`bytes`，其它格式直接返回文本 |
| `raw_body` | `str` | 未被处理的 body 文本 |
| `status` | `int` | 请求状态 |
| `statusText` | `str` | 请求状态文本 |

除以上属性，还有以下属性，自行体会：

headersText、mimeType、requestHeaders、requestHeadersText、connectionReused、connectionId、remoteIPAddress、remotePort、fromDiskCache、fromServiceWorker、fromPrefetchCache、encodedDataLength、timing、serviceWorkerResponseSource、responseTime、cacheStorageCacheName、protocol、alternateProtocolUsage、securityState、securityDetails

---

### 📌 `FailInfo`对象

`FailInfo`对象是`DataPacket`对象内用于保存连接失败信息的对象，有以下属性：

| 属性名称 | 数据类型 | 说明 |
| --- | --- | --- |
| `errorText` | `str` | 错误信息文本 |
| `canceled` | `bool` | 是否取消 |
| `blockedReason` | `str` | 拦截原因 |
| `corsErrorStatus` | `str` | cors 错误状态 |

<!-- https://www.drissionpage.cn/browser_control/console -->

# 🛰️ 获取控制台信息

获取控制台信息的逻辑和监听网络数据差不多，是通过监听控制台数据实现的。

注意

不是所有显示在控制台的信息都能获取，需要用`console.log()`等方法输出到控制台的才能获取。

## ✅️ 示例

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.console.start()
tab.run_js('console.log("DrissionPage");')
data = tab.console.wait()
print(data.text)  # 输出：DrissionPage
```

---

## ✅️ 启动和停止

### 📌 `console.start()`

此方法用于启动控制台信息监听。

**参数：** 无

**返回：**`None`

---

### 📌 `console.stop()`

此方法用于停止监听，清空已监听到的信息列表。

**参数：** 无

**返回：**`None`

---

## ✅️ 获取信息

### 📌 `console.wait()`

此方法用于等待一条控制台信息。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` `None` | `None` | 超时时间（秒），为`None`无限等待 |

| 返回类型 | 说明 |
| --- | --- |
| `ConsoleData` | 控制台信息数据包对象 |
| `False` | 等待超时时 |

---

### 📌 `console.steps()`

此方法返回一个可迭代对象，用于`for`循环，每次循环可从中获取到的信息。

可实现实时获取并返回数据包。

如果`timeout`超时，会中断循环。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` `None` | `None` | 每个信息等待时间（秒），为`None`表示无限等待 |

| 返回类型 | 说明 |
| --- | --- |
| `ConsoleData` | 控制台信息数据包对象 |

---

### 📌 `console.messages`

此属性以`list`方式返回获取到的信息，返回后会清空列表。

| 返回类型 | 说明 |
| --- | --- |
| `List[ConsoleData]` | 控制台信息对象组成的列表 |

---

## ✅️ 其它

### 📌 `console.listening`

此属性返回监听是否进行中。

**返回：** `bool`

---

### 📌 `console.clear()`

此方法用于清空已获取但未返回的信息。

**参数：** 无

**返回：**`None`

---

## ✅️ `ConsoleData`对象

`ConsoleData`对象是获取到的数据包结果对象，包含了数据包各种信息。

### 📌 `对象属性`

| 属性名称 | 数据类型 | 说明 |
| --- | --- | --- |
| `source` | `str` | 来源 |
| `level` | `str` | 类型 |
| `text` | `str` | 内容文本 |
| `body` | `Any` | 把`text`进行 json 解析 |
| `url` | `str` | 网址 |
| `line` | `str` | 行号 |
| `column` | `str` | 列号 |

<!-- https://www.drissionpage.cn/browser_control/screen -->

# 🛰️ 截图和录像

## ✅️️ 页面截图

使用页面对象的`get_screenshot()`方法对页面进行截图，可对整个网页、可见网页、指定范围截图。

对可视范围外截图需要 90 以上版本浏览器支持。

下面三个参数三选一，优先级：`as_bytes`>`as_base64`>`path`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `path` | `str` `Path` | `None` | 保存图片的路径，为`None`时保存在当前文件夹 |
| `name` | `str` | `None` | 完整文件名，后缀可选`'jpg'`、`'jpeg'`、`'png'`、`'webp'`，为`None`时以用 jpg 格式 |
| `as_bytes` | `str` `True` | `None` | 是否以字节形式返回图片，可选`'jpg'`、`'jpeg'`、`'png'`、`'webp'`、`None`、`True` 不为`None`时`path`参数无效 为`True`时选用 jpg 格式 |
| `as_base64` | `str` `True` | `None` | 是否以 base64 形式返回图片，可选`'jpg'`、`'jpeg'`、`'png'`、`'webp'`、`None`、`True` 不为`None`时`path`参数无效 为`True`时选用 jpg 格式 |
| `full_page` | `bool` | `False` | 是否整页截图，为`True`截取整个网页，为`False`截取可视窗口 |
| `left_top` | `Tuple[int, int]` | `None` | 截取范围左上角坐标 |
| `right_bottom` | `Tuple[int, int]` | `None` | 截取范围右下角坐标 |

| 返回类型 | 说明 |
| --- | --- |
| `bytes` | `as_bytes`生效时返回图片字节 |
| `str` | `as_bytes`和`as_base64`为`None`时返回图片完整路径 |
| `str` | `as_base64`生效时返回 base64 格式的字符串 |

说明

如`path`为包含文件名的完整路径，`name`参数无效。

**示例：**

```python
# 对整页截图并保存
tab.get_screenshot(path='tmp', name='pic.jpg', full_page=True)
```

制" class="clean-btn">

## ️️ ✅️️ 元素截图

使用元素对象的`get_screenshot()`方法对元素进行截图。

若元素范围超出视口，需 90 以上版本内核支持。

下面三个参数三选一，优先级：`as_bytes`>`as_base64`>`path`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `path` | `str` `Path` | `None` | 保存图片的路径，为`None`时保存在当前文件夹 |
| `name` | `str` | `None` | 完整文件名，后缀可选`'jpg'`、`'jpeg'`、`'png'`、`'webp'`，为`None`时以用 jpg 格式 |
| `as_bytes` | `str` `True` | `None` | 是否以字节形式返回图片，可选`'jpg'`、`'jpeg'`、`'png'`、`'webp'`、`None`、`True` 不为`None`时`path`和`as_base64`参数无效 为`True`时选用 jpg 格式 |
| `as_base64` | `str` `True` | `None` | 是否以 base64 形式返回图片，可选`'jpg'`、`'jpeg'`、`'png'`、`'webp'`、`None`、`True` 不为`None`时`path`参数无效 为`True`时选用 jpg 格式 |
| `scroll_to_center` | `bool` | `True` | 截图前是否滚动到视口中央 |

| 返回类型 | 说明 |
| --- | --- |
| `bytes` | `as_bytes`生效时返回图片字节 |
| `str` | `as_bytes`和`as_base64`为`None`时返回图片完整路径 |
| `str` | `as_base64`生效时返回 base64 格式的字符串 |

说明

如`path`为包含文件名的完整路径，`name`参数无效。

**示例：**

```python
img = tab('tag:img')
img.get_screenshot()
bytes_str = img.get_screenshot(as_bytes='png')  #   返回截图二进制文本
```

---

## ✅️️ 页面录像

使用页面对象的`screencast`功能，可以录取屏幕图片或视频。

### 📌 设置录制模式

录制模式一共有 5 种，通过`screencast.set_mode.xxx_mode()`设置。

| 模式 | 说明 |
| --- | --- |
| `video_mode()` | 持续录制页面，停止时生成没有声音的视频 |
| `frugal_video_mode()` | 页面有变化时才录制，停止时生成没有声音的视频 |
| `js_video_mode()` | 可生成有声音的视频，但需要手动启动 |
| `imgs_mode()` | 持续对页面进行截图 |
| `frugal_imgs_mode()` | 页面有变化时才保存页面图像 |

### 📌 设置存放路径

使用`screencast.set_save_path()`设置录制结果保存路径。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `save_path` | `str` `Path` | `None` | 保存图片或视频的路径 |

**返回：**`None`

### 📌 `screencast.start()`

此方法用于开始录制浏览器窗口。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `save_path` | `str` `Path` | `None` | 保存图片或视频的路径 |

**返回：**`None`

注意

保存路径必需设置，无论是用`screencast.set()`还是`screencast.start()`都可以。

### 📌 `screencast.stop()`

此方法用于停止录取屏幕。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `video_name` | `str` | `None` | 视频文件名，为`None`时以当前时间名命 |
| `suffix` | `str` | `'mp4'` | 视频文件后缀 |
| `coding` | `str` | `'mp4v'` | 视频编码格式，仅`video_mode`模式有效，根据`cv2.VideoWriter_fourcc()`定义 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 保存为视频时返回视频文件路径，否则返回保存图片的文件夹路径 |

### 📌 注意事项

- 使用`video_mode`和`frugal_video_mode`时，保存路径和保存文件名必需是英文。
- 使用`video_mode`和`frugal_video_mode`时，需先安装 opencv 库。`pip install opencv-python`
- 使用`js_video_mode`时，需用鼠标手动选择要录制的目标，才能开始录制
- 使用`js_video_mode`时，如要对一个窗口进行录制，需在另一个窗口开始录制，否则如窗口出现跳转，会使录制失效

### 📌 示例

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.screencast.set_save_path('video')  # 设置视频存放路径
tab.screencast.set_mode.video_mode()  # 设置录制
tab.screencast.start()  # 开始录制
tab.wait(3)
tab.screencast.stop()  # 停止录制
```

<!-- https://www.drissionpage.cn/browser_control/upload -->

# 🛰️ 上传文件

上传文件有两种方式：

- 拦截文件输入框，自动填入路径
- 找到`<input>`元素，填入文件路径

## ✅️️ 自然的交互

传统自动化工具的文件上传，需要开发者在 DOM 里找到文件上传控件，然后用元素对象的`input()`方法填入路径。

有些上传控件是临时加载的，有些藏得很深，找起来费时费力。

本库提供一种自然的文件上传方式，无需在 DOM 里找控件，只要自然地点击触发文件选择框，程序就能主动截获，并填写设定好的路径，开发更省事。

### 📌 `click.to_upload()`

浏览器元素对象拥有此方法，用于上传文件到网页。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `file_paths` | `str` `Path` `list` `tuple` | 必填 | 文件路径，如果上传框支持多文件，可传入列表或字符串，字符串时多个文件用`\n`分隔 |
| `by_js` | `bool` | `False` | 是否用 js 方式点击，逻辑与`click()`一致 |

**返回：**`None`

**示例**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
ele = tab('#uploadButton')
ele.click.to_upload(r'C:\text.txt')
```

---

### 📌 手动方式

上面的方法使用默认点击方式触发上传，假如页面要求其它触发方式，可自行手动写上传逻辑。

**步骤：**

- 设置要上传的文件路径，多路径传入`list`、`tuple`或以`\n`分隔的字符串
- 点击会触发文件选择框的按钮
- 调用等待录入语句，确保输入完整

**示例：**

```python
# 设置要上传的文件路径
tab.set.upload_files('demo.txt')
# 点击触发文件选择框按钮
btn_ele.click()
# 等待路径填入
tab.wait.upload_paths_inputted()
```

点击按钮后，文本选择框被拦截不会弹出，但可以看到文件路径已经传入其中。

由于此动作是异步输入，需显式等待输入完成才进行下一步操作。

---

### 📌 注意事项

如果您要操作的上传控件在一个异域的`<iframe>`，那必需用这个`<iframe>`对象来设置上传路径，而不能用页面对象设置。

❌ 错误做法：

```python
tab.set.upload_paths('demo.txt')
tab.get_frame(1).ele('@type=file').click()
tab.wait.upload_paths_inputted()
```

⭕ 正确做法：

```python
iframe = tab.get_frame(1)
iframe.set.upload_paths('demo.txt')
iframe.ele('@type=file').click()
iframe.wait.upload_paths_inputted()
```

如果`<iframe>`和主页面是同域的，则用域名对象和`<iframe>`对象设置均可。

---

## ✅️️ 传统方式

传统方式，需要 开发者在 DOM 里找到文件上传控件，然后用元素对象的`input()`方法填入路径。

文件上传控件是`type`属性为`'file'`的`<input>`元素进行输入，把文件路径输入到元素即可，用法与输入文本一致。

稍有不同的是，无论`clear`参数是什么，都会清空原控件内容。

如果控件支持多文件上传，多个路径用`list`、`tuple`或以`\n`分隔的字符串传入。

```python
upload = tab('tag:input@type=file')

# 传入一个路径
upload.input('D:\\test1.txt')

# 传入多个路径，方式 1
paths = 'D:\\test1.txt\nD:\\test2.txt'
upload.input(paths)

# 传入多个路径，方式 2
paths = ['D:\\test1.txt', 'D:\\test2.txt']
upload.input(paths)
```

如果`<input>`元素很好找，这种方式是很简便的。

有些`<input>`是临时加载的，或者经过修饰隐藏很深，找起来很费劲。

万一有些上传是用 js 控制的，这种方式未必能奏效。

<!-- https://www.drissionpage.cn/browser_control/pages -->

# 🛰️ Page 对象

`ChromiumPage`和`WebPage`是 4.1 之前用于连接和控制浏览器的对象。

4.1 这些功能由`Chromium`实现，但`ChromiumPage`和`WebPage`仍能正常使用。

对比`Chromium`，`ChromiumPage`和`WebPage`在连接浏览器时可以少写一行代码，但在多标签页操作的时候容易造成混乱。

更详细的用法可以看旧版文档。

## ✅️️ `ChromiumPage`

`ChromiumPage`把浏览器管理功能和一个标签页（默认接管时激活那个）控制功能整合在一起。

可看作浏览器对象，但同时控制了一个标签页。

如果项目只需要使用单标签页，用`ChromiumPage`会比较方便。

`ChromiumPage`创建的标签页对象为`ChromiumTab`，没有切换模式功能。

| 初始化参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `addr_or_opts` | `str` `int` `ChromiumOptions` | `None` | 浏览器启动配置或接管信息。 传入 'ip: port' 字符串、端口数字或`ChromiumOptions`对象时按配置启动或接管浏览器； 为`None`时使用配置文件配置启动浏览器 |
| `tab_id` | `str` | `None` | 要控制的标签页 id，不指定默认为激活的 |

```python
from DrissionPage import ChromiumPage

page = ChromiumPage()
page.get('http://DrissionPage.cn')
print(page.title)
```

---

## ✅️️ `WebPage`

`WebPage`覆盖了`ChromiumPage`所有功能，并且增加了切换模式功能，创建的标签页对象为`MixTab`。

| 初始化参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `mode` | `str` | `'d'` | 运行模式，可选`'d'`或`'s'` |
| `chromium_options` | `bool` `ChromiumOptions` | `None` | `ChromiumOptions`对象，传入`None`时从默认 ini 文件读取，传入`False`时不读取 ini 文件，使用默认配置 |
| `session_or_options` | `SessionOptions` `None` `False` | `None` | `Session`对象或`SessionOptions`对象，传入`None`时从默认 ini 文件读取，传入`False`时不读取 ini 文件，使用默认配置 |

```python
from DrissionPage import WebPage

page = WebPage()
page.get('http://DrissionPage.cn')
print(page.title)
page.change_mode()
print(page.title)
```

<!-- https://www.drissionpage.cn/browser_control/get_elements/syntax -->

# 🔦 定位语法

定位语法用于指明以哪种方式去查找指定元素，语法简洁明了，熟练使用可大幅提高程序可读性。

所有涉及获取元素的操作都可以使用定位语法，如`ele()`、`actions.move_to()`、`wait.eles_loaded()`、`get_frame()`等等。

定位语法用于简化代码，提高可读性，但并不覆盖所有复杂场景。很复杂的场景可直接用 xpath 查找。

以下使用这个页面进行讲解。

```html
<html>
<body>
<div id="one">
    <p class="p_cls" id="row1" data="a">第一行</p>
    <p class="p_cls" id="row2" data="b">第二行</p>
    <p class="p_cls">第三行</p>
</div>
<div id="two">
    第二个div
</div>
</body>
</html>
```

## ✅️️ 基本概念

几乎所有查找方法都是基于元素属性进行。

元素属性包括以下三种：

| 写法 | 说明 | 示例 |
| --- | --- | --- |
| `@tag()` | 标签名 | 即`<div id="one">`中的`div` |
| `@****` | 标签体中的属性 | 如`<div id="one">`中的`id`，写作`'@id'` |
| `@text()` | 元素文本 | 即`<p class="p_cls">第三行</p>`中的`第三行` |

查找语法就是按需要对这三种属性进行组合，达到查找指定元素的目的。

说明

`@tag()`和`@text()`后面加上`'()'`，是为了避免与普通元素冲突（如`<div text="abc">`）。

### 📌 简单示例

```python
tab.ele('@id=one')  # 获取第一个id为one的元素
tab.ele('@tag()=div')  # 获取第一个div元素
tab.ele('@text()=第一行')  # 获取第一个文本为“第一行”的元素
```

---

## ✅️️ 基本逻辑

### 📌 单属性匹配符 `@`

单个`@`在只以一个属性作为匹配条件时使用，以`'@'`开头，后面跟属性名称。

上面简单示例中就是这种方式：`tab.ele('@id=one')`。

如果`@`后面只有属性名而没有属性值，查找有这个属性的元素，如`tab.ele('@id')`。

注意

如果属性中包含特殊字符（如包含`@`），用这个方式不能正确匹配到，需使用 css selector 方式查找。且特殊字符要用`\`转义。

---

### 📌 多属性与匹配符 `@@`

当需要多个条件同时确定一个元素时，每个属性用`'@@'`开头。

注意

- 匹配文本或属性中出现`@@`、`@|`、`@!`时，不能使用多属性匹配，需改用 xpath 的方式。
- 如果属性中包含特殊字符（如包含`@`），用这个方式不能正确匹配到，需使用 css selector 方式查找。且特殊字符要用`\`转义。

**示例：**

```python
ele = tab.ele('@@class=p_cls@@text()=第三行')  # 查找class为p_cls且文本为“第三行”的元素
```

---

### 📌 多属性或匹配符 `@|`

当需要以或关系条件查找元素时，每个属性用`'@|'`开头。

注意

- 匹配文本或属性中出现`@@`、`@|`、`@!`时，不能使用多属性匹配，需改用 xpath 的方式。
- 如果属性中包含特殊字符（如包含`@`），用这个方式不能正确匹配到，需使用 css selector 方式查找。且特殊字符要用`\`转义。

**示例：**

```python
eles = tab.eles('@|id=row1@|id=row2')  # 查找所有id为row1或id为row2的元素
```

---

### 📌 否定匹配符 `@!`

用于否定某个条件。

如果`@!`后面只有属性名而没有属性值，查找没有这个属性的元素。

**示例：**

```python
ele = tab.ele('@!id=one')  # 获取第一个id不等于“one”的元素
ele = tab.ele('@!class')  # 匹配没有class属性的元素
```

---

### 📌 混合使用

`@@`和`@|`不能同时出现的查找语句中，即一个查找语句只能是与关系或者或关系。

`@!`则可与两者混合使用。混用时，与还是或关系视`@@`还是`@|`而定。

说明

当语句中有多个`tag()`时，如果全部都没有被`@!`修饰，它们是与关系；如有任一个被`@!`修饰，它们是或关系。
`tag()`与其他属性之间是与关系。

**示例：**

```python
# 匹配class等于p_cls且id不等于row1的元素
tab.ele('@@class=p_cls@!id=row1')

# 匹配class等于p_cls或id不等于row1的元素
tab.ele('@|class=p_cls@!id=row1')
```

---

## ✅️️ 匹配模式

匹配模式指某个查询中匹配条件的方式，有精确匹配、模糊匹配、匹配开头、匹配结尾四种。

说明

`tag()`属性无论用哪种匹配模式，都会视作`=`。

### 📌 精确匹配 `=`

表示精确匹配，匹配完全符合的文本或属性。

```python
ele = tab.ele('@id=row1')  # 获取id属性为'row1'的元素
```

---

### 📌 模糊匹配 `:`

表示模糊匹配，匹配含有指定字符串的文本或属性。

```python
ele = tab.ele('@id:ow')  # 获取id属性包含'ow'的元素
```

---

### 📌 匹配开头 `^`

表示匹配开头，匹配开头为指定字符串的文本或属性。

```python
ele = tab.ele('@id^row')  # 获取id属性以'row'开头的元素
```

---

### 📌 匹配结尾 `$`

表示匹配结 尾，匹配结尾为指定字符串的文本或属性。

```python
ele = tab.ele('@id$w1')  # 获取id属性以'w1'结尾的元素
```

---

## ✅️️ 常用语法

基于上述基本逻辑，本库提供了一些更易于使用和阅读的语法。

### 📌 id 匹配符 `#`

用于匹配`id`属性，**只在语句最前面且单独使用时生效**。相当于单属性查找`@id=****`。

可与匹配模式配合使用。

```python
ele = tab.ele('#one')  # 查找id为one的元素
ele = tab.ele('#=one')  # 和上面一行一致
ele = tab.ele('#:ne')  # 查找id属性包含ne的元素
ele = tab.ele('#^on')  # 查找id属性以on开头的元素
ele = tab.ele('#$ne')  # 查找id属性以ne结尾的元素
```

---

### 📌 class 匹配符 `.`

用于匹配`class`属性，**只在语句最前面且单独使用时生效**，相当于单属性查找`@class=****`。

可配合匹配模式使用。

说明

在面对多个 class 的元素时，DrissionPage 与 selenium 处理方式不一样，无需将空格替换成`'.'`。
而是将整个 class 视作普通字符串，空格视作普通字符对待，会比较直观。

```python
ele = tab.ele('.p_cls')  # 查找class属性为p_cls的元素
ele = tab.ele('.=p_cls')  # 与上一行一致
ele = tab.ele('.:_cls')  # 查找class属性包含_cls的元素
ele = tab.ele('.^p_')  # 查找class属性以p_开头的元素
ele = tab.ele('.$_cls')  # 查找class属性以_cls结尾的元素
```

---

### 📌 文本匹配 符 `text`

用于匹配元素文本。**只在语句最前面且单独使用时生效**，相当于单属性查找`@text()=****`。

可配合匹配模式使用。

如果元素内有多个直接的文本节点，精确查找时可匹配所有文本节点拼成的字符串，模糊查找时可匹配每个文本节点。

如果查找语句没有任何本节介绍的匹配符，默认模糊匹配文本。即`ele('第三行')`相当于`ele('text:第三行')`。

注意

如果要匹配的文本包含特殊字符（如`'&nbsp;'`、`'&gt;'`），需将其转换为十六进制形式，详见《语法速查表》一节。

```python
ele = tab.ele('text=第二行')  # 查找文本为“第二行”的元素
ele = tab.ele('text:第二')  # 查找文本包含“第二”的元素
ele = tab.ele('第二')  # 与上一行一致
ele = tab.ele('第\u00A0二')  # 匹配包含&nbsp;文本的元素，需将&nbsp;转为\u00A0
```

Tips

若要查找的文本包含`text:` ，可下面这样写，即第一个`text:` 为关键字，第二个是要查找的内容：

```python
ele2 = tab.ele('text:text:')
```

---

### 📌 类型匹配符 `tag`

用于匹配某类型元素。**只在语句最前面且单独使用时生效**，相当于单属性查找`@tag()=****`。

可与单属性查找或多属性配合使用。`tag:`与`tag=`效果一致，没有`tag^`和`tag$`语法。

```python
ele = tab.ele('tag:div')  # 查找第一个div元素
ele = tab.ele('tag:p@class=p_cls')  # 与单属性查找配合使用
ele = tab.ele('tag:p@@class=p_cls@@text()=第二行')  # 与多属性查找配合使用
```

注意

`tag:div@text():abc` 和 `tag:div@@text():abc` 是有区别的，前者只在`div`的直接文本节点搜索，后者搜索`div`的整个内部。

---

### 📌 css selector 匹配符 `css`

表示用 css selector 方式查找元素。**只在语句最前面且单独使用时生效**。

`css:`与`css=`效果一致，没有`css^`和`css$`语法。

```python
ele = tab.ele('css:.div')  # 查找 div 元素
ele = tab.ele('css:>div')  # 查找 div 子元素元素，这个写法是本库特有，原生不支持
```

---

### 📌 xpath 匹配符 `xpath`

表示用 xpath 方式查找元素。**只在语句最前面且单独使用时生效**。

`xpath:`与`xpath=`效果一致，没有`xpath^`和`xpath$`语法。

Tips

**元素对象**的`ele()`支持完整的 xpath 语法，如能使用 xpath 直接获取元素属性（字符串类型）。

```python
ele2 = ele1.ele('xpath:.//div')  # 查找后代中第一个 div 元素
ele2 = ele1.ele('xpath://div')  # 和上面一行一样，查找元素的后代时，// 前面的 . 可以省略
ele_class_str = ele1.ele('xpath://div/@class')  # 使用xpath获取div元素 的class属性（页面元素无此功能）
```

说明

查找元素的后代时，selenium 原生代码要求 xpath 前面必须加`.`，否则会变成在全个页面中查找。
作者觉得这个设计是画蛇添足，既然已经通过元素查找了，自然应该只查找这个元素内部的元素。
所以，用 xpath 在元素下查找时，最前面`//`或`/`前面的`.`可以省略。

---

### 📌 selenium 的 loc 元组

查找方法能直接接收 selenium 原生定位元组进行查找，便于项目迁移。

```python
from DrissionPage.common import By

# 查找id为one的元素
loc1 = (By.ID, 'one')
ele = tab.ele(loc1)

# 按 xpath 查找
loc2 = (By.XPATH, '//p[@class="p_cls"]')
ele = tab.ele(loc2)
```

---

## ✅️️ `@@text()`的技巧

值得一提的是，`text()`配合`@@`或`@|`能实现一种很便利的按查找方式。

网页种经常会出现元素和文本混排的情况，比如：

```html
<li class="explore-categories__item">
    <a href="/explore/new-tech" class="">
        <i class="explore"></i>
        前沿技术
    </a>
</li>
<li class="explore-categories__item">
    <a href="/explore/program-develop" class="">
        <i class="explore"></i>
        程序开发
    </a>
</li>
```

示例中，如果要用文本获取`'前沿技术'`的`<a>`元素，可以这样写：

```python
ele = tab.ele('text:前沿技术')
# 或
ele = tab.ele('@text():前沿技术')
```

这两种写法都能获取到包含直接文本的元素。

但如果要用文本获取`<li>`元素，就获取不到，因为文本不是`<li>`的直接内容。

我们可以这样写：

```python
ele = tab.ele('tag:li@@text():前沿技术')
```

`@@text()`与`@text()`不同之处在于，前者可以搜索整个元素内所有文本，而不仅仅是直接文本，因此能实现一些非常灵活的查找。

注意

需要注意的是，使用`@@`或`@|`时，`text()`不要作为唯一的查询条件，否则会定位到整个文档最高层的元素。

❌ 错误做法：

```python
ele = tab.ele('@@text():前沿技术')
ele = tab.ele('@|text():前沿技术@|text():程序开发')
```

⭕ 正确做法：

```python
ele = tab.ele('tag:li@|text():前沿技术@|text():程序开发')
```

---

<!-- https://www.drissionpage.cn/browser_control/get_elements/find_in_object -->

# 🔦 页面或元素内查找

## ✅️️ 页面或元素内查找

页面对象和元素对象都拥有`ele()`和`eles()`方法，用于获取其内部指定子元素。

### 📌 `ele()`

用于查找其内部第一个符合条件的元素。

`SessionPage`和`ChromiumPage`获取元素的方法是一致的，但前者返回的元素对象为`SessionElement`，后者是`ChromiumElement`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` | 必填 | 元素的定位信息。可以是查询字符串，或 loc 元组 |
| `index` | `int` | `1` | 获取第几个匹配的元素，从`1`开始，可输入负数表示从后面开始数 |
| `timeout` | `float` | `None` | 等待元素出现的超时时间（秒），为`None`使用页面对象设置 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionElement` | s 模式下返回静态元素对象 |
| `ChromiumElement` | d 模式下返回找到的第一个符合条件的浏览器元素对象 |
| `ChromiumFrame` | 当结果是框架元素时 |
| `NoneElement` | 未找到符合条件的元素时返回 |

说明

- loc 元组是指 selenium 定位符，例：(By.ID, '\*\*\*\*')。下同。
- `ele('****', index=2)`和`eles('****')[1]`结果一样，不过前者会快很多。

**示例：**

```python
from DrissionPage import SessionPage

page = SessionPage()

# 在页面内查找元素
ele1 = page.ele('#one')

# 在元素内查找后代元素
ele2 = ele1.ele('第二行')
```

---

### 📌 `eles()`

此方法与`ele()`相似，但返回的是匹配到的所有元素组成的列表。

页面对象和元素对象都可调用这个方法。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` | 必填 | 元素的定位信息，可以是查询字符串，或 loc 元组 |
| `timeout` | `float` | `None` | 等待元素出现的超时时间（秒），为`None`使用页面对象设置 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionElementsList` | s 模式下返回静态元素对象组成的列表 |
| `ChromiumElementsList` | d 模式下返回浏览器元素对象组成的列表 |

**示例：**

```python
# 获取页面内的所有p元素
p_eles = tab.eles('tag:p')

# 获取ele1元素内的所有p元素
p_eles = ele1.eles('tag:p')

# 打印第一个p元素的文本
print(p_eles[0])
```

---

### 📌 `get_frame()`

`<iframe>`和`<frame>`也可以用`ele()`查找到，生成的对象是`ChromiumFrame`而不是`ChromiumElement`。

但不建议用`ele()`获取`<iframe>`元素，因为 IDE 无法正确提示后续操作。

建议用`get_frame()`方法获取，页面对象和元素对象都有这个方法。

使用方法与`ele()`一致，可以用定位符查找。还增加了用序号、id、name 属性定位元素的功能。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `loc_ind_ele` | `str` `int` `ChromiumFrame` | 必填 | 定位符 `<iframe>`元素序号（从`1`开始，负数表示倒数） `ChromiumFrame对象` `id`属性内容 `name`属性内容 |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`时使用页面超时时间 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumFrame` | `<frame>`或`<iframe>`元素对象 |
| `NoneElement` | 找不到时返回`NoneElement` |

**示例：**

```python
# 在标签页中获取第一个iframe元素
iframe = tab.get_frame(1)

# 在元素中获取id为`theFrame`的<iframe>元素对象
iframe = ele.get_frame('#theFrame')
```

---

### 📌 `get_frames()`

此方法用于获取页面中多个符合条件的`<frame>`或`<iframe>`对象。

元素对象无此方法。

提醒

获取所有`<iframe>`会很慢，而且浪费资源，非必要别用。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` | `None` | 定位符，为`None`时返回所有 |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`时使用页面超时时间 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElementsList` | `<frame>`或`<iframe>`元素对象组成的列表 |

---

## ✅️️ 静态方式查找

静态元素即 s 模式的`SessionElement`元素对象，是纯文本构造的，因此用它处理速度非常快。
对于复杂的页面，要在成百上千个元素中采集数据时，转换为静态元素可把速度提升几个数量级。
作者曾在实践的时候，用同一套逻辑，仅仅把元素转换为静态，就把一个要 30 秒才完成的页面，加速到零点几秒完成。
我们甚至可以把整个页面转换为静态元素，再在其中提取信息。
当然，这种元素不能进行点击等交互。
用`s_ele()`可在把查找到的动态元素转换为静态元素输出，或者获取元素或页面本身的静态元素副本。

注意

如果需要获取多条数据，不要反复使用`s_ele()`，只要在容器元素调用一次获取其静态副本，再在其中执行获取多个元素。

### 📌 `s_ele()`

页面对象和元素对象都拥有此方法，用于查找第一个匹配条件的元素，获取其静态版本。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` | `None` | 元素的定位信息，可以是查询字符串，或 loc 元组，为`None`时获取调用者本身的静态版本 |
| `index` | `int` | `1` | 获取第几个匹配的元素，从`1`开始，可输入负数表示从后面开始数 |
| `timeout` | `float` | `None` | 查找元素超时时间（秒），为`None`与页面等待时间一致 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionElement` | 返回查找到的第一个符合条件的元素对象的静态版本 |
| `NoneElement` | 限时内未找到符合条件的元素时返回`NoneElement`对象 |

注意

页面对象和元素对象的`s_ele()`方法不能搜索到在`<iframe>`里的元素，页面对象的静态版本也不能搜索`<iframe>`里的元素。
要使用`<iframe>`里元素的静态版本，可先获取该元素，再转换。而使用`ChromiumFrame`对象，则可以直接用`s_ele()`查找元素，这在后面章节再讲述。

Tips

从一个`ChromiumElement`元素获取到的`SessionElement`版本，依然能够使用相对定位方法定位祖先或兄弟元素。

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab

# 在页面中查找元素，获取其静态版本
ele1 = tab.s_ele('search text')

# 在动态元素中查找元素，获取其静态版本
ele = tab.ele('search text')
ele2 = ele.s_ele()

# 获取页面元素的静态副本（不传入参数）
s_page = tab.s_ele()

# 获取动态元素的静态副本
s_ele = ele.s_ele()

# 在静态副本中查询下级元素（因为已经是静态元素，用ele()查找结果也是静态）
ele3 = s_page.ele('search text')
ele4 = s_ele.ele('search text')
```

---

### 📌 `s_eles()`

此方法与`s_ele()`相似，但返回的是匹配到的所有元素组成的列表，或属性值组成的列表。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` | 必填 | 元素的定位信息，可以是查询字符串，或 loc 元组 |
| `timeout` | `float` | `None` | 查找元素超时时间（秒），为`None`与页面等待时间一致 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionElementsList` | 返回找到的所有元素的`SessionElement`版本组成的列表 |

**示例：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
for ele in tab.s_eles('search text'):
    print(ele.text)
```

---

## ✅️ 获取页面焦点元素

使用页面对象的`active_ele`属性获取页面上焦点所在元素。

```python
ele = tab.active_ele
```

---

## ✅️️ 查找`<iframe>`中的元素

### 📌 在页面下跨级查找

与 selenium 不同，本库可以直接查找同域`<iframe>`里面的元素。
而且无视层级，可以直接获取到多层`<iframe>`里的元素。无需切入切出，大大简化了程序逻辑，使用更便捷。
但同域的`<iframe>`才能这样查找。

假设在页面中有个两级`<iframe>`，其中有个元素`<div id='abc'></div>`，可以这样获取：

```python
tab = Chromium().latest_tab
ele = tab('#abc')
```

获取前后无需切入切出，也不影响获取页面上其它元素。

如果用 selenium，要这样写：

```python
driver = webdriver.Chrome()
driver.switch_to.frame(0)
driver.switch_to.frame(0)
ele = driver.find_element(By.ID, 'abc')
driver.switch_to.default_content()
```

显然比较繁琐，而且切入到`<iframe>`后无法对`<iframe>`外的元素进行操作。

注意

- 跨级查找只是页面对象支持，元素对象不能直接查找内部 iframe 里的元素。
- 跨级查找只能用于与主框架同域名的`<iframe>`，不同域名的请用下面的方法。

---

### 📌 在 iframe 元素内查找

对于跨域的`<iframe>`，我们无法通过页面直接查找里面的元素，可以先获取到`<iframe>`元素，再在其下查找。

当然，非跨域`<iframe>`也可以这样操作。

假设一个`<iframe>`的 id 为 `'iframe1'`，要在其中查找一个 id 为`'abc'`的元素：

```python
tab = Chromium().latest_tab
iframe = tab('#iframe1')
ele = iframe('#abc')
```

这个`<iframe>`元素是一个页面对象，因此可以继续在其下进行跨`<iframe>`查找（相对这个`<iframe>`不跨域的）。

---

## ✅️️ `ShadowRoot`内查找

本库把 shadow-root 也作为元素对象看待，是为`ShadowRoot`对象。
该对象可与普通元素一样查找下级元素和 DOM 内相对定位。
对`ShadowRoot`对象进行相对定位时，把它看作其父对象内部的第一个对象，其余定位逻辑与普通对象一致。

用元素对象的`shadow_root`属性可获取`ShadowRoot`对象。

注意

如果`ShadowRoot`元素的下级元素中有其它`ShadowRoot`元素，那这些下级`ShadowRoot`
元素内部是无法直接通过定位语句查找到的，只能先定位到其父元素，再用`shadow-root`属性获取。

```python
# 获取一个 shadow-root 元素
sr_ele = page.ele('#app').shadow_root

# 在该元素下查找下级元素
ele1 = sr_ele.ele('tag:div')

# 用相对定位获取其它元素
ele1 = sr_ele.parent(2)
ele1 = sr_ele.next('tag:div', 1)
ele1 = sr_ele.after('tag:div', 1)
eles = sr_ele.nexts('tag:div')

# 定位下级元素中的 shadow+-root 元素
sr_ele2 = sr_ele.ele('tag:div').shadow_root
```

由于 shadow-root 不能跨级查找，链式操作非常常见，所以设计了一个简写：`sr`，功能和`shadow_root`
一样，都是获取元素内部的`ShadowRoot`。

**多级 shadow-root 链式操作示例：**

以下这段代码，可以打印浏览器历史第一页，可见是通过多级 shadow-root 来获取的。

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('chrome://history/')

items = tab('#history-app').sr('#history').sr.eles('t:history-item')
for i in items:
    print(i.sr('#item-container').text.replace('\n', ''))
```

---

## ✅️️ 同时匹配多个定位符

所有页面或元素对象都有`find()`方法，可接收多个定位符，同时查找多个（批）不同定位符的元素。

以`dict`方法返回每个定位符结果。

说明

当`first_ele`为`True`时，如果一个定位符没有被执行过查找，它返回的结果为`None`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locators` | `List[str]` `Tuple[str, str]` `str` | 必填 | 一个定位符或多个组成的列表 |
| `any_one` | `bool` | `True` | 是否任何一个定位符找到结果即返回 |
| `first_ele` | `bool` | `True` | 每个定位符获取第一个元素还是所有元素 |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`使用该对象默认设置 |

说明

以下所说的 “定位符”，是`str`或`tuple`类型的。
“元素对象”，是`ChromiumElement`（d 模式）或`SessionElement`（s 模式）类型的，没有找到时是`NoneElement`类型的。
“元素对象组成的列表” 是`ChromiumElementsList`（d 模式）或`SessionElementsList`（s 模式）类型的。
`any_one`参数为`True`时，以`tuple`方式返回找到目标的定位符和结果，为`False`时以`dict`方法返回每个定位符结果。

| 返回类型 | `any_one`参数取值 | 说明 |
| --- | --- | --- |
| `tuple(定位符, 元素对象)` | `True` | `first_ele`为`True`时，返回第一个有结果的定位符找到的第一个元素对象 |
| `tuple(定位符, 元素对象组成的列表)` | `True` | `first_ele`为`False`时，返回第一个有结果的定位符找到的所有元素对象 |
| `tuple(None, None)` | `True` | 所有定位符都没有找到元素，返回`(None, None)` |
| `dict{定位符: 元素对象}` | `False` | `first_ele`为`True`时，每个定位符返回第一个元素，找不到时为`NoneElement` |
| `dict{定位符: 元素对象组成的列表}` | `False` | `first_ele`为`False`时，每个定位符返回所有结果元素组成的列表 |

**示例：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('https://www.baidu.com')
res = tab.find(['#kw', '#su'])
print(res)
```

<!-- https://www.drissionpage.cn/browser_control/get_elements/relative -->

# 🔦 相对定位

相对定位的意思是以一个已获取的元素为基准，按需要使用不同方法获取指定的其它元素。

相对定位有基于 DOM 的方式和基于视觉的方式两种。

## ✅️️ 基于 DOM 相对定位

以下方法可以以某元素为基准，在 DOM 中按照条件获取其直接子节点、同级节点、祖先元素、文档前后节点。

这里说的是 “节点”，不是 “元素”。因为相对定位可以获取除元素外的其它节点，包括文本、注释节点。

注意

如果元素在`<iframe>`中，相对定位不能超越`<iframe>`文档。

### 📌 获取父级元素

🔸 `parent()`

此方法获取当前元素某一级父元素，可指定筛选条件或层数。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `level_or_loc` | `int` `str` `Tuple[str, str]` | `1` | 第几级父元素，从`1`开始，或用定位符在祖先元素中进行筛选 |
| `index` | `int` | `1` | 当`level_or_loc`传入定位符，使用此参数选择第几个结果，从当前元素往上级数；当`level_or_loc`传入数字时，此参数无效 |
| `timeout` | `float` | `0` | 查找超时时间（秒），为`None`时使用页面超时设置，s 模式下无效 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | d 模式下的元素对象 |
| `SessionElement` | s 模式下的元素对象 |
| `NoneElement` | 未获取到结果时 |

**示例：**

```python
# 获取 ele1 的第二层父元素
ele2 = ele1.parent(2)

# 获取 ele1 父元素中 id 为 id1 的元素
ele2 = ele1.parent('#id1')
```

---

### 📌 获取直接子节点

🔸 `child()`

此方法返回当前元素的一个直接子节点，可指定筛选条件和第几个。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` `int` | `''` | 用于筛选节点的查询语法，为`int`类型时`index`参数无效 |
| `index` | `int` | `1` | 查询结果中的第几个，从`1`开始，可输入负数表示倒数 |
| `timeout` | `float` | `None` | 查找超时时间（秒），为`None`时使用页面超时设置，s 模式下无效 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 获取非元素节点时返回字符串 |
| `ChromiumElement` | d 模式下的元素对象 |
| `SessionElement` | s 模式下的元素对象 |
| `NoneElement` | 未获取到结果时 |

---

🔸 `children()`

此方法返回当前元素全部符合条件的直接子节点组成的列表，可用查询语法筛选。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` | `''` | 用于筛选节点的查询语法 |
| `timeout` | `float` | `None` | 查找超时时间（秒），为`None`时使用页面超时设置，s 模式下无效 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElementsList` | d 模式结果列表 |
| `SessionElementsList` | s 模式结果列表 |

---

### 📌 获取后面的同级节点

🔸 `next()`

此方法返回当前元素后面的某一个同级节点，可指定筛选条件和第几个。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` `int` | `''` | 用于筛选节点的查询语法，为`int`类型时`index`参数无效 |
| `index` | `int` | `1` | 查询结果中的第几个，从`1`开始，可输入负数表示倒数 |
| `timeout` | `float` | `None` | 查找超时时间（秒），为`None`时使用页面超时设置，s 模式下无效 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 获取非元素节点时返回字符串 |
| `ChromiumElement` | d 模式下的元素对象 |
| `SessionElement` | s 模式下的元素对象 |
| `NoneElement` | 未获取到结果时 |

**示例：**

```python
# 获取 ele1 后面第一个兄弟元素
ele2 = ele1.next()

# 获取 ele1 后面第 3 个兄弟元素
ele2 = ele1.next(3)

# 获取 ele1 后面第 3 个 div 兄弟元素
ele2 = ele1.next('tag:div', 3)

# 获取 ele1 后面第一个文本节点的文本
txt = ele1.next('xpath:text()', 1)
```

---

🔸 `nexts()`

此方法返回当前元素后面全部符合条件的同级节点组成的列表，可用查询语法筛选。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` | `''` | 用于筛选节点的查询语法 |
| `timeout` | `float` | `None` | 查找超时时间（秒），为`None`时使用页面超时设置，s 模式下无效 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElementsList` | d 模式结果列表 |
| `SessionElementsList` | s 模式结果列表 |

**示例：**

```python
# 获取 ele1 后面所有兄弟元素
eles = ele1.nexts()

# 获取 ele1 后面所有 div 兄弟元素
divs = ele1.nexts('tag:div')

# 获取 ele1 后面的所有文本节点
txts = ele1.nexts('xpath:text()')
```

---

### 📌 获取前面的同级节点

🔸 `prev()`

此方法返回当前元素前面的某一个同级节点，可指定筛选条件和第几个。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` `int` | `''` | 用于筛选节点的查询语法 ，为`int`类型时`index`参数无效 |
| `index` | `int` | `1` | 查询结果中的第几个，从`1`开始，可输入负数表示倒数 |
| `timeout` | `float` | `None` | 查找超时时间（秒），为`None`时使用页面超时设置，s 模式下无效 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 获取非元素节点时返回字符串 |
| `ChromiumElement` | d 模式下的元素对象 |
| `SessionElement` | s 模式下的元素对象 |
| `NoneElement` | 未获取到结果时 |

**示例：**

```python
# 获取 ele1 前面第一个兄弟元素
ele2 = ele1.prev()

# 获取 ele1 前面第 3 个兄弟元素
ele2 = ele1.prev(3)

# 获取 ele1 前面第 3 个 div 兄弟元素
ele2 = ele1.prev(3, 'tag:div')

# 获取 ele1 前面第一个文本节点的文本
txt = ele1.prev(1, 'xpath:text()')
```

---

🔸 `prevs()`

此方法返回当前元素前面全部符合条件的同级节点组成的列表，可用查询语法筛选。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` | `''` | 用于筛选节点的查询语法 |
| `timeout` | `float` | `None` | 查找超时时间（秒），为`None`时使用页面超时设置，s 模式下无效 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElementsList` | d 模式结果列表 |
| `SessionElementsList` | s 模式结果列表 |

**示例：**

```python
# 获取 ele1 前面所有兄弟元素
eles = ele1.prevs()

# 获取 ele1 前面所有 div 兄弟元素
divs = ele1.prevs('tag:div')
```

---

### 📌 在后面文档中查找节点

🔸 `after()`

此方法返回当前元素后面的某一个节点，可指定筛选条件和第几个。查找范围不限同级节点，而是整个 DOM 文档。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` `int` | `''` | 用于筛选节点的查询语法，为`int`类型时`index`参数无效 |
| `index` | `int` | `1` | 查询结果中的第几个，从`1`开始，可输入负数表示倒数 |
| `timeout` | `float` | `None` | 查找超时时间（秒），为`None`时使用页面超时设置，s 模式下无效 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 获取非元素节点时返回字符串 |
| `ChromiumElement` | d 模式下的元素对象 |
| `SessionElement` | s 模式下的元素对象 |
| `NoneElement` | 未获取到结果时 |

**示例：**

```python
# 获取 ele1 后面第 3 个元素
ele2 = ele1.after(index=3)

# 获取 ele1 后面第 3 个 div 元素
ele2 = ele1.after('tag:div', 3)

# 获取 ele1 后面第一个文本节点的文本
txt = ele1.after('xpath:text()', 1)
```

---

🔸 `afters()`

此方法返回当前元素后面符合条件的全部节点组成的列表，可用查询语法筛选。查找范围不限同级节点，而是整个 DOM 文档。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` | `''` | 用于筛选节点的查询语法 |
| `timeout` | `float` | `None` | 查找超时时间（秒），为`None`时使用页面超时设置，s 模式下无效 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElementsList` | d 模式结果列表 |
| `SessionElementsList` | s 模式结果列表 |

**示例：**

```python
# 获取 ele1 后所有元素
eles = ele1.afters()

# 获取 ele1 前面所有 div 元素
divs = ele1.afters('tag:div')
```

---

### 📌 在前面文档中查找节点

🔸 `before()`

此方法返回当前元素前面的某一个符合条件的节点，可指定筛选条件和第几个。查找范围不限同级节点，而是整个 DOM 文档。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` `int` | `''` | 用于筛选节点的查询语法，为`int`类型时`index`参数无效 |
| `index` | `int` | `1` | 查询结果中的第几个，从`1`开始，可输入负数表示倒数 |
| `timeout` | `float` | `None` | 查找超时时间（秒），为`None`时使用页面超时设置，s 模式下无效 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 获取非元素节点时返回字符串 |
| `ChromiumElement` | d 模式下的元素对象 |
| `SessionElement` | s 模式下的元素对象 |
| `NoneElement` | 未获取 到结果时 |

**示例：**

```python
# 获取 ele1 前面第 3 个元素
ele2 = ele1.before(3)

# 获取 ele1 前面第 3 个 div 元素
ele2 = ele1.before('tag:div', 3)

# 获取 ele1 前面第一个文本节点的文本
txt = ele1.before('xpath:text()', 1)
```

---

🔸 `befores()`

此方法返回当前元素前面全部符合条件的节点组成的列表，可用查询语法筛选。查找范围不限同级节点，而是整个 DOM 文档。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` | `''` | 用于筛选节点的查询语法 |
| `timeout` | `float` | `None` | 查找超时时间（秒），为`None`时使用页面超时设置，s 模式下无效 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElementsList` | d 模式结果列表 |
| `SessionElementsList` | s 模式结果列表 |

**示例：**

```python
# 获取 ele1 前面所有元素
eles = ele1.befores()

# 获取 ele1 前面所有 div 元素
divs = ele1.befores('tag:div')
```

---

## ✅️️ 基于视觉相对定位

以 下方法可以以某元素为基准，向不同方向或指定偏移量获取元素。

只有浏览器模式支持这类定位方式。

只能获取可见的元素（不论是否在视口内），不能获取被遮挡的。

### 📌 `east()`

此方法用于获取一个在当前元素右边的元素。

`loc_or_pixel`参数可用定位符指定筛选条件，定位符只支持`str`格式，且不支持 xpath 和 css 方式。

用`index`参数可指定获取第几个结果。如果`loc_or_pixel`为`None`，获取第若干个元素。

`loc_or_pixel`为`int`格式时，直接获取元素右边这个距离的元素，此时`index`参数无效。距离从右边框开始计算。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `loc_or_pixel` | `str` `int` | `None` | 定位符或距离（像素） |
| `index` | `int` | `1` | 第几个，从1开始，`loc_or_pixel`为`int`格式时无效 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 找到的元素对象 |
| `NoneElement` | 未获取到结果时 |

---

### 📌 `west()`

此方法用于获取一个在当前元素左边的元素。

`loc_or_pixel`参数可用定位符指定筛选条件，定位符只支持`str`格式，且不支持 xpath 和 css 方式。

用`index`参数可指定获取第几个结果。如果`loc_or_pixel`为`None`，获取第若干个元素。

`loc_or_pixel`为`int`格式时，直接获取元素左边这个距离的元素，此时`index`参数无效。距离从左边框开始计算。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `loc_or_pixel` | `str` `int` | `None` | 定位符或距离（像素） |
| `index` | `int` | `1` | 第几个，从1开始，`loc_or_pixel`为`int`格式时无效 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 找到的元素对象 |
| `NoneElement` | 未获取到结果时 |

---

### 📌 `south()`

此方法用于获取一个在当前元素下边的元素。

`loc_or_pixel`参数可用定位符指定筛选条件，定位符只支持`str`格式，且不支持 xpath 和 css 方式。

用`index`参数可指定获取第几个结果。如果`loc_or_pixel`为`None`，获取第若干个元素。

`loc_or_pixel`为`int`格式时，直接获取元素下边这个距离的元素，此时`index`参数无效。距离从下边框开始计算。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `loc_or_pixel` | `str` `int` | `None` | 定位符或距离（像素） |
| `index` | `int` | `1` | 第几个，从1开始，`loc_or_pixel`为`int`格式时无效 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 找到的元素对象 |
| `NoneElement` | 未获取到结果时 |

---

### 📌 `north()`

此方法用于获取一个在当前元素上边的元素。

`loc_or_pixel`参数可用定位符指定筛选条件，定位符只支持`str`格式，且不支持 xpath 和 css 方式。

用`index`参数可指定获取第几个结果。如果`loc_or_pixel`为`None`，获取第若干个元素。

`loc_or_pixel`为`int`格式时，直接获取元素上边这个距离的元素，此时`index`参数无效。距离从上边框开始计算。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `loc_or_pixel` | `str` `int` | `None` | 定位符或距离（像素） |
| `index` | `int` | `1` | 第几个，从1开始，`loc_or_pixel`为`int`格式时无效 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 找到的元素对象 |
| `NoneElement` | 未获取到结果时 |

---

### 📌 `offset()`

此方法用于获取相对于元素左上角指定偏移量的一个元素。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `offset_x` | `int` | 必填 | 横坐标偏移量（像素），向右为正 |
| `offset_y` | `int` | 必填 | 纵坐标偏移量（像素），向下为正 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 找到的元素对象 |
| `NoneElement` | 未获取到结果时 |

---

### 📌 `over()`

此方法用于获取覆盖在本元素上最上层的元素。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 等待元素出现的超时时间（秒），为`None`使用页面`timeout`设置值 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 找到的元素对象 |
| `NoneElement` | 未获取到结果时 |

<!-- https://www.drissionpage.cn/browser_control/get_elements/behavior -->

# 🔦 行为模式

## ✅️ 等待元素

由于网络、js 运行时间的不确定性，经常需要等待元素加载到 DOM 中才能使用。

浏览器所有查找元素操作都自带等待，时间默认跟随元素所在页面`timeout`属性（默认 10 秒），也可以在每次查找时单独设置，单独设置的等待时间不会改变页面原来设置。

### 📌 内置等待

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
# 设置查找元素超时时间为 5 秒
tab.set.timeouts(5)

# 使用页面超时时间来查找元素（5 秒）
ele1 = tab.ele('search text')
# 为这次查找页面独立设置等待时间（1 秒）
ele1 = tab.ele('search text', timeout=1)
# 查找后代元素，使用页面超时时间（5 秒）
ele2 = ele1.ele('search text')
# 查找后代元素，使用单独设置的超时时间（1 秒）
ele2 = ele1.ele('some text', timeout=1)
```

### 📌 主动等待

页面对象的`wait.eles_loaded()`方法，可主动等待指定元素加载到 DOM。

用法详见等待章节。

---

## ✅️ 链式写法

因为元素对象本身又可以查找对象，所有可实现多级链式操作，可使程序更简洁。

**示例：**

```python
ele = tab.ele('#s_fm').ele('#su')
```

其中`ele()`可省略，简化写成：

```python
ele = tab('#s_fm')('#su')
```

---

## ✅️ 找不到元素时

### 📌 默认情况

默认情况下，找不到元素时不会立即抛出异常，而是返回一个`NoneElement`对象。

这个对象用`if`判断表现为`False`，调用其功能会抛出`ElementNotFoundError`异常。

这样可以用`if`判断是否找到元素，也可以用`try`去捕获异常。

查找多个元素找不到时，返回空的`list`。

**示例 ，用`if`判断：**

```python
ele = tab.ele('****')

# 判断是否找到元素
if ele:
    print('找到了。')

if not ele:
    print('没有找到。')
```

**示例，用`try`捕获：**

```python
try:
    ele.click()
except ElementNotFoundError:
    print('没有找到。')
```

---

### 📌 立即抛出异 常

如果想在找不到元素时立刻抛出异常，可以用以下方法设置。

此设置为全局有效，在项目开始时设置一次即可。

查找多个元素找不到时，依然返回空的`list`。

设置全局变量：

```python
from DrissionPage.common import Settings

Settings.set_raise_when_ele_not_found(True)
```

**示例：**

```python
from DrissionPage import Chromium
from DrissionPage.common import Settings

Settings.set_raise_when_ele_not_found(True)

tab = Chromium().latest_tab
tab.get('https://www.baidu.com')
ele = tab('#abcd')  # ('#abcd')这个元素不存在
```

输出：

```console
DrissionPage.errors.ElementNotFoundError:
没有找到元素。
method: ele()
args: {'locator': '#abcd'}
```

---

### 📌 设置默认返回值

如果查找元素后要获取一个属性，但这个元素不一定存在，或者链式查找其中一个节点找不到，可以设置查找失败时返回的值，而不是抛出 异常，可以简化一些采集逻辑。

使用浏览器页面对象的`set.NoneElement_value()`方法设置该值。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `value` | `Any` | `None` | 将返回的设定值 |
| `on_off` | `bool` | `True` | `bool`表示是否启用 |

**返回：**`None`

**示例**

比如说，遍历页面上一个列表中多个对象，但其中有些元素可能缺失某个子元素，可以这样写：

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.set.NoneElement_value('没找到')
for li in tab.eles('t:li'):
    name = li('.name').text
    age = li('.age').text
    phone = li('.phone').text
```

这样，假如某个子元素不存在，不会抛出异常，而是返回`'没找到'`这个字符串。

<!-- https://www.drissionpage.cn/browser_control/get_elements/filter -->

# 🔦 在结果列表中筛选

本节介绍在元素列表中按需要进行筛选，获取指定元素。

`eles()`、`nexts()`等能够获取多个元素的方法，返回的列表可进行进一步筛选，以获取指定的元素。

说明

浏览器页面对象和`SessionPage`产生的元素列表均有此功能，前者筛选功能比后者多。

**示例1，筛选并返回元素列表：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('https://www.baidu.com')
eles = tab('#s-top-left').eles('t:a')  # 获取左上角导航栏内所有<a>元素
for ele in eles.filter.displayed():  # 筛选出显示的元素列表并逐个打印文本
    print(ele.text, end=' ')
```

**输出：**

```shell
新闻 hao123 地图 贴吧 视频 图片 网盘 文库 更多
```

**示例2，筛选并返回第一个元素：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('https://www.baidu.com')
eles = tab('#s-top-left').eles('t:a')  # 获取左上角导航栏内所有<a>元素
print(eles.filter_one.displayed().text)  # 筛选出显示的元素并返回第一个
```

**输出：**

```shell
新闻
```

## ✅️️ 获取单个匹配元素

说明

静态元素列表只有`filter_one.attr()`和`filter_one.text()`方法。

### 📌 `filter_one.displayed()`

此方法用于在元素列表中以是否显示为条件筛选元素，返回第一个结果。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `equal` | `bool` | `True` | 是否匹配显示的元素，`False`匹配不显示的 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 匹配成功返回元素对象 |
| `NoneElement` | 失败返回`NoneElement` |
| 抛出`ElementNotFoundError`异常 | `Settings.raise_when_ele_not_found`为`True`时抛出 |

---

### 📌 `filter_one.checked()`

此方法用于在元素列表中以是否被选中为条件筛选元素，返回第一个结果。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `equal` | `bool` | `True` | 是否匹配被选中的元素，`False`匹配不被选中的 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 匹配成功返回元素对象 |
| `NoneElement` | 失败返回`NoneElement` |
| 抛出`ElementNotFoundError`异常 | `Settings.raise_when_ele_not_found`为`True`时抛出 |

---

### 📌 `filter_one.selected()`

此方法用于在元素列表中以是否被选择为条件筛选元素，返回第一个结果。用于`<select>`元素项目。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `equal` | `bool` | `True` | 是否匹配被选择的元素，`False`匹配不被选择的 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 匹配成功返回元素对象 |
| `NoneElement` | 失败返回`NoneElement` |
| 抛出`ElementNotFoundError`异常 | `Settings.raise_when_ele_not_found`为`True`时抛出 |

---

### 📌 `filter_one.enabled()`

此方法用于在元素列表中以是否可用为条件筛选元素，返回第一个结果。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `equal` | `bool` | `True` | 是否匹配可用的元素，`False`匹配 disabled 状态的 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 匹配成功返回元素对象 |
| `NoneElement` | 失败返回`NoneElement` |
| 抛出`ElementNotFoundError`异常 | `Settings.raise_when_ele_not_found`为`True`时抛出 |

---

### 📌 `filter_one.clickable()`

此方法用于在元素列表中以是否可点击为条件筛选元素，返回第一个结果。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `equal` | `bool` | `True` | 是否匹配可点击的元素，`False`表示匹配不是可点击的 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 匹配成功返回元素对象 |
| `NoneElement` | 失败返回`NoneElement` |
| 抛出`ElementNotFoundError`异常 | `Settings.raise_when_ele_not_found`为`True`时抛出 |

---

### 📌 `filter_one.have_rect()`

此方法用于在元素列表中以是否有大小为条件筛选元素，返回第一个结果。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `equal` | `bool` | `True` | 是否匹配有大小的元素，`False`表示匹配没有大小的 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 匹配成功返回元素对象 |
| `NoneElement` | 失败返回`NoneElement` |
| 抛出`ElementNotFoundError`异常 | `Settings.raise_when_ele_not_found`为`True`时抛出 |

---

### 📌 `filter_one.style()`

此方法用于在元素列表中以是否拥有某个 style 值为条件筛选元素，返回第一个结果。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 属性名称 |
| `value` | `str` | 必填 | 属性值 |
| `equal` | `bool` | `True` | `True`表示匹配`name`值为`value`值的元素，`False`表示匹配`name`值不为`value`值的 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 匹配成功返回元素对象 |
| `NoneElement` | 失败返回`NoneElement` |
| 抛出`ElementNotFoundError`异常 | `Settings.raise_when_ele_not_found`为`True`时抛出 |

---

### 📌 `filter_one.property()`

此方法用于在元素列表中以是否拥有某个 property 值为条件筛选元素，返回第一个结果。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 属性名称 |
| `value` | `str` | 必填 | 属性值 |
| `equal` | `bool` | `True` | `True`表示匹配`name`值为`value`值的元素，`False`表示匹配`name`值不为`value`值的 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 匹配成功返回元素对象 |
| `NoneElement` | 失败返回`NoneElement` |
| 抛出`ElementNotFoundError`异常 | `Settings.raise_when_ele_not_found`为`True`时抛出 |

---

### 📌 `filter_one.attr()`

此方法用于在元素列表中以是否拥有某个 attribute 值为条件筛选元素，返回第一个结果。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 属性名称 |
| `value` | `str` | 必填 | 属性值 |
| `equal` | `bool` | `True` | `True`表示匹配`name`值为`value`值的元素，`False`表示匹配`name`值不为`value`值的 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 匹配成功返回元素对象 |
| `NoneElement` | 失败返回`NoneElement` |
| 抛出`ElementNotFoundError`异常 | `Settings.raise_when_ele_not_found`为`True`时抛出 |

---

### 📌 `filter_one.text()`

此方法用于在元素列表中以是否含有指定文本为条件筛选元素，返回第一个结果。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `text` | `str` | 必填 | 用于匹配的文本 |
| `fuzzy` | `bool` | `True` | 是否模糊匹配 |
| `contain` | `bool` | `True` | 是否包含该字符串，`False`表示不包含 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 匹配成功返回元素对象 |
| `NoneElement` | 失败返回`NoneElement` |
| 抛出`ElementNotFoundError`异常 | `Settings.raise_when_ele_not_found`为`True`时抛出 |

---

### 📌 `filter_one.tag()`

此方法用于在元素列表中以某个类型为条件筛选元素，返回第一个结果。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 元素类型名称 |
| `equal` | `bool` | `True` | `True`表示匹配该类型元素，`False`表示匹配非该类型元素 |

| 返回类型 | 说明 |
| --- | --- |
| `ChromiumElement` | 匹配成功返回元素对象 |
| `NoneElement` | 失败返回`NoneElement` |
| 抛出`ElementNotFoundError`异常 | `Settings.raise_when_ele_not_found`为`True`时抛出 |

---

### 📌 选择获取第几个

`filter_one`可加参数，以选择返回第几个结果。

**示例：**

```python
ele = eles.filter_one(2).text('图')  # 获取第二个文本带有“图”字的元素
```

说明

`filter_one`在不加序号参数时，可不要后面的`()`。

---

## ✅️️ 获取全部匹配元素

说明

静态元素列表只有`filter.attr()`和`filter.text()`方法。

### 📌 `filter.displayed()`

此方法用于在元素列表中以是否显示为条件筛选元素，返回新的列表。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `equal` | `bool` | `True` | 是否匹配显示的元素，`False`匹配不显示的 |

| 返回类型 | 说明 |
| --- | --- |
| `Filter` | 元素对象组成的列表，可继续用于筛选 |

---

### 📌 `filter.checked()`

此方法用于在元素列表中以是否被选中为条件筛选元素，返回新的列表。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `equal` | `bool` | `True` | 是否匹配被选中的元素，`False`匹配不被选中的 |

| 返回类型 | 说明 |
| --- | --- |
| `Filter` | 元素对象组成的列表，可继续用于筛选 |

---

### 📌 `filter.selected()`

此方法用于在元素列表中以是否被选择为条件筛选元素，返回新的列表。用于`<select>`元素项目。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `equal` | `bool` | `True` | 是否匹配被选择的元素，`False`匹配不被选择的 |

| 返回类型 | 说明 |
| --- | --- |
| `Filter` | 元素对象组成的列表，可继续用于 筛选 |

---

### 📌 `filter.enabled()`

此方法用于在元素列表中以是否可用为条件筛选元素，返回新的列表。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `equal` | `bool` | `True` | 是否匹配可用的元素，`False`匹配 disabled 状态的 |

| 返回类型 | 说明 |
| --- | --- |
| `Filter` | 元素对象组成的列表，可继续用于筛选 |

---

### 📌 `filter.clickable()`

此方法用于在元素列表中以是否可点击为条件筛选元素，返回新的列表。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `equal` | `bool` | `True` | 是否匹配可点击的元素，`False`表示匹配不是可点击的 |

| 返回类型 | 说明 |
| --- | --- |
| `Filter` | 元素对象组成的列表，可继续用于筛选 |

---

### 📌 `filter.have_rect()`

此方法用于在元素列表中以是否有大小为条件筛选元素，返回新的列表。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `equal` | `bool` | `True` | 是否匹配有大小的元素，`False`表示匹配没有大小的 |

| 返回类型 | 说明 |
| --- | --- |
| `Filter` | 元素对象组成的列表，可继续用于筛选 |

---

### 📌 `filter.style()`

此方法用于在元素列表中以是否拥有某个 style 值为条件筛选元素，返回新的列表。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 属性名称 |
| `value` | `str` | 必填 | 属性值 |
| `equal` | `bool` | `True` | `True`表示匹配`name`值为`value`值的元素，`False`表示匹配`name`值不为`value`值的 |

| 返回类型 | 说明 |
| --- | --- |
| `Filter` | 元素对象组成的列表，可继续用于筛选 |

---

### 📌 `filter.property()`

此方法用于在元素列表中以是否拥有某个 property 值为条件筛选元素，返回新的列表。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 属性名称 |
| `value` | `str` | 必填 | 属性值 |
| `equal` | `bool` | `True` | `True`表示匹配`name`值为`value`值的元素，`False`表示匹配`name`值不为`value`值的 |

| 返回类型 | 说明 |
| --- | --- |
| `Filter` | 元素对象组成的列表，可继续用于筛选 |

---

### 📌 `filter.tag()`

此方法用于在元素列表中以某个类型为条件筛选元素，返回新的列表。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 元素类型名称 |
| `equal` | `bool` | `True` | `True`表示匹配该类型元素，`False`表示匹配非该类型元素 |

| 返回类型 | 说明 |
| --- | --- |
| `Filter` | 元素对象组成的列表，可继续用于筛选 |

---

### 📌 `filter.attr()`

此方法用于在元素列表中以是否拥有某个 attribute 值为条件筛选元素，返回新的列表。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 属性名称 |
| `value` | `str` | 必填 | 属性值 |
| `equal` | `bool` | `True` | `True`表示匹配`name`值为`value`值的元素，`False`表示匹配`name`值不为`value`值的 |

| 返回类型 | 说明 |
| --- | --- |
| `Filter` | 元素对象组成的列表，可继续用于筛选 |

---

### 📌 `filter.text()`

此方法用于在元素列表中以是否含有指定文本为条件筛选元素，返回新的列表。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `text` | `str` | 必填 | 用于匹配的文本 |
| `fuzzy` | `bool` | `True` | 是否模糊匹配 |
| `contain` | `bool` | `True` | 是否包含该字符串，`False`表示不包含 |

| 返回类型 | 说明 |
| --- | --- |
| `Filter` | 元素对象组成的列表，可继续用于筛选 |

---

## ✅️️ 多条件筛选

### 📌 与关系筛选

筛选支持链式操作，可串连多个条件，每个条件会筛选一层再进入下一层。

可实现多个条件的与关系筛选。

**示例，出导航栏中显示且含有“图”字的元素：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('https://www.baidu.com')
eles = tab('#s-top-left').eles('t:a')
for ele in eles.filter.displayed().text('图'):
    print(ele.text, end=' ')
```

---

### 📌 或关系筛选

元素列表的`search()`和`search_one()`方法可用于多个条件或筛选元素。

说明

静态元素列表没有这种方法。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `index`（`search_one()`独有） | `int` | `1` | 结果中的元素序号，`1`开始 |
| `displayed` | `bool` | `None` | 是否显示，`bool`表示匹配是或否，`None`为忽略该项 |
| `checked` | `bool` | `None` | 是否被选中，`bool`表示匹配是或否，`None`为忽略该项 |
| `selected` | `bool` | `None` | 是否被选择，`bool`表示匹配是或否，`None`为忽略该项 |
| `enabled` | `bool` | `None` | 是否可用，`bool`表示匹配是或否，`None`为忽略该项 |
| `clickable` | `bool` | `None` | 是否可点击，`bool`表示匹配是或否，`None`为忽略该项 |
| `have_rect` | `bool` | `None` | 是否拥有大小，`bool`表示匹配是或否，`None`为忽略该项 |
| `have_text` | `bool` | `None` | 是否含有文本，`bool`表示匹配是或否，`None`为忽略该项 |
| `tag` | `str` | `None` | 指定标签页类型，`None`为忽略该项 |

| 返回类型 | 说明 |
| --- | --- |
| `Filter` | `search()`返回元素对象组成的列表 |
| `ChromiumElement` | `search_one()`匹配成功返回元素对象 |
| `NoneElement` | `search_one()`匹配失败返回`NoneElement` |

---

### 📌 混合筛选

与关系和或关系可以用链式操作混合使用。

说明

静态元素列表没有这种方法。

```python
es = eles.search(displayed=True).enabled()
ele = eles.filter.enablde().search_one(displayed=True)
```

---

## ✅️️ 获取筛选结果的属性集合

筛选结果列表可以调用`get()`方法获取指定属性结合。

该集合为遍历列表中所有元素获取的。

**示例：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('https://www.baidu.com')
eles = tab('#s-top-left').eles('t:a')
print(eles.get.texts())  # 获取所有元素的文本
print(eles.filter.displayed().get.texts())  # 获取的元素的文本
```

**输出：**

```shell
['新闻', 'hao123', '地图', '贴吧', '视频', '图片', '网盘', '文库', '更多', '翻译', '学术', '百科', '知道', '健康', '营销推广', '直播', '音乐', '橙篇', '查看全部百度产品 >']
['新闻', 'hao123', '地图', '贴吧', '视频', '图片', '网盘', '文库', '更多']
```

### 📌 `get.attrs()`

此方法用于返回所有元素指定的 attribute 属性组成的列表。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 属性名称 |

| 返回类型 | 说明 |
| --- | --- |
| `List[str]` | 属性文本组成的列表 |

---

### 📌 `get.links()`

此方法用于返回所有元素的`link`属性组成的列表。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `List[str]` | 链接文本组成的列表 |

---

### 📌 `get.texts()`

此方法用于返回所有元素的`text`属性组成的列表。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `List[str]` | 元素文本组成的列表 |

<!-- https://www.drissionpage.cn/browser_control/get_elements/simplify -->

# 🔦 简化写法

为进一步精简代码，定位语法都可以用简化形式来表示，使语句更短，链式操作时更清晰。

## ✅️ 定位符语法简化

- 定位语法都有其简化形式
- 页面和元素对象都实现了`__call__()`方法，所以`page.ele('****')`可简化为`page('****')`
- 查找方法都支持链式操作

示例：

```python
# 查找tag为div的元素
ele = tab.ele('tag:div')  # 原写法
ele = tab('t:div')  # 简化写法

# 用xpath查找元素
ele = tab.ele('xpath://****')  # 原写法
ele = tab('x://****')  # 简化写法

# 查找text为'something'的元素
ele = tab.ele('text=something')  # 原写法
ele = tab('tx=something')  # 简化写法
```

简化 写法对应列表

| 原写法 | 简化写法 | 说明 |
| --- | --- | --- |
| `@id` | `#` | 表示 id 属性，简化写法只在语句最前面且单独使用时生效 |
| `@class` | `.` | 表示 class 属性，简化写法只在语句最前面且单独使用时生效 |
| `text` | `tx` | 按文本匹配 |
| `@text()` | `@tx()` | 按文本查找，与 @ 或 @@ 配合使用时 |
| `tag` | `t` | 按标签类型匹配 |
| `@tag()` | `@t()` | 按元素名查找，与 @ 或 @@ 配合使用时 |
| `xpath` | `x` | 用 xpath 方式查找元素 |
| `css` | `c` | 用 css selector 方式查找元素 |

---

## ✅️ shadow root 简化

一般获取元素的 shadow root 元 素，用`ele.shadow_root`属性。

由于此属性经常用于大量链式操作，名字太长影响可读性，因此可简化为`ele.sr`

**示例：**

```python
txt = ele.sr('t:div').text
```

---

## ✅️ 相对定位参数简化

相对定位时，有时需要获取当前元素后某个元素，而不关心该元素是什么类型，一般是这样写：`ele.next(index=2)`。

但有一种简化的写法，可以直接写作`ele.next(2)`。

当第一个参数`filter_loc`接收数字时，会自动将其视作序号，替代`index`参数。因此书写可以稍微精简一些。

**示例：**

```python
ele2 = ele1.parent(2)
ele2 = ele1.next(2)('tx=****')
ele2 = ele1.before(2)
# 如此类推
```

<!-- https://www.drissionpage.cn/browser_control/get_elements/sheet -->

# 🔦 语法速查表

## ✅️ 定位语法

### 📌 基本用法

| 写法 | 精确匹配 | 模糊匹配 | 匹配开头 | 匹配结尾 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `@属性名` | `@属性名=` | `@属性名:` | `@属性名^` | `@属性名$` | 按某个属性查找 |
| `@!属性名` | `@!属性名=` | `@!属性名:` | `@!属性名^` | `@!属性名$` | 查找属性不符合指定条件的元素 |
| `text` | `text=` | `text:`或不写 | `text^` | `text$` | 按某个文本查找 |
| `@text()` | `@text()=` | `@text():` | `text()^` | `text()$` | `text`与`@`或`@@`配合使用时改为`text()`，常用于多条件匹配 |
| `tag` | `tag=`或`tag:` | 无 | 无 | 无 | 查找某个类型的元素 |
| `@tag()` | `@tag()=`或`@tag():` | 无 | 无 | 无 | 组合使用时查找某个类型的元素 |
| `xpath` | `xpath=`或`xpath:` | 无 | 无 | 无 | 用 xpath 方式查找元素 |
| `css` | `css=`或`css:` | 无 | 无 | 无 | 用 css selector 方式查找元素 |

---

### 📌 组合用法

| 写法 | 说明 |
| --- | --- |
| `@@属性1@@属性2` | 匹配属性同时符合多个条 件的元素 |
| `@@属性1@!属性2` | 多属性匹配与否定匹配同时使用 |
| `@|属性1@|属性2` | 匹配属性至符合多个条件中一的元素 |
| `tag:元素名@属性名` | `tag`与属性匹配共同使用 |
| `tag:元素名@@属性1@@属性2` | `tag`与多属性匹配共同使用 |
| `tag:元素名@|属性1@|属性2` | `tag`与多属性匹配共同使用 |
| `tag:元素名@@text()=文本@@属性` | `tag`与文本和属性匹配共同使用 |

---

### 📌 简化写法

| 原写法 | 简化写法 | 精确匹配 | 模糊匹配 | 匹配开头 | 匹配结尾 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| `@id` | `#` | `#`或`#=` | `#:` | `#^` | `#$` | 简化写法只能单独使用 |
| `@class` | `.` | `.`或`.=` | `.:` | `.^` | `.$` | 简化写法只能单独使用 |
| `tag` | `t` | `t:`或`t=` | 无 | 无 | 无 | 只能用在句首 |
| `@tag()` | `@t()` | `@t():`或`@t()=` | 无 | 无 | 无 | 可作为属性组合使用 |
| `text` | `tx` | `tx=` | `tx:`或不写 | `tx^` | `tx$` | 无标签时使用模糊匹配文本 |
| `@text()` | `@tx()` | `@tx()=` | `@tx():` | `@tx()^` | `@tx()$` | 可作为属性组合使用 |
| `xpath` | `x` | `x:`或`x=` | 无 | 无 | 无 | 只能单独使用 |
| `css` | `c` | `c:`或`c=` | 无 | 无 | 无 | 只能单独使用 |

---

## ✅️ 相对定位

| 方法 | 说明 |
| --- | --- |
| `parent()` | 查找当前元素某一级父元素 |
| `child()` | 查找当前元素的一个直接子节点 |
| `children()` | 查找当前元素全部符合条件的直接子节点 |
| `next()` | 查找当前元素之后第一个符合条件的兄弟节点 |
| `nexts()` | 查找当前元素之后所有符合条件的兄弟节点 |
| `prev()` | 查找当前元素之前第一个符合条件的兄弟节点 |
| `prevs()` | 查找当前元素之前所有符合条件的兄弟节点 |
| `after()` | 查找文档中当前元素之后第一个符合条件的节点 |
| `afters()` | 查找文档中当前元素之后所有符合条件的节点 |
| `before()` | 查找文档中当前元素之前第一个符合条件的节点 |
| `befores()` | 查找文档中当前元素之前所有符合条件的节点 |

## ✅️ iframe 和 shadow root

| 方法 | 简化写法 | 说明 | 备注 |
| --- | --- | --- | --- |
| `get_frame()` | 无 | 在页面中查找一个`<iframe>`元素 | 只有页面对象有此方法 |
| `shadow_root` | `sr` | 获取当前元素内的 shadow root 对象 | 只有元素对象有此属性 |

---

## ✅️ 特殊字符对照表

要匹配的文本中如包含特殊字符（如`'&nbsp;'`、`'&gt;'`），需将特殊字符转为十六进制，对照表如下：

| 特殊符号 | 命名实体 | 编码 | 特殊符号 | 命名实体 | 编码 | 特殊符号 | 命名实体 | 编码 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `Α` | `&Alpha;` | \u0391 | `Β` | `&Beta;` | \u0392 | `Γ` | `&Gamma;` | \u0393 |
| `Δ` | `&Delta;` | \u0394 | `Ε` | `&Epsilon;` | \u0395 | `Ζ` | `&Zeta;` | \u0396 |
| `Η` | `&Eta;` | \u0397 | `Θ` | `&Theta;` | \u0398 | `Ι` | `&Iota;` | \u0399 |
| `Κ` | `&Kappa;` | \u039A | `Λ` | `&Lambda;` | \u039B | `Μ` | `&Mu;` | \u039C |
| `Ν` | `&Nu;` | \u039D | `Ξ` | `&Xi;` | \u039E | `Ο` | `&Omicron;` | \u039F |
| `Π` | `&Pi;` | \u03A0 | `Ρ` | `&Rho;` | \u03A1 | `Σ` | `&Sigma;` | \u03A3 |
| `Τ` | `&Tau;` | \u03A4 | `Υ` | `&Upsilon;` | \u03A5 | `Φ` | `&Phi;` | \u03A6 |
| `Χ` | `&Chi;` | \u03A7 | `Ψ` | `&Psi;` | \u03A8 | `Ω` | `&Omega;` | \u03A9 |
| `α` | `&alpha;` | \u03B1 | `β` | `&beta;` | \u03B2 | `γ` | `&gamma;` | \u03B3 |
| `δ` | `&delta;` | \u03B4 | `ε` | `&epsilon;` | \u03B5 | `ζ` | `&zeta;` | \u03B6 |
| `η` | `&eta;` | \u03B7 | `θ` | `&theta;` | \u03B8 | `ι` | `&iota;` | \u03B9 |
| `κ` | `&kappa;` | \u03BA | `λ` | `&lambda;` | \u03BB | `μ` | `&mu;` | \u03BC |
| `ν` | `&nu;` | \u03BD | `ξ` | `&xi;` | \u03BE | `ο` | `&omicron;` | \u03BF |
| `π` | `&pi;` | \u03C0 | `ρ` | `&rho;` | \u03C1 | `ς` | `&sigmaf;` | \u03C2 |
| `σ` | `&sigma;` | \u03C3 | `τ` | `&tau;` | \u03C4 | `υ` | `&upsilon;` | \u03C5 |
| `φ` | `&phi;` | \u03C6 | `χ` | `&chi;` | \u03C7 | `ψ` | `&psi;` | \u03C8 |
| `ω` | `&omega;` | \u03C9 | `ϑ` | `&thetasym;` | \u03D1 | `ϒ` | `&upsih;` | \u03D2 |
| `ϖ` | `&piv;` | \u03D6 | `•` | `&bull;` | \u2022 | `…` | `&hellip;` | \u2026 |
| `′` | `&prime;` | \u2032 | `″` | `&Prime;` | \u2033 | `‾` | `&oline;` | \u203E |
| `⁄` | `&frasl;` | \u2044 | `℘` | `&weierp;` | \u2118 | `ℑ` | `&image;` | \u2111 |
| `ℜ` | `&real;` | \u211C | `™` | `&trade;` | \u2122 | `ℵ` | `&alefsym;` | \u2135 |
| `←` | `&larr;` | \u2190 | `↑` | `&uarr;` | \u2191 | `→` | `&rarr;` | \u2192 |
| `↓` | `&darr;` | \u2193 | `↔` | `&harr;` | \u2194 | `↵` | `&crarr;` | \u21B5 |
| `⇐` | `&lArr;` | \u21D0 | `⇑` | `&uArr;` | \u21D1 | `⇒` | `&rArr;` | \u21D2 |
| `⇓` | `&dArr;` | \u21D3 | `⇔` | `&hArr;` | \u21D4 | `∀` | `&forall;` | \u2200 |
| `∂` | `&part;` | \u2202 | `∃` | `&exist;` | \u2203 | `∅` | `&empty;` | \u2205 |
| `∇` | `&nabla;` | \u2207 | `∈` | `&isin;` | \u2208 | `∉` | `&notin;` | \u2209 |
| `∋` | `&ni;` | \u220B | `∏` | `&prod;` | \u220F | `∑` | `&sum;` | \u2212 |
| `−` | `&minus;` | \u2212 | `∗` | `&lowast;` | \u2217 | `√` | `&radic;` | \u221A |
| `∝` | `&prop;` | \u221D | `∞` | `&infin;` | \u221E | `∠` | `&ang;` | \u2220 |
| `∧` | `&and;` | \u22A5 | `∨` | `&or;` | \u22A6 | `∩` | `&cap;` | \u2229 |
| `∪` | `&cup;` | \u222A | `∫` | `&int;` | \u222B | `∴` | `&there4;` | \u2234 |
| `∼` | `&sim;` | \u223C | `≅` | `&cong;` | \u2245 | `≈` | `&asymp;` | \u2245 |
| `≠` | `&ne;` | \u2260 | `≡` | `&equiv;` | \u2261 | `≤` | `&le;` | \u2264 |
| `≥` | `&ge;` | \u2265 | `⊂` | `&sub;` | \u2282 | `⊃` | `&sup;` | \u2283 |
| `⊄` | `&nsub;` | \u2284 | `⊆` | `&sube;` | \u2286 | `⊇` | `&supe;` | \u2287 |
| `⊕` | `&oplus;` | \u2295 | `⊗` | `&otimes;` | \u2297 | `⊥` | `&perp;` | \u22A5 |
| `⋅` | `&sdot;` | \u22C5 | `⌈` | `&lceil;` | \u2308 | `⌉` | `&rceil;` | \u2309 |
| `⌊` | `&lfloor;` | \u230A | `⌋` | `&rfloor;` | \u230B | `◊` | `&loz;` | \u25CA |
| `♠` | `&spades;` | \u2660 | `♣` | `&clubs;` | \u2663 | `♥` | `&hearts;` | \u2665 |
| `♦` | `&diams;` | \u2666 |  | `&nbsp;` | \u00A0 | `¡` | `&iexcl;` | \u00A1 |
| `¢` | `&cent;` | \u00A2 | `£` | `&pound;` | \u00A3 | `¤` | `&curren;` | \u00A4 |
| `¥` | `&yen;` | \u00A5 | `¦` | `&brvbar;` | \u00A6 | `§` | `&sect;` | \u00A7 |
| `¨` | `&uml;` | \u00A8 | `©` | `&copy;` | \u00A9 | `ª` | `&ordf;` | \u00AA |
| `«` | `&laquo;` | \u00AB | `¬` | `&not;` | \u00AC | `­` | `&shy;` | \u00AD |
| `®` | `&reg;` | \u00AE | `¯` | `&macr;` | \u00AF | `°` | `&deg;` | \u00B0 |
| `±` | `&plusmn;` | \u00B1 | `²` | `&sup2;` | \u00B2 | `³` | `&sup3;` | \u00B3 |
| `´` | `&acute;` | \u00B4 | `µ` | `&micro;` | \u0012 | `"` | `&quot;` | \u0022 |
| `<` | `&lt;` | \u003C | `>` | `&gt;` | \u003E | `'` |  | \u0027 |

<!-- https://www.drissionpage.cn/download/DownloadKit -->

# ⤵️ download方法

DrissionPage 每种页面对象都内置一个下载工具，提供任务管理、多线程并发、大文件分块、自动重连、文件名冲突处理等功能。

该工具现已独立打包成一个库，名为 DownloadKit，详细介绍见：[DownloadKit](http://drissionpage.cn/DownloadKitDocs)。

这里只介绍其主要功能，具体使用和设置方法请移步该文档。

## ✅️️ 功能简介

### 📌 支持该工具的对象

以下对象均支持

- `SessionPage`
- `ChromiumTab`
- `MixTab`
- `ChromiumFrame`
- `ChromiumPage`
- `WebPage`

---

### 📌 下载器功能

- 可下载指定 url 文件
- 支持多线程并发下载多个文件
- 大文件自动分块使用多线程下载
- 可对现有文件追加数据
- 自动创建目标路径
- 下载时支持文件重命名
- 自动处理文件名冲突
- 自动去除路径和文件名中非法字符
- 支持 post 方式
- 支持自定义连接参数
- 任务失败自动重试

注意

`DownloadKit`是对 requests 封装实现的，不是调用浏览器功能。
如果下载目标对 headers、data 等有要求，必需手动添加。

---

## ✅️️ 添加任务

### 📌 单线程任务

使用`download()`方法可添加单线程任务，该方法是阻塞式 的，且只使用一个线程。

**示例：**

```python
from DrissionPage import SessionPage

page = SessionPage()
url = 'https://www.baidu.com/img/flexible/logo/pc/result.png'
save_path = r'C:\download'

res = page.download(url, save_path)
print(res)
```

显示：

```shell
url：https://www.baidu.com/img/flexible/logo/pc/result.png
文件名：result.png
目标路径：C:\download
100% 下载完成 C:\download\result.png

('success', 'C:\\download\\result.png')
```

---

### 📌 并发任务

使用`download.add()`添加并发任务。

**示例：**

```python
url1 = 'https://dldir1.qq.com/qqfile/qq/TIM3.4.8/TIM3.4.8.22092.exe'
url2 = 'https://dldir1.qq.com/qqfile/qq/PCQQ9.7.16/QQ9.7.16.29187.exe'
save_path = 'files'

page = SessionPage()
page.download.add(url1, save_path)
page.download.add(url2, save_path)
```

---

### 📌 文件分块并行下载

使用`download.add()`方法的`split`参数可设置大文件是否分块下载。

使用`download.set.block_size()`方法可设置分块大小。

默认情况下载，超过 50M 的文件会自动分块下载。

**示例：**

```python
page = SessionPage()
page.download.set.block_size('30m')  # 设置分块大小
page.download.add('http://****/demo.zip')  # 默认分块下载
page.download.add('http://****/demo.zip', split=False)  # 不使用分块下载
```

---

### 📌 阻塞式多线程任务

使用并行分块下载时，也可以使任务逐个下载，在`add()`后使用`wait()`即可。

**示例：**

```python
page = SessionPage()
page.download.add('http://****/demo.zip').wait()
page.download.add('http://****/demo.zip').wait()
```

---

### 📌 详细使用文档

以上仅是普通示例，详细功能请查阅：[DownloadKit 添加任务](http://drissionpage.cn/DownloadKitDocs/usage/add_missions/)

---

## ✅️️ 下载设置

### 📌 全局设置

使用`download.set.****()`方法，可对默认下载行为进行设置。

包括以下设置：

- 保存路径
- 允许使用的线程总数
- 是否启用分块下载
- 分块大小
- 连接失败重试次数
- 重试间隔
- 连接超时时间
- 文件名冲突时的处理方式
- 日志和显示相关设置

---

### 📌 每个任务单独设置

新建任务时，`download()`和`add()`方法的参数可对当前任务进行参数设置，覆盖全局设置。

详见上文添加参数的文档。

---

### 📌 详细使用文档

详细设置功能请查阅：[DownloadKit 运行设置](http://drissionpage.cn/DownloadKitDocs/usage/settings/)

---

## ✅️️ 任务管理

### 📌 任务对象

对象`Mission`用于管理任务，有以下功能：

- 查看任务状态、信息、进度
- 保存任务参数，如 url、连接参数等
- 取消进行中的任务
- 删除已下载的文件

---

### 📌 获取单个任务对象

使用`download.add()`添加任务时，会返回一个任务对 象。

**示例：**

```python
mission = page.download.add('http://****.pdf')
print(mission.id)  # 获取任务id
print(mission.rate)  # 打印下载进度（百分比）
print(mission.state)  # 打印任务状态
print(mission.info)  # 打印任务信息
print(mission.result)  # 打印任务结果
```

除添加任务时获取对象，也可以使用`download.get_mission()`获取。在上一个示例中可以看到，任务对象有`id`属性，把任务的`id`传入此方法，会返回该任务对象。

**示例：**

```python
mission_id = mission.id
mission = page.download.get_mission(mission_id)
```

---

### 📌 获取全部任务对象

使用页面对象的`download.missions`属性，可以获取所有下载任务。该属性返回一个`dict`，保存了所有下载任务。以任务对象的`id`为 key。

```python
page.download_set.save_path(r'D:\download')
page.download('http://****/****1.pdf')
page.download('http://****/****1.pdf')
print(page.download.missions)
```

**输出：**

```text
{
    1: <Mission 1 D:\download\xxx1.pdf xxx1.pdf>
    2: <Mission 2 D:\download\xxx1_1.pdf xxx1_1.pdf>
    ...
}
```

---

### 📌 获取下载失败的任务

使用`download.get_failed_missions()`方法，可以获取下载失败的任务列表。

```python
page.download_set.save_path(r'D:\download')
page.download('http://****/****1.pdf')
page.download('http://****/****1.pdf')
print(page.download.get_failed_missions()
```

**输出：**

```text
[
    <Mission 1 状态码：404 None>,
    <Mission 2 状态码：404 None>
    ...
]
```

Tips

获取失败任务对象后，可从其`data`属性读取任务内容，以便记录日志或择机重试。

---

### 📌 详细使用文档

详细设置功能请查阅：[DownloadKit 任务管理](http://drissionpage.cn/DownloadKitDocs/usage/misssions/)

<!-- https://www.drissionpage.cn/download/browser -->

# ⤵️ 浏览器下载

本节介绍对浏览器下载任务进行设置的功能。

## ✅️ 概述

### 📌 功能

DrissionPage 提供以下功能，用于对浏览器下载任务进行控制：

- 每个 tab 对象可独立设置文件保存路径
- 下载前可指定文件名称，实现文件重命名
- 可设置存在同名文件时的处理方式
- 可获取任务下载进度
- 可等待下载任务结束
- 可取消任务
- 可拦截下载任务并获取其信息

---

## ⚠️ 注意事项

### 📌 记得等待任务结束

因技术原因，程序在下载结束时才能对其重命名，在这之前文件名是临时的任务 id。

因此必需等待下载完毕，文件名才能正确命名。无论是否指定文件名都一样。

**示例：**

```python
tab = Chromium().latest_tab
tab('#button').click()  # 点击下载按钮
tab.wait.download_begin()  # 等待下载开始
tab.wait.downloads_done()  # 等待所有任务结束
```

---

### 📌 多 Tab 操作时推荐设置临时路径

程序需要把任务下载到一个指定位置，完成后再移动到目标路径。

因此，如果程序涉及多个 Tab 触发下载任务，最好给`Chromium`对象设置一个下载路径。

即使每个 Tab 对象都设置了自己的路径。

**示例：**

```python
from DrissionPage import Chromium

browser = Chromium()
browser.set.download_path('tmp')  # 设置总路径

tab1 = browser.get_tab(1)
tab1.set.download_path('path1')

tab2 = browser.get_tab(2)
tab2.set.download_path('path2')
```

---

### 📌 启动下载管理功能

本节介绍的下载管理功能默认不开启，此时触发下载任务和手动操作没有区别。

当启动配置中设置了下载路径，或调用`set.download_path()`方法时，管理功能才会启动。

使用`click.to_download()`方法会自动自动此功能。

---

## ✅️ `click.to_download()`

当预期点击元素后会触发下载，可使用此方法返回下载任务。

使用时可以同时设置下载路径、指定文件名名称。

注意

- 有些下载任务是点击后弹出新标签页，在新标签页触发下载，此时必须设置`new_tab=True`
- 点击后等待下载触发时间为页面对象`timeout`属性（默认10秒），如果需要更久的等待，用下文介绍的方法。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `save_path` | `str` `Path` | 必填 | 保存路径，为`None`保存在原来设置的，如未设置保存到当前路径 |
| `rename` | `str` | `None` | 重命名文件名，为`None`则不修改 |
| `suffix` | `str` | `None` | 指定文件后缀，为`None`则不 修改 |
| `new_tab` | `bool` | `False` | 预期的下载是否在新标签页中触发 |
| `by_js` | `bool` | `False` | 是否用 js 方式点击，逻辑与`click()`一致 |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`时使用页面对象默认超时时间 |

| 返回类型 | 说明 |
| --- | --- |
| `DownloadMission` | 下载任务对象 |

**示例：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('https://im.qq.com/pcqq/index.shtml')
ele = tab('全新体验版下载')
ele.wait.has_rect()
mission = ele.click.to_download(save_path='tmp', rename='QQ.exe')
mission.wait()
```

`click.to_download()`方法能够应付多数情况，不是点击触发的下载任务或更复杂的情况，请根据下文介绍的配置方式使用。

---

## ✅️ 设置下载路径

### 📌 设置总下载路径

使用`Chromium`对象的`set.download_path()`方法设置下载路径。不设置时，默认下载到程序当前路径。

`Chromium`对象设置下载路径后，后续新建的 Tab 对象均会使用该路径，之前建立的 Tab 对象使用的路径则不会改变。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `path` | `str` `Path` | 必填 | 下载路径 |

**返回：**`None`

**示例：**

```python
from DrissionPage import Chromium

browser = Chromium()
browser.set.download_path(r'C:\tmp')
```

---

### 📌 设置 Tab 下载路径

使用方法与设置`Chromium`的一致，但只在当前 Tab 对象生效。

**示例：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.set.download_path(r'C:\tmp1')  # 设置Tab下载路径
```

---

## ✅️ 设置文件名

使用`download_file_name()`方法，可在下载前设置文件名，实现下载文件的重命名。

设置的文件名可以不带后缀，程序会根据下载的文件自动补充后缀。

如设置的文件名带`'.'`，且后缀与网络文件不一致，程序会以网络文件的后缀为准。

如果想修改后缀名，设置`suffix`参数即可。

每次触发下载后，该设置会被清空。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | `None` | 文件名 |
| `suffix` | `str` | `None` | 文件后缀名，传入`''`可去除后缀 |

**返回：**`None`

**示例：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.set.download_file_name('new_file')
tab('t:a').click()  # 点击一个会触发下载的链接
mission = tab.wait.download_begin()
mission.wait()  # 记得等待任务触发和结束
```

---

## ✅️ 等待

### 📌 等待下载开始

点击下载链接后，下载并不会瞬间触发，需要进行等待，才能将其捕获。

使用`wait.download_begin()`方法等待下载开始。

一般来说，标签页触发的下载任务用 Tab 对象进行等待，未被控制的标签页触发的下载，可由`Chromium`对象进行等待。

`cancel_it`参数为`True`时，捕获到任务时会将其取消，以便将返回的下载信息用于其它需要。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 超时时间（秒），`None`为页面默认等待时间 |
| `cancel_it` | `bool` | `False` | 是否取消该任务 |

| 返回类型 | 说明 |
| --- | --- |
| `DownloadMission` | 等待成功且`cancel_it`为`False`时返回下载任务对象 |
| `dict` | 等待成功且`cancel_it`为`True`时返回下载任务信息 |
| `False` | 等待失败返回`False` |

**示例：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab('t:a').click()  # 点击一个会触发下载的链接
tab.wait.download_begin()
```

---

### 📌 等待所有下载任务结束

用`Chromium`对象的`wait.downloads_done()`方法可等待浏览器所有下载任务结束。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`时无限等待 |
| `cancel_if_timeout` | `bool` | `False` | 如超时是否取消未完成的任务 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否等待成功 |

---

### 📌 等待某 Tab 所有下载任务结束

用 Tab 对象的`wait.downloads_done()`方法可等待该 Tab 对象触发点下载任务结束。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`时无限等待 |
| `cancel_if_timeout` | `bool` | `False` | 如超时是否取消未完成的任务 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否等待成功 |

---

## ✅️ 拦截下载任务

`wait.download_begin()`方法有个`cancel_it`参数，当为`True`时，会取消下载任务。

此时可 使用该方法返回的任务信息进行下一步操作，如改用`download()`方法下载等。

**示例：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab('t:a').click()
data = tab.wait.download_begin(cancel_it=True)
tab.download(data.url)
```

---

## ✅️ 同名文件的处理

下载遇到同名 文件时，可选择三种处理方式：自动重命名、覆盖、跳过。

使用`set.when_download_file_exists('****')`进行设置。

其中`****`可选`'rename'`、`'overwrite'`、`'skip'`。

也可选择它们的首字母`'r'`、`'o'`、`'s'`。

### 📌 自动重命名

设置方法：`set.when_download_file_exists('rename')`

这种方式遇到已有同名文件时会自动将新文件重命名，方式是在后面加上序号。

假设保存路径已存在名为 'abc.zip' 的文件，再下载一个 'abc.zip' 时，新文件会自动重命名为 'abc\_1.zip'。

之后再下载会命名为 'abc\_2.zip'，如此类推。

---

### 📌 覆盖已有文件

设置方法：`set.when_download_file_exists('overwrite')`

这种方式会把原有的同名文件替换成新下载的。

---

### 📌 跳过

设置方法：`set.when_download_file_exists('skip')`

这种方式下，发现已有同名文件时会取消下载任务。

---

## ✅️ 任务管理

`wait.download_begin()`方法会返回`DownloadMission`对象，用于浏览器下载任务的管理。

### 📌 获取任务信息

可获取任务状态、进度、保存路径、文件名等信息。

| 属性名称 | 类型 | 说明 |
| --- | --- | --- |
| `url` | `str` | 返回任务网址 |
| `tab_id` | `str` | 触发任务的 Tab 对象 id |
| `id` | `str` | 任务 id |
| `folder` | `str` | 保存文件夹路径 |
| `name` | `str` | 文件名 |
| `tmp_path` | `str` | 临时文件保存路径 |
| `state` | `str` | 任务状态，'running', 'done', 'canceled', 'skipped' |
| `total_bytes` | `int` | 总字节数 |
| `received_bytes` | `int` | 已接收字节数 |
| `final_path` | `str` `None` | 最终完整路径，任务完成后才产生 |

**示例：**

实时打印任务进度。

```python
mission = tab.wait.download_begin()
while not mission.is_done:
    print(f'\r{mission.rate}%', end='')
```

---

### 📌 等待任务结束

使用`DownloadMission`对象的`wait()`方法，可等待任务结束。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `show` | `bool` | `True` | 是否打印下载信息 |
| `timeout` | `float` | `None` | 超时时间（秒），`None`为无限等待 |
| `cancel_if_timeout` | `bool` | `False` | 如超时是否取消该任务 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 下载完成返回最终保存路径 |
| `False` | 超时或被取消返回`False` |

---

### 📌 取消任务

使用`DownloadMission`对象的`cancel()`方法，可取消任务。

调用该方法，已下载的文件会被删除，即使是已完成的任务。

<!-- https://www.drissionpage.cn/get_start/installation -->

# 🌏 安装

## ✅️️ 运行环境

操作系统：Windows、Linux 和 Mac

Python 版本：3.6 及以上

支持：Chromium 内核浏览器（如 Chrome 和 Edge）、electron 应用

---

## ✅️️ 安装

请使用 pip 安装：

```shell
pip install DrissionPage
```

---

## ✅️️ 升级

### 📌 升级最新稳定版

```shell
pip install DrissionPage --upgrade
```

---

### 📌 指定版本升级

```shell
pip install DrissionPage==4.0.0b17
```

<!-- https://www.drissionpage.cn/get_start/import -->

# 🌏 导入

DrissionPage 提供的功能放在以下几个路径：

- `from DrissionPage import ****`：浏览器类、配置类、页面类
- `from DrissionPage.errors import ****`：异常
- `from DrissionPage.common import ****`：辅助工具
- `from DrissionPage.items import ****`：衍生对象，用于类型判断

## ✅️ 浏览器类

### 📌 `Chromium`

浏览器类用于连接浏览器、管理标签页及其它和浏览器总体有关的操作。

浏览器类相当于总管，它可以作为浏览器入口，使用它产生 Tab 对象去操控每个标签页。

```python
from DrissionPage import Chromium
```

---

## ✅️ 页面类

### 📌 `ChromiumPage`

`ChromiumPage`是将浏览器对象和第一个标签页对象封装在一起，用于控制浏览器。

`ChromiumPage`只是简化了操作，使用效果和直接使用`Chromium`对象基本一致。

唯一区别是，`ChromiumPage`生成的标签页对象是`ChromiumTab`，不能切换模式。

```python
from DrissionPage import ChromiumPage
```

---

### 📌 `WebPage`

`WebPage`与`ChromiumPage`相似，不过其自身及其产生的 Tab 对象可切换模式，既可控制浏览器，也可收发数据包。

```python
from DrissionPage import WebPage
```

---

### 📌 `SessionPage`

`SessionPage`用于收发数据包，是对 requests 和 lxml 进行封装实现的。

它把网络连接和结果解析封装成页面。操作逻辑和其它页面一致。

```python
from DrissionPage import SessionPage
```

---

## ✅️ 配置工具

### 📌 `ChromiumOptions`

`ChromiumOptions`类用于设置浏览器启动参数。

这些参数只有在启动浏览器时有用，接管已存在的浏览器时是不生效的。

```python
from DrissionPage import ChromiumOptions
```

---

### 📌 `SessionOptions`

`SessionOptions`类用于设置`Session`对象启动参数。

用于配置`SessionPage`或`WebPage`的 s 模式的连接参数。

```python
from DrissionPage import SessionOptions
```

---

### 📌 `Settings`

`Settings`用于设置全局运行配置，如找不到元素时是否抛出异常等。

```python
from DrissionPage.common import Settings
```

---

## ✅️ 辅助工具

### 📌 `Keys`

键盘按键类，用于键入 ctrl、alt 等按键。

```python
from DrissionPage.common import Keys
```

---

### 📌 `By`

与 selenium 一致的`By`类，便于项目迁移。

```python
from DrissionPage.common import By
```

---

### 📌 其它工具

这些工具都在`DrissionPage.common`路径中。

- `wait_until`：可等待传入的方法结果为真
- `make_session_ele`：从 html 文本生成`ChromiumElement`对象
- `configs_to_here`：把配置文件复制到当前路径
- `get_blob`：获取指定的 blob 资源
- `tree`：用于打印页面对象或元素对象结构
- `from_selenium`：用于对接 selenium 代码
- `from_playwright`：用于对接 playwright 代码

```python
from DrissionPage.common import wait_until
from DrissionPage.common import make_session_ele
from DrissionPage.common import configs_to_here
```

---

## ✅️ 异常

异常放在`DrissionPage.errors`路径。

全部异常详见进阶使用章节。

```python
from DrissionPage.errors import ElementNotFoundError
```

---

## ✅️ 衍生对象类型

Tab、Element 等被其它对象生成的对象，开发过程中需要类型判断时需要导入这些类型。

可在`DrissionPage.items`路径导入。

```python
from DrissionPage.items import SessionElement
from DrissionPage.items import ChromiumElement
from DrissionPage.items import ShadowRoot
from DrissionPage.items import NoneElement
from DrissionPage.items import ChromiumTab
from DrissionPage.items import MixTab
from DrissionPage.items import ChromiumFrame
```

<!-- https://www.drissionpage.cn/get_start/set_lang -->

# 🌏 设置语言 / Set Language

DrissionPage 的报错信息及提示支持中文和英文。

DrissionPage error messages and prompts are available in Chinese and English.

## ✅️ 设置方法 / Usage

```python
from DrissionPage.common import Settings

Settings.set_language('en')  # 设置为中文时，填入'zh_cn'
```

<!-- https://www.drissionpage.cn/get_start/before_start -->

# 🌏 准备工作

开始前，我们先设置一下浏览器路径。

如果只使用收发数据包功能，无需任何准备工作。

程序默认控制 Chrome，所以下面用 Chrome 演示。
如果要使用 Edge 或其它 Chromium 内核浏览器，设置方法是一样的。

注意

尽量使用版本号在 100 以上的浏览器，旧版有些功能不支持。

## 1️⃣ 尝试启动浏览器

默认状态下，程序会自动在系统内查找 Chrome 路径。

执行以下代码，浏览器启动并且访问了项目官网，说明可直接使用，跳过后面的步骤即可。

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('http://DrissionPage.cn')
```

---

## 2️⃣ 设置路径

如果上面的步骤提示出错，说明程序没在系统里找到 Chrome 浏览器。

可用以下其中一种方法设置，设置会持久化记录到默认配置文件，之后程序会使用该设置启动。

获取浏览器路径的方法

- 这里的浏览器路径不一定是 Chrome，Edge 等 Chromium 内核的浏览器都可以。
- 打开浏览器，在地址栏输入`chrome://version`（Edge 输入`edge://version`），回车。
  ![](/assets/images/find_browser_path-1b46b5e4ba053115091a598d3b4211ac.png)
  如图所示，红框中就是要获取的路径。
  此法不限于 Windows，有界面的 Linux 也可使用。

## 📌 方法一

新建一个临时 py 文件，并输入以下代码，填入您电脑 里的 Chrome 浏览器可执行文件路径，然后运行。

```python
from DrissionPage import ChromiumOptions

path = r'D:\Chrome\Chrome.exe'  # 请改为你电脑内Chrome可执行文件路径
ChromiumOptions().set_browser_path(path).save()
```

这段代码会把浏览器路径记录到配置文件，今后启动浏览器皆使用该路径。

如果是想临时切换浏览器路径以尝试运行和操作是否正常，可以去掉`.save()`，以如下方式结合第1️⃣步的代码。

```python
from DrissionPage import Chromium, ChromiumOptions

path = r'D:\Chrome\Chrome.exe'  # 请改为你电脑内Chrome可执行文件路径
co = ChromiumOptions().set_browser_path(path)
tab = Chromium(co).latest_tab
tab.get('http://DrissionPage.cn')
```

## 📌 方法二

在命令行输入以下命令（路径改成自己电脑里的）：

```shell
dp -p "D:\Chrome\chrome.exe"
```

注意

- 注意命令行的 python 环境与项目应是同一个
- 注意要先使用 cd 命令定位到项目路径

---

## 3️⃣ 重试控制浏览器

现在，请重新执行第1️⃣步的代码，如果正确访问了项目官网，说明已经设置完成。

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
tab.get('http://DrissionPage.cn')
```

---

## ✅️️ 说明

当您完成准备工作后，无需关闭浏览器，后面的上手示例可继续接管当前浏览器。

<!-- https://www.drissionpage.cn/get_start/examples/control_browser -->

# 🗺️ 自动登录

本示例演示控制浏览器登录 gitee 网站。

## ✅️️ 页面分析

网址：<https://gitee.com/login>

打开网址，按`F12`，我们可以看到页面 html 如下：

![](/assets/images/gitee_1-a0c506a07b80ba8c2713bf306a475c2e.jpg)

用户名输入框`id`为`'user_login'`，密码输入框`id`为`'user_password'`，登录按钮`value`为`'登 录'`。

我们可以用这三个属性定位这三个元素，然后对其输入数据和点击。

---

## ✅️️ 示例代码

您可以把以下代码复制到编辑器，把账号和密码改为您自己的，可直接执行看到运行结果。

```python
from DrissionPage import Chromium

# 启动或接管浏览器，并获取标签页对象
tab = Chromium().latest_tab
# 跳转到登录页面
tab.get('https://gitee.com/login')

# 定位到账号文本框，获取文本框元素
ele = tab.ele('#user_login')
# 输入对文本框输入账号
ele.input('您的账号')
# 定位到密码文本框并输入密码
tab.ele('#user_password').input('您的密码')
# 点击登录按钮
tab.ele('@value=登 录').click()
```

---

## ✅️️ 示例详解

我们逐行解读代码：

```python
from DrissionPage import Chromium
```

↑ 首先，我们导入用于控制浏览器的类`Chromium`。

```python
tab = Chromium().latest_tab
```

↑ 接下来，我们创建一个`Chromium`对象，用于连接浏览器，并用`latest_tab`获取一个标签页对象。

```python
tab.get('https://gitee.com/login')
```

↑ `get()`方法用于访问参数中的网址。它会等待页面完全加载，再继续执行后面的代码。
您也可以修改等待策略，如等待 DOM 加载而不等待资源下载，就停止加载，这将在后面的章节说明。

```python
ele = tab.ele('#user_login')
```

↑ `ele()`方法用于查找元素，它返回一个`ChromiumElement`对象，用于操作元素。

`'#user_login'`是定位符文本，`#`意思是按`id`属性查找元素。

值得一提的是，`ele()`内置了等待，如果元素未加载，它会执行等待，直到元素出现或到达时限。默认超时时间 10 秒。

```python
ele.input('您的账 号')
```

↑ `input()`方法用于对元素输入文本。

```python
tab.ele('#user_password').input('您的密码')
```

↑ 我们也可以进行链式操作，获取元素后直接输入文本。

```python
tab.ele('@value=登 录').click()
```

↑ 输入账号密码后，以相同的方法获取按钮元素，并对其执行点击操作。

不同的是，这次通过其`value`属性作为查找条件。`@`表示按属性名查找。

到这里，我们已完成了自动登录 gitee 网站的操作。

<!-- https://www.drissionpage.cn/get_start/concept -->

# ☀️ 基本概念

本节讲解 DrissionPage 的一些基本概念。了解它大概的构成。

如果您觉得有点懵，可直接跳过本节。

## ✅️️ 网页自动化

网页自动化的形式通常有两种，它们各有优劣：

- 直接向服务器发送数据包，获取需要的数据
- 控制浏览器跟网页进行交互

前者轻量级，速度快，便于多线程、分布式部署，如 requests 库。但当数据包构成复杂，甚至加入加密技术时，开发过程烧脑程度直线上升。

鉴于此，DrissionPage 以页面为单位将两者整合，对 Chromium 协议 和 requests 进行了重新封装，实现两种模式的互通，并加入常用的页面和元素控制功能，可大幅降低开发难度和代码量。
用于操作浏览器的对象叫 Driver，requests 用于管理连接的对象叫 Session，Drission 就是它们两者的合体。Page 表示以页面为单位使用。

在旧版本，本库是通过对 selenium 和 requests 的重新封装实现的。
从 3.0 版开始，作者另起炉灶，自行实现了 selenium 全部功能，从而摆脱了对 selenium 的依赖，功能更多更强，运行效率更高，开发更灵活。
4.0 则在 3.0 经验的基础上对整个项目底层进行了重构，逻辑更合理。

如果您想了解旧版，请查阅“旧版 使用方法”章节。

---

## ✅️️ 基本使用逻辑

无论是控制浏览器，还是收发数据包，其操作逻辑是一致的。

即先创建页面对象，然后从页面对象中获取元素对象，通过对元素对象的读取或操作，实现数据的获取或页面的控制。

因此，最主要的对象就是两种：页面对象，及其生成的元素对象。

---

## ✅️️ 主要对象

### 📌 浏览器和标签页对象

- `Chromium`：浏览器对象，用于连接浏览器、管理标签页及其它和浏览器总体有关的操作
- `MixTab`：浏览器标签页对象，由`Chromium`对象产生，一个对象控制一个实际的标签页
- `ChromiumTab`：和`MixTab`一样也是标签页对象，由`ChromiumPage`对象产生，不可切换收发数据包模式

### 📌 元素对象

- `ChromiumElement`：浏览器元素对象
- `SessionElement`：静态元素对象
- `ChromiumFrame`：`<iframe>`元素对象，兼有标签页对象和元素特性
- `ShadowRoot`：shadow-root 元素对象

### 📌 Page 对象

- `ChromiumPage`：能管理浏览器本身的标签页对象，可用作程序入口
- `WebPage`：类似于`ChromiumPage`，整合浏览器控制和收发数据包于一体的页面对象
- `SessionPage`：单纯用于收发数据包的页面对象，可单独使用

### 📌 称呼

文档里经常用到这几个称呼：

- `MixTab`、`ChromiumTab`统称为 Tab 对象
- `ChromiumPage`、`WebPage`和`SessionPage`统称为 Page 对象
- Page 对象、Tab 对象和`ChromiumFrame`统称为页面对象

---

## ✅️️ 对象关系图

下图列出本库中要用到的各种对象的生成关系。

```text
├─ SessionPage
|     └─ SessionElement
|           └─ SessionElement
├─ Chrmoium
|     └─ MixTab
|           ├─ ChromiumElement
|           |    ├─ ChromiumElement
|           |    ├─ ChromiumFrame
|           |    └─ SessionElement
|           ├─ SessionElement
|           |    └─ SessionElement
|           ├─ ChromiumFrame
|           |    ├─ ChromiumElement
|           |    ├─ ChromiumFrame
|           |    └─ SessionElement
|           └─ ShadowRoot
|                ├─ ChromiumElement
|                ├─ ChromiumFrame
|                └─ SessionElement
├─ SessionOptions
└─ ChrmoiumOptions
```

---

## ✅️️ 工作模式

`MixTab`和`WebPage`既可控制浏览器，也可用数据包方式访问网络数据。
它们有两种工作方式：d 模式和 s 模式。
页面对象可以在这两种模式间切换，两种模式拥有一致的使用方法，但任一时间只能处于其中一种模式。

### 📌 d 模式

d 模式既表示 Driver，还有 Dynamic 的意思。
d 模式用于控制浏览器，不仅可以读取浏览器获取到的信息，还能对页面进行操作， 如点击、填写、开关标签页、改变元素属性、执行 js 脚本等等。
d 模式功能强大，但运行速度受浏览器制约非常缓慢，而且需要占用大量内存。

---

### 📌 s 模式

s 模式既表示 Session，还有 speed、silence 的意思。
s 模式的运行速度比 d 模式快几个数量级，但只能基于数据包进行读取或发送，不能对页面进行操作，不能运行 js。
爬取数据时，如网站数据包较为简单，应首选 s 模式。

---

### 📌 模式切换

`MixTab`和`WebPage`对象可以在 d 模式和 s 模式之间切换，这通常用于以下情况：

- 当登录验证很严格，难以解构，如有验证码的时候，用浏览器处理登录，然后转换成 s 模式爬取数据。既避免了处理烧脑的 js，又能享受 s 模式的速度。
- 页面数据由 js 产生，且页面结构极其复杂，可以用 d 模式读取页面元素，然后把元素转成 s 模式的元素进行分析。可以极大地提高 d 模式的处理速度。

---

## ✅️️ 配置管理

无论 requests 还是浏览器，都通常需要一些配置信息才能正常工作，如长长的`user_agent`、浏览器 exe 文件路径、浏览器配置等。
这些代码往往是繁琐而重复的，不利于代码的简洁。
因此，DrissionPage 使用配置文件记录常用配置信息，程序会自动读取默认配置文件里的内容。
所以，在示例中，通常看不见配置信息的代码。

这个功能支持用户保存不同的配置文件，按情况调研，也可以支持直接把配置写在代码里面，屏蔽读取配置文件。

Tips

当需要打包程序时，必需把配置写到代码里，或打包后手动复制配置文件到运行路径，否则会报错。详见相关章节。

### 📌 `SessionOptions`

用于`SessionPage`和`WebPage` s 模式的配置对象。

---

### 📌 `ChromiumOptions`

用于用于浏览器的配置对象。

---

## ✅️️ 定位符

定位符用于定位页面中的元素，是本库一大特色，能够用非常简明的方式来获取元素，简洁易用。
可读性和易用性高于 xpath 等其它方式，并且兼容 xpath、css selector、selenium 定位符。

以下是一组对比：

定位文本包含`'abc'`的元素：

```python
# DrissionPage
ele = tab('abc')

# selenium
ele = driver.find_element(By.XPATH, '//*[contains(text(), "abc"]')
```

定位 class 为`'abc'`的元素：

```python
# DrissionPage
ele = tab('.abc')

# selenium
ele = driver.find_element(By.CLASS_NAME, 'abc')
```

定位 ele 元素的兄弟元素：

```python
# DrissionPage
ele1 = ele.next()  # 获取后一个元素
ele1 = ele.prev(index=2)  # 获取前面第二个元素

# selenium
ele1 = ele.find_element(By.XPATH, './/following-sibling::*')  # 获取有i一个元素
ele1 = ele.find_element(By.XPATH, './/preceding-sibling::*[2]')  # 获取前面第二个元素
```

显然，本库的定位语句更简洁易懂，还有很多灵活好用的方法，详见 “查找元素” 章节。

<!-- https://www.drissionpage.cn/get_start/examples/data_packets -->

# 🗺️ 收发数据包

本示例演示用`SessionPage`已收发数据包的方式采集 gitee 网站数据。

本示例不使用浏览器。

## ✅️️ 页面分析

网址：<https://gitee.com/explore/all>

这个示例的目标，要获取所有库的名称和链接，为避免对网站造成压力，我们只采集 3 页。

打开网址，按`F12`，我们可以看到页面 html 如下：

![](/assets/images/gitee_2-a46709588060c6c79e04dd943765307a.jpg)

从 html 代码中可以看到，所有开源项目的标题都是`class`属性为`'title project-namespace-path'`的`<a>`元素。我们可以遍历这些`<a>`元素，获取它们的信息。

同时，我们观察到，列表页网址是以页数为参数访问的，如第一页 url 为`https://gitee.com/explore/all?page=1`，页数就是`page`参数。因此我们可以通过修改这个参数访问不同的页面。

---

## ✅️️ 示例代码

以下代码可直接运行并查看结果：

```python
from DrissionPage import SessionPage

# 创建页面对象
page = SessionPage()

# 爬取3页
for i in range(1, 4):
    # 访问某一页的网页
    page.get(f'https://gitee.com/explore/all?page={i}')
    # 获取所有开源库<a>元素列表
    links = page.eles('.title project-namespace-path')
    # 遍历所有<a>元素
    for link in links:
        # 打印链接信息
        print(link.text, link.link)
```

**输出：**

```shell
小熊派开源社区/BearPi-HM_Nano https://gitee.com/bearpi/bearpi-hm_nano
明月心/PaddleSegSharp https://gitee.com/raoyutian/PaddleSegSharp
RockChin/QChatGPT https://gitee.com/RockChin/QChatGPT
TopIAM/eiam https://gitee.com/topiam/eiam

以下省略。。。
```

---

## ✅️️ 示例详解

我们逐行解读代码：

```python
from DrissionPage import SessionPage
```

↑ 首先，我们导入用于收发数据包的页面类`SessionPage`。

```python
page = SessionPage()
```

↑ 接下来，我们创建一个`SessionPage`对象。

```python
for i in ranage(1, 4):
    page.get(f'https://gitee.com/explore/all?page={i}')
```

到剪贴板" title="复制" class="clean-btn">

↑ 然后我们循环 3 次，以构造每页的 url，每次都用`get()`方法访问该页网址。

```python
    links = page.eles('.title project-namespace-path')
```

↑ 访问网址后，我们用页面对象的`eles()`获取页面中所有`class`属性为`'title project-namespace-path'`的元素对象。

`eles()`方法用于查找多个符合条件的元素，返回由它们组成的`list`。

这里查找的条件是`class`属性，`.`表示按`class`属性查找元素。

```python
    for link in links:
        print(link.text, link.link)
```

↑ 最后，我们遍历获取到的元素列表，获取每个元素的属性并打印出来。

`.text`获取元素的文本，`.link`获取元素的`href`或`src`属性。

<!-- https://www.drissionpage.cn/get_start/examples/switch_mode -->

# 🗺️ 模式切换

这个示例演示标签页对象如何切换控制浏览器和收发数据包两种模式。

通常，切换模式是用来应付登录检查很严格的网站，可以用浏览器处理登录，再转换模式用收发数据包的形式来采集数据。
但是这种场景需要有对应的账号，不便于演示。演示使用浏览器在 gitee 搜索，然后转换到收发数据包的模式来读取数据。
虽然此示例现实使用意义不大，但可以了解其工作模式。

## ✅️️ 页面分析

网址：<https://gitee.com/explore>

打开网址，按`F12`，我们可以看到页面 html 如下：

![](/assets/images/change1-bac86dfcdb35ce852aaa00390c5100f1.png)

输入框`<input>`元素`id`属性为`'q'`，搜索按钮`<button>`元素`文本`包含`'搜索'`文本，可用来作条件查找元素。

输入关键词搜索后，再查看页面 html：

![](/assets/images/change2-5177047ea61c4c245d44736eeb34d8fd.png)

通过分析 html 代码，我们可以看出，每个结果的标题都存在`id`为`'hits-list'`里面，`class`为`'item'`的元素中。因此，我们可以获取页面中所有这些元素，再遍历获取其信息。

---

## ✅️️ 示例代码

您可以直接运行以下代码：

```python
from DrissionPage import Chromium

# 连接浏览器并获取一个MixTab对象
tab = Chromium().latest_tab
# 访问网址
tab.get('https://gitee.com/explore/all')
# 切换到收发数据包模式
tab.change_mode()
# 获取所有行元素
items = tab.ele('.ui relaxed divided items explore-repo__list').eles('.item')
# 遍历获取到的元素
for item in items:
    # 打印元素文本
    print(item('t:h3').text)
    print(item('.project-desc mb-1').text)
    print()
```

**输出：**

```shell
dromara/Sa-Token
一个轻量级 Java 权限认证框...

lengleng/pig
基于Spring Boot 3.3...

...
```

---

## ✅️️ 示例详解

我们逐行解读代码：

```python
from DrissionPage import Chromium
```

↑ 首先，我们导入用于控制浏览器的类`Chromium`。

```python
tab = Chromium().latest_tab
```

↑ 接下来，们创建一个`Chromium`对象，用于连接浏览器，并用`latest_tab`获取一个可切换模式的标签页对象。

```python
tab.get('https://gitee.com/explore')
```

码到剪贴板" title="复制" class="clean-btn">

↑ 然后控制浏览器访问 gitee。

```python
tab.change_mode()
```

↑ `change_mode()`方法用于切换工作模式，从当前控制浏览器的模式切换到收发数据包模式。

切换的时候程序会在新模式重新访问 当前 url。

```python
items = tab('#hits-list').eles('.item')
```

↑ 切换后，我们可以用与控制浏览器一致的语法，获取页面元素，这获取页面中所有结果行素，它返回这些元素对象组成的列表。

```python
for item in items:
    print(item('.title').text)
    print(item('.desc').text)
    print()
```

↑ 最后，我们遍历这些元素，并逐个打印它们包含的文本。

<!-- https://www.drissionpage.cn/SessionPage/create_obj -->

# 🛩️ 创建页面对象

## ✅️️ `SessionPage`初始化参数

| 初始化参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `session_or_options` | `Session` `SessionOptions` | `None` | 传入`Session`对象时使用该对象收发数据包；传入`SessionOptions`对象时用该配置创建`Session`对象；为`None`则从 ini 文件读取，为`False`则不从 ini 文件读取，而用内置默认配置 |

---

## ✅️️ 直接创建

这种方式代码最简洁，程序会从配置文件中读取配置，自动生成页面对象。

```python
from DrissionPage import SessionPage

page = SessionPage()
```

`SessionPage`无需控制浏览器，无需做任何配置即可使用。

直接创建时，程序默认读取 ini 文件配置，如 ini 文件不存在，会使用内置配置。

默认 ini 和内置配置信息详见 “进阶使用->配置文件的使用” 章节。

---

## ✅️️ 通过配置信息创建

如果需要在使用前进行一些配置，可使用`SessionOptions`。它是专门用于设置`Session`对象初始状态的类，内置了常用的配置。详细使用方法见 “启动配置” 一节。

### 📌 使用方法

在`SessionPage`创建时，将已创建和设置好的`SessionOptions`对象以参数形式传递进去即可。

| 初始化参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `read_file` | `bool` | `True` | 是否从 ini 文件中读取配置信息 |
| `ini_path` | `str` | `None` | 文件路径，为`None`则读取默认 ini 文件 |

注意

`Session`对象创建后再修改这个配置是没有效果的。

```python
# 导入 SessionOptions
from DrissionPage import SessionPage, SessionOptions

# 创建配置对象，并设置代理信息
so = SessionOptions().set_proxies(http='127.0.0.1:1080')
# 用该配置创建页面对象
page = SessionPage(session_or_options=so)
```

Tips

您可以把配置保存到配置文件以后自动读取，详见 “启动配置” 章节。

---

### 📌 从指定 ini 文件创建

以上方法是使用默认 ini 文件中保存的配置信息创建对象，你可以保存一个 ini 文件到别的地方，并在创建对象时指定使用它。

```python
from DrissionPage import SessionPage, SessionOptions

# 创建配置对象时指定要读取的ini文件路径
so = SessionOptions(ini_path=r'./config1.ini')
# 使用该配置对象创建页面
page = SessionPage(session_or_options=so)
```

---

### 📌 不使用 ini 文件

可以用以下方法，指定不使用 ini 文件的配置，而把配置写在代码中。

```python
from DrissionPage import SessionPage, SessionOptions

so = SessionOptions(read_file=False)  # read_file设为False
so.set_retry(5)
page = SessionPage(so)
```

---

## ✅️️ 传递控制权

当需要使用多个页面对象共同操作一个页面时，可在页面对象创建时接收另一个页面间对象传递过来的`Session`对象，以达到多个页面对象同时使用一个`Session`对象的效果。

```python
from DrissionPage import SessionPage

# 创建一个页面
page1 = SessionPage()
# 获取页面对象内置的Session对象
session = page1.session
# 在第二个页面对象初始化时传递该对象
page2 = SessionPage(session_or_options=session)
```

<!-- https://www.drissionpage.cn/SessionPage/visit -->

# 🛩️ 访问网页

`SessionPage`基于 requests 进行网络连接，因此可使用 requests 内置的所有请求方式，包括`get()`、`post()`、`head()`、`options()`、`put()`、`patch()`、`delete()`。

不过本库目前只对`get()`和`post()`做了封装和优化，其余方式可通过调用页面对象内置的`Session`对象使用。

## ✅️️ `get()`

此方法用于以 GET 方式请求页面。

### 📌 访问在线网页

`get()`方法语法与 requests 的`get()`方法一致，在此基础上增加了连接失败重试功能。

与 requests 不一样的是，它不返回`Response`对象，而是从`SessionPae`对象的`html`等属性读取结果。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `url` | `str` | 必填 | 目标 url，可指向本地文件路径 |
| `show_errmsg` | `bool` | `False` | 连接出错时是否显示和抛出异常 |
| `retry` | `int` | `None` | 重试次数，为`None`时使用页面参数，默认`3` |
| `interval` | `float` | `None` | 重试间隔（秒），为`None`时使用页面参数，默认`2` |
| `timeout` | `float` | `None` | 加载超时时间（秒） |
| `params` | `dict` | `None` | url 请求参数 |
| `data` | `dict` `str` | `None` | 携带的数据 |
| `json` | `dict` `str` | `None` | 要发送的 JSON 数据，会自动设置 Content-Type 为`'application/json'` |
| `headers` | `dict` | `None` | 请求头 |
| `cookies` | `dict` `CookieJar` | `None` | cookies 信息 |
| `files` | `Any` | `None` | 要上传的文件，可以是一个字典，其中键是文件名，值是文件对象或文件路径 |
| `auth` | `Any` | `None` | 身份认证信息 |
| `allow_redirects` | `bool` | `True` | 是否允许重定向 |
| `proxies` | `dict` | `None` | 代理信息 |
| `hooks` | `Any` | `None` | 回调方法 |
| `stream` | `bool` | `None` | 是否使用流式传输 |
| `verify` | `bool` `str` | `None` | 是否验证 SSL 证书 |
| `cert` | `str` `Tuple[str, str]` | `None` | SSL 客户端证书文件的路径(.pem 格式)，或('cert', 'key')元组 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否连接成功 |

说明

`**kwargs`参数与 requests 中该参数使用方法一致，但有一个特点，如果该参数中设置了某一项（如`headers`），该项中的每个项会覆盖从配置中读取的同名项，而不会整个覆盖。
就是说，如果想继续使用配置中的`headers`信息，而只想修改其中一项，只需要传入该项的值即可。这样可以简化代码逻辑。

程序会根据要访问的网址自动在`headers`中加入`Host`和`Referer`项

程序会自动从返回内容中确定编码，一般情况无需手动设置

普通访问网页：

```python
from DrissionPage import SessionPage

page = SessionPage()
page.get('http://g1879.gitee.io/drissionpage')
```

使用连接参数访问网页：

```python
from DrissionPage import SessionPage

page = SessionPage()

url = 'https://www.baidu.com'
headers = {'referer': 'gitee.com'}
cookies = {'name': 'value'}
proxies = {'http': '127.0.0.1:1080', 'https': '127.0.0.1:1080'}
page.get(url, headers=headers, cookies=cookies, proxies=proxies)
```

---

### 📌 读取本地文件

`get()`的`url`参数可指向本地文件，实现本地 html 解析。

```python
from DrissionPage import SessionPage

page = SessionPage()
page.get(r'D:\demo.html')
```

---

## ✅️️ `post()`

此方法是用 POST 方式请求页面。用法与`get()`一致。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `url` | `str` | 必填 | 目标 url，可指向本地文件路径 |
| `show_errmsg` | `bool` | `False` | 连接出错时是否显示和抛出异常 |
| `retry` | `int` | `None` | 重试次数，为`None`时使用页面参数，默认`3` |
| `interval` | `float` | `None` | 重试间隔（秒），为`None`时使用页面参数，默认`2` |
| `timeout` | `float` | `None` | 加载超时时间（秒） |
| `params` | `dict` | `None` | url 请求参数 |
| `data` | `dict` `str` | `None` | 携带的数据 |
| `json` | `dict` `str` | `None` | 要发送的 JSON 数据，会自动设置 Content-Type 为`'application/json'` |
| `headers` | `dict` | `None` | 请求头 |
| `cookies` | `dict` `CookieJar` | `None` | cookies 信息 |
| `files` | `Any` | `None` | 要上传的文件，可以是一个字典，其中键是文件名，值是文件对象或文件路径 |
| `auth` | `Any` | `None` | 身份认证信息 |
| `allow_redirects` | `bool` | `True` | 是否允许重定向 |
| `proxies` | `dict` | `None` | 代理信息 |
| `hooks` | `Any` | `None` | 回调方法 |
| `stream` | `bool` | `None` | 是否使用流式传输 |
| `verify` | `bool` `str` | `None` | 是否验证 SSL 证书 |
| `cert` | `str` `Tuple[str, str]` | `None` | SSL 客户端证书文件的路径(.pem 格式)，或('cert', 'key')元组 |

| 返回类型 | 说明 |
| --- | --- |
| `bool` | 是否连接成功 |

```python
from DrissionPage import SessionPage

page = SessionPage()
data = {'username': '****', 'pwd': '****'}

page.post('http://example.com', data=data)
# 或
page.post('http://example.com', json=data)
```

`data`参数和`json`参数都可接收`str`和`dict`格式数据，即有以下 4 种传递数据的方式：

```python
# 向 data 参数传入字符串
page.post(url, data='abc=123')

# 向 data 参数传入字典
page.post(url, data={'abc': '123'})

# 向 json 参数传入字符串
page.post(url, json='abc=123')

# 向 json 参数传入字典
page.post(url, json={'abc': '123'})
```

具体使用哪种，按服务器要求而定。

---

## ✅️️ 其它请求方式

本库只针对常用的 GET 和 POST 方式作了优化，但也可以通过提取页面对象内的`Session`对象以原生 requests 代码方式执行其它请求方式。

```python
from DrissionPage import SessionPage

page = SessionPage()
# 获取内置的 Session 对象
session = page.session
# 以 head 方式发送请求
response = session.head('https://www.baidu.com')
print(response.headers)
```

**输出：**

```shell
{'Accept-Ranges': 'bytes', 'Cache-Control': 'private, no-cache, no-store, proxy-revalidate, no-transform', 'Connection': 'keep-alive', 'Content-Length': '277', 'Content-Type': 'text/html', 'Date': 'Tue, 04 Jan 2022 06:49:18 GMT', 'Etag': '"575e1f72-115"', 'Last-Modified': 'Mon, 13 Jun 2016 02:50:26 GMT', 'Pragma': 'no-cache', 'Server': 'bfe/1.0.8.18'}
```

<!-- https://www.drissionpage.cn/SessionPage/get_page_info -->

# 🛩️ 获取页面信息

成功访问网页后，可使用`SessionPage`对象自身属性和方法获取页面信息。

```python
from DrissionPage import SessionPage

page = SessionPage()
page.get('http://www.baidu.com')
# 获取页面标题
print(page.title)
# 获取页面html
print(page.html)
```

**输出：**

```shell
百度一下，你就知道
<!DOCTYPE html>
<!--STATUS OK--><html> <head><meta http-equi...
```

---

## ✅️️ 页面信息

### 📌 `url`

此属性返回当前访问的 url。

**类型：**`str`

---

### 📌 `url_available`

此属性以布尔值返回当前链接是否可用。

**类型：**`bool`

---

### 📌 `title`

此属性返回当前页面`title`文本。

**类型：**`str`

---

### 📌 `raw_data`

此属性返回访问到的元素数据，即`Response`对象的`content`属性。

**类型：**`bytes`

---

### 📌 `html`

此属性返回当前页面 html 文本。

**类型：**`str`

---

### 📌 `json`

此属性把返回内容解析成 json。
比如请求接口时，若返回内容是 json 格式，用`html`属性获取的话会得到一个字符串，用此属性获取可将其解析成`dict`。
支持访问 `*.json` 文件，也支持 API 返回的json字符串。

**类型：**`dict`

---

### 📌 `user_agent`

此属性返回当前页面 user\_agent 信息。

**类型：**`str`

---

## ✅️️ 运行参数信息

### 📌 `timeout`

此属性返回网络请求超时时间，默认为 10 秒。

**类型：**`int`、`float`

---

### 📌 `retry_times`

此属性为网络连接失败时的重试次数，默认为`3`。

**类型：**`int`

---

### 📌 `retry_interval`

此属性为网络连接失败时的重试等待间隔秒数，默认为`2`。

**类型：**`int`、`float`

---

### 📌 `encoding`

此属性返回用户主动设置的编码格式。

---

## ✅️️ cookies 信息

### 📌 `cookies()`

此方法返回 cookies 信息。

**类型：**`dict`、`list`

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `all_domains` | `bool` | `False` | 是否返回所有 cookies，为`False`只返回当前 url 的 |
| `all_info` | `bool` | `False` | 返回的 cookies 是否包含所有信息，`False`时只包含`name`、`value`、`domain`信息 |

| 返回类型 | 说明 |
| --- | --- |
| `CookiesList` | cookies 组成的列表 |

`cookies()`方法返回的列表可转换为其它指定格式。

- `cookies().as_str()`：`'name1=value1; name2=value2'`格式的字符串
- `cookies().as_dict()`：`{name1: value1, name2: value2}`格式的字典
- `cookies().as_json()`：json 格式的字符串

说明

`as_str()`和`as_dict()`都只会保留`'name'`和`'value'`字段。

**示例：**

```python
from DrissionPage import SessionPage

page = SessionPage()
page.get('http://www.baidu.com')
page.get('http://gitee.com')

for i in page.cookies(all_domains=True):
    print(i)
```

**输出：**

```text
{'name': 'BDORZ', 'value': '27875', 'domain': '.baidu.com'}
{'name': 'BEC', 'value': '1f1759dfh65j65j5j4feb0357', 'domain': 'gitee.com'}
```

---

## ✅️️ 内嵌对象

### 📌 `session`

此属性返回当前页面对象使用的`Session`对象。

**类型：**`Session`

---

### 📌 `response`

此属性为请求网页后生成的`Response`对象，本库没实现的功能可直接获取此属性调用 requests 库的原生功能。

**类型：**`Response`

```python
# 打印连接状态
r = page.response
print(r.status_code)
```

<!-- https://www.drissionpage.cn/SessionPage/get_ele -->

# 🛩️ 查找元素

## ✅️️ 页面或元素内查找

页面对象和元素对象都拥有`ele()`和`eles()`方法，用于获取其内部指定子元素。

### 📌 `ele()`

用于查找其内部第一个条件匹配的元素。

页面对象和元素对象的`ele()`方法参数名称稍有不同，但用法一样。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` | 必填 | 元素的定位信息。可以是查询字符串，或 loc 元组 |
| `index` | `int` | `1` | 获取第几个匹配的元素，从`1`开始，可输入负数表示从后面开始数 |
| `timeout` | `float` | `None` | 此参数在这里没有作用 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionElement` | 找到的第一个元素对象 |
| `NoneElement` | 未找到符合条件的元素时返回 |

---

### 📌 `eles()`

此方法与`ele()`相似，但返回的是匹配到的所有元素组成的列表。

页面对象和元素对象都可调用这个方法。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` | 必填 | 元素的定位信息，可以是查询字符串，或 loc 元组 |
| `timeout` | `float` | `None` | 此参数在这里没有作用 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionElementsList` | 元素对象组成的列表 |

---

## ✅️️ 相对定位

以下方法可以以某元素为基准，在 DOM 中按照条件获取其直接子节点、同级节点、祖先元素、文档前后节点。

这里说的是 “节点”，不是 “元素”。因为相对定位可以获取除元素外的其它节点，包括文本、注释节点。

### 📌 获取父级元素

🔸 `parent()`

此方法获取当前元素某一级父元素，可指定筛选条件 或层数。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `level_or_loc` | `int` `str` `Tuple[str, str]` | `1` | 第几级父元素，从`1`开始，或用定位符在祖先元素中进行筛选 |
| `index` | `int` | `1` | 当`level_or_loc`传入定位符，使用此参数选择第几个结果，从当前元素往上级数；当`level_or_loc`传入数字时，此参数无效 |
| `timeout` | `float` | `0` | 查找超时时间（秒） |

| 返回类型 | 说明 |
| --- | --- |
| `SessionElement` | 元素对象 |
| `NoneElement` | 未获取到结果时 |

---

### 📌 获取直接子节点

🔸 `child()`

此方法返回当前元素的一个直接子节点，可指定筛选条件和第几个。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` `int` | `''` | 用于筛选节点的查询语法，为`int`类型时`index`参数无效 |
| `index` | `int` | `1` | 查询结果中的第几个，从`1`开始，可输入负数表示倒数 |
| `timeout` | `float` | `None` | 无实际作用 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 获取非元素节点时返回字符串 |
| `SessionElement` | 元素对象 |
| `NoneElement` | 未获取到结果时 |

---

🔸 `children()`

此方法返回当前元素全部符合条件的直接子节点组成的列表，可用查询语法筛选。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` | `''` | 用于筛选节点的查询语法 |
| `timeout` | `float` | `None` | 无实际作用 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionElementsList` | 结果元素对象组成的列表 |

---

### 📌 获取后面的同级节点

🔸 `next()`

此方法返回当前元素后面的某一个同级节点，可指定筛选条件和第几个。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` `int` | `''` | 用于筛选节点的查询语法，为`int`类型时`index`参数无效 |
| `index` | `int` | `1` | 查询结果中的第几个，从`1`开始，可输入负数表示倒数 |
| `timeout` | `float` | `None` | 无实际作用 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 获取非元素节点时返回字符串 |
| `SessionElement` | 元素对象 |
| `NoneElement` | 未获取到结果时 |

---

🔸 `nexts()`

此方法返回当前元素后面全部符合条件的同级节点组成的列表，可用查询语法筛选。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` | `''` | 用于筛选节点的查询语法 |
| `timeout` | `float` | `None` | 无实际作用 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionElementsList` | 结果元素对象组成的列表 |

---

### 📌 获取前面的同级节点

🔸 `prev()`

此方法返回当前元素前面的某一个同级节点，可指定筛选条件和第几个。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` `int` | `''` | 用于筛选节点的查询语法，为`int`类型时`index`参数无效 |
| `index` | `int` | `1` | 查询结果中的第几个，从`1`开始，可输入负数表示倒数 |
| `timeout` | `float` | `None` | 无实际作用 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 获取非元素节点时返回字符串 |
| `SessionElement` | 元素对象 |
| `NoneElement` | 未获取到结果时 |

---

🔸 `prevs()`

此方法返回当前元素前面全部符合条件的同级节点组成的列表，可用查询语法筛选。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` | `''` | 用于筛选节点的查询语法 |
| `timeout` | `float` | `None` | 无实际作用 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionElementsList` | 结果元素对象组成的列表 |

---

### 📌 在后面文档中查找节点

🔸 `after()`

此方法返回当前元素后面的某一个节点，可指定筛选条件和第几个。查找范围不限同级节点，而是整个 DOM 文档。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` `int` | `''` | 用于筛选节点的查询语法，为`int`类型时`index`参数无效 |
| `index` | `int` | `1` | 查询结果中的第几个，从`1`开始，可输入负数表示倒数 |
| `timeout` | `float` | `None` | 无实际作用 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 获取非元素节点时返回字符串 |
| `SessionElement` | 元素对象 |
| `NoneElement` | 未获取到结果时 |

---

🔸 `afters()`

此方法返回当前元素后面符合条件的全部节点组成的列表，可用查询语法筛选。查找范围不限同级节点，而是整个 DOM 文档。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` | `''` | 用于筛选节点的查询语法 |
| `timeout` | `float` | `None` | 无实际作用 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionElementsList` | 结果元素对象组成的列表 |

---

### 📌 在前面文档中查找节点

🔸 `before()`

此方法返回当前元素前面的某一个符合条件的节点，可指定筛选条件和第几个。查找范围不限同级节点，而是整个 DOM 文档。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` `int` | `''` | 用于筛选节点的查询语法，为`int`类型时`index`参数无效 |
| `index` | `int` | `1` | 查询结果 中的第几个，从`1`开始，可输入负数表示倒数 |
| `timeout` | `float` | `None` | 无实际作用 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 获取非元素节点时返回字符串 |
| `SessionElement` | 元素对象 |
| `NoneElement` | 未获取到结果时 |

---

🔸 `befores()`

此方法返回当前元素前面全部符合条件的节点组成的列表，可用查询语法筛选。查找范围不限同级节点，而是整个 DOM 文档。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locator` | `str` `Tuple[str, str]` | `''` | 用于筛选节点的查询语法 |
| `timeout` | `float` | `None` | 无实际作用 |
| `ele_only` | `bool` | `True` | 是否只查找元素，为`False`时把文本、 注释节点也纳入查找范围 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionElementsList` | 结果元素对象组成的列表 |

---

## ✅️️ 同时匹配多个定位符

所有页面或元素对象都有`find()`方法，可接收多个定位符，同时查找多个（批）不同定位符的元素。

以`dict`方法返回每个定位符结果。

说明

当`first_ele`为`True`时，如果一个定位符没有被执行过查找，它返回的结果为`None`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `locators` | `List[str]` `Tuple[str]` `str` `tuple` | 必填 | 定位符组成的列表 |
| `any_one` | `bool` | `True` | 是否任何一个定位符找到结果即返回 |
| `first_ele` | `bool` | `True` | 每个定位符获取第一个元素还是所有元素 |
| `timeout` | `float` | `None` | 超时时间（秒），为`None`使用该对象默认设置 |

说明

以下所说的 “定位符”，是`str`或`tuple`类型的。
“元素对象”，是`SessionElement`类型的，没有找到时是`NoneElement`类型的。
“元素对象组成的列表” 是`SessionElementsList`类型的。
`any_one`参数为`True`时，以`tuple`方式返回找到 目标的定位符和结果，为`False`时以`dict`方法返回每个定位符结果。

| 返回类型 | `any_one`参数取值 | 说明 |
| --- | --- | --- |
| `tuple(定位符, 元素对象)` | `True` | `first_ele`为`True`时，返回第一个有结果的定位符找到的第一个元素对象 |
| `tuple(定位符, 元素对象组成的列表)` | `True` | `first_ele`为`False`时，返回第一个有结果的定位符找到的所有元素对象 |
| `tuple(None, None)` | `True` | 所有定位符都没有找到元素，返回`(None, None)` |
| `dict{定位符: 元素对象}` | `False` | `first_ele`为`True`时，每个定位符返回第一个元素，找不到时为`NoneElement` |
| `dict{定位符: 元素对象组成的列表}` | `False` | `first_ele`为`False`时，每个定位符返回所有结果元素组成的列表 |

<!-- https://www.drissionpage.cn/SessionPage/get_ele_info -->

# 🛩️ 获取元素信息

`SessionPage`对象获取的元素是`SessionElement`，本节介绍其属性。

假设`ele`为以下`div`元素的对象，本节示例均使用该元素：

```html
<div id="div1" class="divs">Hello World!
    <p>行元素</p>
    <!--这是注释-->
</div>
```

## ✅️️ `html`

此属性返回元素的`outerHTML`文本。

**返回类型：**`str`

```python
print(ele.html)
```

**输出：**

```shell
<div id="div1" class="divs">Hello World!
    <p>行元素</p>
    <!--这是注释-->
</div>
```

---

## ✅️️ `inner_html`

此属性返回元素的`innerHTML`文本。

**返回类型：**`str`

```python
print(ele.inner_html)
```

**输出：**

```shell
Hello World!
    <p>行元素</p>
    <!--这是注释-->
```

---

## ✅️️ `tag`

此属性返回元素的标签名。

**返回类型：**`str`

```python
print(ele.tag)
```

**输出：**

```shell
div
```

---

## ✅️️ `text`

此属性返回元素内所有文本组合成的字符串。
该字符串已格式化，即已转码，已去除多余换行符，符合人读取习惯，便于直接使用。

**返回类型：**`str`

```python
print(ele.text)
```

**输出：**

```shell
Hello World!
行元素
```

---

## ✅️️ `raw_text`

此属性返回元素内原始文本。

**返回类型：**`str`

```python
print(ele.raw_text)
```

输出（注意保留了元素间的空格和换行）：

```shell
Hello World!
    行元素
　
　
```

---

## ✅️️ `texts()`

此方法返回元素内所有**直接**子节点的文本，包括元素和文本节点。 它有一个参数`text_node_only`，为`True`时则只获取只返回不被包裹的文本节点。这个方法适用于获取文本节点和元素节点混排的情况。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `text_node_only` | `bool` | `False` | 是否只返回文本节点 |

| 返回类型 | 说明 |
| --- | --- |
| `List[str]` | 文本列表 |

**示例：**

```python
print(e.texts())
print(e.texts(text_node_only=True))
```

**输出：**

```shell
['Hello World!', '行元素']
['Hello World!']
```

---

## ✅️️ `comments`

此属性以列表形式返回元素内的注释。

**返回类型：**`List[str]`

```python
print(ele.comments)
```

**输出：**

```shell
[<!--这是注释-->]
```

---

## ✅️️ `attrs`

此属性以字典形式返回元素所有属性及值。

**返回类型：**`dict`

```python
print(ele.attrs)
```

**输出：**

```shell
{'id': 'div1', 'class': 'divs'}
```

贴板" title="复制" class="clean-btn">

---

## ✅️️ `attr()`

此方法返回元素某个 attribute 属性值。它接收一个字符串参数，返回该属性值文本，无该属性时返回`None`。
此属性返回的`src`、`href`属性为已补充完整的路径。`text`属性为已格式化文本。
如果要获取未补充完整路径的`src`或`href`属性，可以用`attrs['src']`。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 属性名称 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 属性值文本 |
| `None` | 没有该属性返回`None` |

**示例：**

```python
print(ele.attr('id'))
```

**输出：**

```shell
div1
```

---

## ✅️️ `link`

此方法返回元素的 href 属性或 src 属性，没有这两个属性则返回`None`。

**返回类型：**`str`

```html
<a href='http://www.baidu.com'>百度</a>
```

假设`a_ele`为以上元素的对象：

```python
print(a_ele.link)
```

**输出：**

```shell
http://www.baidu.com
```

---

### 📌 `child_count`

此属性返回元素内第一级子元素个数。

**类型：**`int`

---

## ✅️️ `page`

此属性返回元素所在的页面对象。由 html 文本直接生成的`SessionElement`的`page`属性为`None`。

**返回类型：**`SessionPage`、`WebPage`

```python
page = ele.page
```

---

## ✅️️ `xpath`

此属性返回当前元素在页面中 xpath 的绝对路径。

**返回类型：**`str`

```python
print(ele.xpath)
```

**输出：**

```shell
/html/body/div
```

---

## ✅️️ `css_path`

此属性返回当前元素在页面中 css selector 的绝对路径。

**返回类型：**`str`

```python
print(ele.css_path)
```

**输出：**

```shell
:nth-child(1)>:nth-child(1)>:nth-child(1)
```

---

## ✅️️ 元素列表中批量获取信息

`eles()`等返回的元素列表，自带`get`属性，可用于获取指定信息。

### 📌 示例

```python
from DrissionPage import SessionPage

page = SessionPage()
page.get('https://www.baidu.com')
eles = page('#s-top-left').eles('t:a')
print(eles.get.texts())  # 获取所有元素的文本
```

**输出：**

```shell
['新闻', 'hao123', '地图', '贴吧', '视频', '图片', '网盘', '文库', '更多', '翻译', '学术', '百科', '知道', '健康', '营销推广', '直播', '音乐', '橙 篇', '查看全部百度产品 >']
```

### 📌 `get.attrs()`

此方法用于返回所有元素指定的 attribute 属性组成的列表。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 属性名称 |

| 返回类型 | 说明 |
| --- | --- |
| `List[str]` | 属性文本组成的列表 |

---

### 📌 `get.links()`

此方法用于返回所有元素的`link`属性组成的列表。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `List[str]` | 链接文本组成的列表 |

---

### 📌 `get.texts()`

此方法用于返回所有元素的`text`属性组成的列表。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `List[str]` | 元素文本组成的列表 |

---

## ✅️️ 实际示例

以下示例可直接运行查看结果：

```python
from DrissionPage import SessionPage

page = SessionPage()
page.get('https://gitee.com/explore')

# 获取推荐目录下所有 a 元素
li_eles = page('tag:ul@text():全部推荐项目').eles('t:a')

# 遍历列表
for i in li_eles:
    # 获取并打印标签名、文本、href 属性
    print(i.tag, i.text, i.attribute('href'))
```

**输出：**

```shell
a 全部推荐项目 https://gitee.com/explore/all
a 前沿技术 https://gitee.com/explore/new-tech
a 智能硬件 https://gitee.com/explore/hardware
a IOT/物联网/边缘计算 https://gitee.com/explore/iot
a 车载应用 https://gitee.com/explore/vehicle
以下省略……
```

<!-- https://www.drissionpage.cn/SessionPage/settings -->

# 🛩️ 页面设置

本节介绍`SessionPage`运行参数设置。

这些设置是全局参数，设置后每次请求都会使用它们。

**示例：**

```python
from DrissionPage import SessionPage

page = SessionPage()
page.set.cookies([{'name': 'a', 'value': '1'}, {'name': 'b', 'value': '2'}])
```

## ✅️️ `set.retry_times()`

此方法用于设置连接失败时重连次数。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `times` | `int` | 必填 | 次数 |

**返回：**`None`

## ✅️️ `set.retry_interval()`

此方法用于设置连接失败时重连间隔。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `interval` | `float` | 必填 | 秒数 |

**返回：**`None`

## ✅️️ `set.timeout()`

此方法用于设置连接超时时间（秒）。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `second` | `float` | 必填 | 秒数 |

**返回：**`None`

**示例：**

```python
page.set.timeout(20)
```

---

## ✅️️ `set.encoding()`

此方法用于设置网页编码。

默认情况下，程序会自动从 headers、页面上获取编码，但总有些奇葩网页的编码不准确。这时候可以主动设置编码。

可以针对已获取的`Rsponse`对象设置，或作为整体设置对之后的连接都有效。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `encoding` | `str` | 必填 | 编码名称，如果要取消之前的设置，传入`None` |
| `set_all` | `bool` | `True` | 是否设置对象参数，为`False`则只设置当前`Response`对象 |

**返回：**`None`

---

## ✅️️ `set.cookies()`

此方法用于设置一个或多个 cookie。

设置一个 cookie 支持的格式：

- `Cookie`：单个`Cookie`对象
- `str`：`'name=value; domain=****; ...'`或`'name=****; value=****; domain=****; ...'`格式，只支持用`';'`分隔
- `dict`：`{'name': '****', 'value': '****', 'domain': '****', ...}`或`{name: value, 'domain': '****', ...}`格式

设置多个 cookie 支持的格式：

- `list`或`tuple`：上面几种形式的单个 cookie 放到列表中传入即可
- `dict`：`{name1: value1, name2: value2, ..., 'domain': '****', ...}`格式
- `str`：`'name1=value1; name2=value2; ... domain=****; ...'`格式，多个 cookie 之间只能用`';'`分隔
- `CookieJar`：单个`CookieJar`对象

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `cookies` | `Cookie` `CookieJar` `list` `tuple` `str` `dict` | 必填 | cookies 信息 |

**返回：**`None`

---

## ✅️️ `set.cookies.clear()`

此方法用于清除所有 cookie。

**参数：** 无

**返回：**`None`

---

## ✅️️ `set.cookies.remove()`

此方法用于删除一个 cookie。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | cookie 的 name 字段 |

**返回：**`None`

---

## ✅️️ `set.headers()`

此方法用于设置 headers，会取代已有 headers。

headers 可以是`dict`格式的，也可以是文本格式。

文本格式不同字段用`\n`分隔，字段 key 和 value 用`': '`分隔，即从浏览器直接复制的格式。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `headers` | `dict` `str` | 必填 | headers 信息 |

**返回：**`None`

---

## ✅️️ `set.header()`

此方法用于设置 headers 中一个项。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 设置名称 |
| `value` | `str` | 必填 | 设置值 |

**返回：**`None`

---

## ✅️️ `set.user_agent()`

此方法用于设置 user\_agent 。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `ua` | `str` | 必填 | user\_agent 信息 |

**返回：**`None`

---

## ✅️️ `set.proxies()`

此方法用于设置代理 ip。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `http` | `str` | `None` | http 代理地址 |
| `https` | `str` | `None` | https 代理地址 |

**返回：**`None`

---

## ✅️️ `set.auth()`

此方法用于设置认证元组或对象。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `auth` | `Tuple[str, str]` `HTTPBasicAuth` | 必填 | 认证元组或对象 |

**返回：**`None`

---

## ✅️️ `set.hooks()`

此方法用于设置回调方法。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `hooks` | `dict` | 必填 | 回调方法 |

**返回：**`None`

---

## ✅️️ `set.params()`

此方法用于设置查询参数字典。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `params` | `dict` | 必填 | 查询参数字典 |

**返回：**`None`

---

## ✅️️ `set.verify()`

此方法用于设置是否验证SSL证书。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | 必填 | `bool`表示开或关 |

**返回：**`None`

---

## ✅️️ `set.cert()`

此方法用于设置SSL客户端证书。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `cert` | `str` `Tuple[str, str]` | 必填 | SSL客户端证书文件的路径(.pem格式)，或(‘cert’, ‘key’)元组 |

**返回：**`None`

---

## ✅️️ `set.stream()`

此方法用于设置是否使用流式响应内容。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | 必填 | `bool`表示开或关 |

**返回：**`None`

---

## ✅️️ `set.trust_env()`

此方法用于设置是否信任环境。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | 必填 | `bool`表示开或关 |

**返回：**`None`

---

## ✅️️ `set.max_redirects()`

此方法用于设置连接最大重定向次数。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| ``times | `int` | 必填 | 最大重定向次数 |

**返回：**`None`

---

## ✅️️ `set.add_adapter()`

此方法用于添加适配器。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `url` | `str` | 必填 | 适配器对应url |
| `adapter` | `HTTPAdapter` | 必填 | 适配器对象 |

**返回：**`None`

---

## ✅️️ `close()`

此方法用于关闭连接。

**参数：** 无

**返回：**`None`

---

<!-- https://www.drissionpage.cn/SessionPage/session_opt -->

# 🛩️ 启动配置

我们用`SessionOptions`对象管理`SessionPage`对象初始配置。

注意

`SessionOptions`仅用于管理启动配置，程序启动后再修改无效。

## ✅️️ 创建对象

### 📌 导入

```python
from DrissionPage import SessionOptions
```

---

### 📌 初始化参数

`SessionOptions`对象用于管理`Session`对象的初始化配置。可从配置文件中读取配置来进行初始化。

| 初始化参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `read_file` | `bool` | `True` | 是否从 ini 文件中读取配置信息，为`False`则用默认配置创建 |
| `ini_path` | `Path` `str` | `None` | 指定 ini 文件路径，为`None`则读取内置 ini 文件 |

创建配置对象：

```python
from DrissionPage import SessionOptions

so = SessionOptions()
```

默认情况下，`SessionOptions`对象会从 ini 文件中读取配置信息，当指定`read_file`参数为`False`时，则以默认配置创建。

提醒

对象创建时已带有默认 headers，如要清除，可调用`clear_headers()`方法。

---

## ✅️️ 使用方法

创建配置对象后，可调整配置内容，然后在页面对象创建时以参数形式把配置对象传递进去。

```python
from DrissionPage import SessionPage, SessionOptions

# 创建配置对象（默认从 ini 文件中读取配置）
so = SessionOptions()
# 设置代理
so.set_proxies('http://localhost:1080')
# 设置 cookies
cookies = ['key1=val1; domain=****', 'key2=val2; domain=****']
so.set_cookies(cookies)

# 以该配置创建页面对象
page = SessionPage(session_or_options=so)
```

---

## ✅️️ 用于设置的方法

### 📌 `set_headers()`

该方法用于设置整个 headers 参数，传入值会覆盖原来的 headers。

headers 可以是`dict`格式的，也可以是文本格式。

文本格式不同字段用`\n`分隔，字段 key 和 value 用`': '`分隔，即从浏览器直接复制的格式。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `headers` | `dict` `str` | 必填 | headers 信息 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionOptions` | 配置对象本身 |

**示例：**

```python
so.set_headers = {'user-agent': 'Mozilla/5.0 (Macint...', 'connection': 'keep-alive' ...}
```

---

### 📌 `set_a_header()`

该方法用于设置`headers`中的一个项。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 设置名称 |
| `value` | `str` | 必填 | 设置值 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionOptions` | 配置对象本身 |

**示例：**

```python
so.set_a_header('accept', 'text/html')
so.set_a_header('Accept-Charset', 'GB2312')
```

**输出：**

```text
{'accept': 'text/html', 'accept-charset': 'GB2312'}
```

---

### 📌 `remove_a_header()`

此方法用于从`headers`中移除一个设置项。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `name` | `str` | 必填 | 要删除的设置 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionOptions` | 配置对象本身 |

**示例：**

```python
so.remove_a_header('accept')
```

---

### 📌 `clear_headers()`

此方法用于清空已设置的`headers`参数。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `SessionOptions` | 配置对象自身 |

---

### 📌 `set_cookies()`

此方法用于设置一个或多个 cookie，每次设置会覆盖之前所有 cookies 信息。

详细用法见实用教程相关章节。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `cookies` | `Cookie` `CookieJar` `list` `tuple` `str` `dict` | 必填 | cookies |

| 返回类型 | 说明 |
| --- | --- |
| `SessionOptions` | 配置对象本身 |

**示例：**

```python
cookies = ['key1=val1; domain=****', 'key2=val2; domain=****']
so.set_cookies(cookies)
```

---

### 📌 `set_timeout()`

此方法用于设置连接超时属性。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `second` | `float` | 必填 | 连接等待秒数 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionOptions` | 配置对象本身 |

---

### 📌 `set_retry()`

此方法用于设置页面连接超时时的重试次数和间隔。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `times` | `int` | `None` | 连接失败重试次数 |
| `interval` | `float` | `None` | 连接失败重试间隔（秒） |

| 返回类型 | 说明 |
| --- | --- |
| `SessionOptions` | 配置对象本身 |

---

### 📌 `retry_times`

该属性返回连接失败时的重试次数。

**类型：**`int`

---

### 📌 `retry_interval`

该属性返回连接失败时的重试间隔（秒）。

**类型：**`float`

---

### 📌 `set_proxies()`

此方法用于设置代理信息。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `http` | `str` | `None` | http 代理地址 |
| `https` | `str` | `None` | https 代理地址 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionOptions` | 配置对象本身 |

**示例：**

```python
so.set_proxies('http://127.0.0.1:1080')
```

---

### 📌 `set_download_path()`

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `path` | `str` `Path` | 必填 | 默认下载保存路径 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionOptions` | 配置对象本身 |

---

### 📌 `set_auth()`

此方法用于设置认证元组信息。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `auth` | `tuple` `HTTPBasicAuth` | 必填 | 认证元组或对象 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionOptions` | 配置对象本身 |

---

### 📌 `set_hooks()`

此方法用于设置回调方法。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `hooks` | `dict` | 必填 | 回调方法 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionOptions` | 配置对象本身 |

---

### 📌 `set_params()`

此方法用于设置查询参数。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `params` | `dict` | 必填 | 查询参数字典 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionOptions` | 配置对象本身 |

---

### 📌 `set_cert()`

此方法用于设置 SSL 客户端证书文件的路径（.pem格式），或 ('cert', 'key') 元组。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `cert` | `str` `tuple` | 必填 | 证书路径或元组 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionOptions` | 配置对象本身 |

---

### 📌 `set_verify()`

此方法用于设置是否验证SSL证书。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | 必填 | `bool`表示开或关 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionOptions` | 配置对象本身 |

---

### 📌 `add_adapter()`

此方法用于添加适配器。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `url` | `str` | 必填 | 适配器对应 url |
| `adapter` | `HTTPAdapter` | 必填 | 适配器对象 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionOptions` | 配置对象本身 |

---

### 📌 `set_stream()`

此方法用于设置是否使用流式响应内容。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | 必填 | `bool`表示开或关 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionOptions` | 配置对象本身 |

---

### 📌 `set_trust_env()`

此方法用于设置是否信任环境。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `on_off` | `bool` | 必填 | `bool`表示开或关 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionOptions` | 配置对象本身 |

---

### 📌 `set_max_redirects()`

此方法用于设置最大重定向次数。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `times` | `int` | 必填 | 最大重定向次数 |

| 返回类型 | 说明 |
| --- | --- |
| `SessionOptions` | 配置对象本身 |

---

## ✅️️ 保存设置到文件

您可以把不同的配置保存到各自的 ini 文件，以便适应不同的场景。

注意

`hooks`和`adapters`配置是不会保存到文件中的。

### 📌 `save()`

此方法用于保存配置项到一个 ini 文件。

| 参数名称 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `path` | `str` `Path` | `None` | ini 文件的路径， 传入`None`保存到当前读取的配置文件 |

| 返回类型 | 说明 |
| --- | --- |
| `str` | 保存的 ini 文件绝对路径 |

**示例：**

```python
# 保存当前读取的ini文件
so.save()

# 把当前配置保存到指定的路径
so.save(path=r'D:\tmp\settings.ini')
```

---

### 📌 `save_to_default()`

此方法用于保存配置项到固定的默认 ini 文件。默认 ini 文件是指随 DrissionPage 内置的那个。

**参数：** 无

| 返回类型 | 说明 |
| --- | --- |
| `str` | 保存的 ini 文件绝对路径 |

**示例：**

```python
so.save_to_default()
```

---

## ✅️️ `SessionOptions`属性

### 📌 `headers`

该属性返回 headers 设置信息。

**类型：**`dict`

---

### 📌 `cookies`

此属性以`list`方式返回 cookies 设置信息。

**类型：**`list`

---

### 📌 `proxies`

此属性返回代理信息。

**类型：**`dict`
**格式：**`{'http': 'http://**.**.**.**:****', 'https': 'http://**.**.**.**:****'}`

---

### 📌 `auth`

此属性返回认证设置。

**类型：**`tuple`、`HTTPBasicAuth`

---

### 📌 `hooks`

此属性返回回调方法设置。

**类型：**`dict`

---

### 📌 `params`

此属性返回查询参数设置。

**类型：**`dict`

---

### 📌 `verify`

此属性返回是否验证 SSL 证书设置。

**类型：**`bool`

---

### 📌 `cert`

此属性返回 SSL 证书设置。

**类型：**`str`、`tuple`

---

### 📌 `adapters`

此属性返回适配器设置。

**类型：**`List[HTTPAdapter]`

---

### 📌 `stream`

此属性返回是否使用流式响应设置。

**类型：**`bool`

---

### 📌 `trust_env`

此属性返回是否信任环境设置。

**类型：**`bool`

---

### 📌 `max_redirects`

此属性返回`max_redirects`设置。

**类型：**`int`

---

### 📌 `timeout`

此属性返回连接超时设置。

**类型：**`int`、`float`

---

### 📌 `download_path`

此属性返回默认下载路径设置。

**类型：**`str`

<!-- https://www.drissionpage.cn/tutorials/xingqiu -->

# 🌏️ 知识星球

## 欢迎加入作者的知识星球

这里是一个关于 DrissionPage 实战案例、问题记录、解决问题、共同讨论的地方。

在这里，你可以：

- 找到 dp 常见的问题的解决方案
- 学到更多使用技巧和案例
- 向作者提问，获得官方技术支持
- 查看作者的开发笔记
- 与志同道合的其他人一起讨论技术，共同成长

还欢迎提出好的点子和改进意见，把 dp 打造得越来越 好。

![](/assets/images/zsxq-d2326c68adc888e01dda6b8a75721ec7.jpg)

<!-- https://www.drissionpage.cn/tutorials/video -->

# 🎞️ 视频教程

- Bilibili：<https://space.bilibili.com/20526000>
- 小红书：<https://www.xiaohongshu.com/user/profile/63293b09000000002303e82e>
- 抖音号：52635622816

![](/assets/images/video-318e4be75d5fe6df2af02901a317f02d.png)

<!-- https://www.drissionpage.cn/tutorials/gongzhonghao -->

# 🗨️ 公众号

## 欢迎关注公众号

![](/assets/images/gzh-2ebd3a4f84055229e0db2cfbaf02558f.jpg)

<!-- https://www.drissionpage.cn/tutorials/offline_doc -->

# 📚 离线文档

DrissionPage 提供了离线文档，用户可以在没有网络的情况下使用，也可以将文档投喂给 AI。

## ✅️️ DrissionPage 离线文档

📌 [4.1 离线文档](https://mall.bilibili.com/neul-next/detailuniversal/detail.html?isMerchant=1&page=detailuniversal_detail&saleType=10&itemsId=11372029&loadingShow=1&noTitleBar=1&msource=merchant_share)

📌 [4.0 离线文档](https://mall.bilibili.com/neul-next/detailuniversal/detail.html?isMerchant=1&page=detailuniversal_detail&saleType=10&itemsId=12020073&loadingShow=1&noTitleBar=1&msource=merchant_share)

📌 [3.2 离线文档](https://mall.bilibili.com/neul-next/detailuniversal/detail.html?isMerchant=1&page=detailuniversal_detail&saleType=10&itemsId=12019346&loadingShow=1&noTitleBar=1&msource=merchant_share)

---

## ✅️️ CDP 接口手册

📌 [CDP 接口手册](https://mall.bilibili.com/detail.html?itemsId=40573480&noTitleBar=1&jumpLinkType=0&from=detailspage&isMerchant=NaN&hasBack=false&msource=link&share_source=weixin&share_medium=android&bbid=C5F966E3-58FB-A945-3834-DE4F3E1A59CF40204infoc&ts=1778483592420)

---

## ✅️️ DrissionRecord 离线文档

📌 [1.0 离线文档](https://mall.bilibili.com/detail.html?itemsId=12874031&noTitleBar=1&jumpLinkType=0&from=detailspage&isMerchant=NaN&hasBack=false&msource=link&share_source=weixin&share_medium=android&bbid=C5F966E3-58FB-A945-3834-DE4F3E1A59CF40204infoc&ts=1778483548542)

<!-- https://www.drissionpage.cn/tutorials/QandA -->

# ❓ 常见问题

本页收集一些用户使用过程中的常见问题。

欢迎各位开发者添砖加瓦，您可提交 issues、PR，也可以写成博客文章，链接发给本库作者，直接链接到文章。

## ❔ 如何在无界面 Linux 使用

CentOS 请参考这篇文章：[linux 部署说明](https://blog.csdn.net/sinat_39327967/article/details/132181129?spm=1001.2014.3001.5501)

Ubuntu 请参考这篇文章：[DrissionPage在UbuntuLinux的使用](https://zhuanlan.zhihu.com/p/674687748)

---

## ❔ 为什么浏览器不能退出无头模式？

> 为什么设置过无头后，下次运行即使不设置`headless()`，浏览器依然进入无头状态？

因为上一次打开的浏览器没有关闭，只是因为开了无头不可见，程序继续接管了它。

如果要关闭浏览器，可在程序结束时使用`Chromium`对象的`quit()`语句。

也可以设置`co.headless(False)`，程序会自动关闭之前的无头浏览器再启动新的。

另请注意，`tab.close()`的功能是关闭当前标签页，而不是关闭浏览器，除非浏览器只有一个标签页。

---

## ❔ 如何禁用保存密码、恢复页面等提示气泡？

浏览器提示气泡出现时可以手动关闭，不关闭也不影响自动操作，在代码中阻止其显示也是可以的。
加一些浏览器配置代码即可禁止相应的气泡显示，需要添加下面这样的代码：

```python
co = ChromiumOptions()

# 阻止“自动保存密码”的提示气泡
co.set_pref('credentials_enable_service', False)

# 阻止“要恢复页面吗？Chrome未正确关闭”的提示气泡
co.set_argument('--hide-crash-restore-bubble')
```

---

## ❔ 点击报错“该元素没有位置及大小”怎么办？

没有位置及大小是正常的，很多元素都没有位置和大小。

这个时候你要检查是否页面中有同名元素，定位符没写准确拿到了另一个。

如果要点击的元素就是没有位置的，可以强制使用 js 点击，用法是 `.click(by_js=True)`，可以简写为 `.click('js')`。

---

## ❔ 如何使用启动参数、用户配置、实验项等功能？

**arguments 启动参数**

- 使用参考：<http://DrissionPage.cn/ChromiumPage/browser_opt#-set_argument>
- 参数详见：<https://peter.sh/experiments/chromium-command-line-switches/>

**prefs 用户配置**

- 使用参考：<http://DrissionPage.cn/ChromiumPage/browser_opt#-set_pref>
- 参数详见：<https://src.chromium.org/viewvc/chrome/trunk/src/chrome/common/pref_names.cc>

**flags 实验项**

- 使用参考：<http://DrissionPage.cn/ChromiumPage/browser_opt#-set_flag>
- 参数详见：chrome://flags

注意

外部链接仅供参考，请谨慎使用任何高级功能，仅在确保一切都可以掌控时才可使用，因为使用这些功能可能会导致浏览器数据丢失或安全和隐私受到威胁。

---

## ❔ 如何匹配特殊字符（如`'&nbsp;'`）文本？

需先将特殊字符转为十六进制形式，详见《查找元素》中《语法速查表》一节。

<!-- https://www.drissionpage.cn/tutorials/functions/new_browser -->

# 🥦 创建全新的浏览器

默认设置下，DrissionPage 会在 9222 端口创建浏览器，如果该端口下浏览器已经启动，则会接管使用。

并且会重复使用用户文件夹，即该端口登录过的账号，下次启动时可能仍有效，使用的插件也一样。

这为调试和日常使用带来大量便利，无须总是要处理登录和加载插件。

但项目中往往需要创建全新的浏览器环境，不希望复用之前的用户数据，可用以下方法实现：

## ✅️️ `auto_port()`方法

使用`ChromiumOptions`对象的`atuo_port()`方法，可指定程序自动创建全新的浏览器，多个浏览器互不干扰。

```python
from DrissionPage import ChromiumOptions, Chromium

co = ChromiumOptions().auto_port()
browser1 = Chromium(co)
browser2 = Chromium(co)
```

如此即可创建两个全新且独立的浏 览器。

可以注意到，示例中两个`Chromium`对象共用了一个`ChromiumOptions`对象，这在设置`auto_port()`时才会生效。

如果没有设置`auto_port()`，两个页面对象其实是同一个。

注意

如果使用`atuo_port()`后再使用`set_local_port()`、`set_address()`或`set_user_data_path()`，会覆盖`auto_port()`设置。

---

## ✅️️ 手动配置

如果有更细致的需求，不使用`auto_port()`，可自行使用`set_local_port()`、`set_address()`和`set_user_data_path()`为每个浏览器指定端口和用户文件夹。

注意

- 务必注意的是，每个浏览器的端口和用户文件夹都必须是独立的，不能复用
- 每个浏览器都要一个`ChromiumOptions`对象，不能复用

```python
from DrissionPage import Chromium, ChromiumOptions

co1 = ChromiumOptions().set_local_port(9111).set_user_data_path('data1')
co2 = ChromiumOptions().set_local_port(9222).set_user_data_path('data2')

browser1 = Chromium(co1)
browser2 = Chromium(co2)
```

<!-- https://www.drissionpage.cn/tutorials/functions/create_browsers -->

# 🥦 浏览器多开

本节介绍如何启动多个浏览器同时使用。

## ✅️️ 直接指定端口

使用`Chromium()`启动浏览器时可以直接指定端口来启动多个浏览器。

如果指定端口已有浏览器在运行，会接管这个浏览器。

使用端口号创建的浏览器用户数据文件夹会保留，只要临时文件夹未被清理，下次使用该端口时还会使用这些数据，比如登录信息和插件。

```python
from DrissionPage import Chromium

browser1 = Chromium(9222)
browser2 = Chromium(9333)
```

## ✅️️ 自动设置端口

使用`ChromiumOptions`对象的`auto_port()`方法，可自动获取空闲端口，并创建全新浏览器（无用户数据和插件）。

这时多个页面对象可共用一个`ChromiumOptions`对象，不会产生冲突。

浏览器关闭后会自动删除用户文件夹，不会过多占用硬盘空间。

```python
from DrissionPage import Chromium, ChromiumOptions

co = ChromiumOptions().auto_port()
browser1 = Chromium(co)
browser2 = Chromium(co)
```

## ✅️️ 手动指定端口和路径

也可以用指定独立端口和用户文件夹路径的方式启动多个浏览器。

需要注意的是，端口和用户文件夹每个浏览器都要独立使用，不能共用。

因此，这时每个页面对象需要自己的配置对象。

```python
from DrissionPage import Chromium, ChromiumOptions

co1 = ChromiumOptions().set_local_port(9222).set_user_data_path('data1')
co2 = ChromiumOptions().set_local_port(9333).set_user_data_path('data2')
browser1 = Chromium(co1)
browser2 = Chromium(co2)
```

<!-- https://www.drissionpage.cn/tutorials/functions/headless -->

# 🥦 无头模式

要使用无头模式很简单，在`ChromiumOptions`设置`headless()`即可。

```python
from DrissionPage import Chromium, ChromiumOptions

co = ChromiumOptions().headless()
browser = Chromium(co)
```

需要注意的是，程序结束时浏览器不会自动关闭，下次运行会继续接管该浏览器。

无头浏览器因为看不见很容易被忽视。可在程序结尾用`browser.quit()`将其关闭。

<!-- https://www.drissionpage.cn/tutorials/functions/set_cookies -->

# 🥦 设置 cookies

## ✅️️ 设置 cookies

### 📌 页面对象中设置

任意页面对象都有`set.cookies()`方法，用于设置 cookies。

该方法接收多种格式的 cookies 信息，可设置一个或多个 cookies。

使用浏览器时，任意页面对象设置的 cookies 是所有标签页共用的（由`new_tab(new_context=True)`创建的标签页除外）。

**示例：**

```python
from DrissionPage import Chromium

tab = Chromium().latest_tab
cookies = 'name1=value1; name2=value2; path=/; domain=.example.com;'

tab.set.cookies(cookies)
```

---

### 📌 `SessionOptions`中设置

`SessionOptions`对象有`set_cookies()`方法，可接收一个或多个 cookies，用于`SessionPage`初始化时设置 cookies。

每次设置会覆盖之前所有 cookies 信息。

**示例：**

```python
from DrissionPage import SessionOptions

cookies = 'name1=value1; name2=value2; path=/; domain=.example.com;'

co = SessionOptions()
co.set_cookies(cookies)
```

---

### 📌 删除 cookies

页面对象用`set.cookies.remove()`和`set.cookies.clear()`删除和清空 cookies。

`SessionOptions`对象用`set_cookies(None)`清空 cookies。

具体用法详见使用文档有关章节。

---

## ✅️️ cookies 格式

### 📌 设置一个 cookie

设置一个 cookie 时，可传入`Cookie`、`dict`或`str`类型。

`dict`和`str`需要有`name`和`value`字段。

`str`多个字段间用`';'`或`','`分隔，但不能两种同时出现。

**格式：**

```python
# dict类型
{'name': 'abc', 'value': '123', 'domain': '.example.com', ...}

# str类型
'name=abc; value=123; domain=.example.com; ...'
```

---

### 📌 设置多个 cookies

设置多个时，可传入`CookieJar`、`list`、`tuple`、`str`、`dict`类型。

列表里面可以放`Cookie`、`str`或`dict`类型，多个 cookies 格式可以是不同的。

注意

列表中如果放`str`或`dict`，每个项都只能是一个 cookie。

**格式：**

```python
# dict类型
{'abc': '123', 'def': '456', 'domain': '.example.com', ...}

# str类型
'abc=123; def=456; domain=.example.com; ...'

# list或tuple类型
['name=123; domain=.example.com; ...', 'name=abc; value=123; domain=.example.com; ...']
```

---

### 📌 说明

cookies 中只有`name`和`value`字段是必须的，但如果没有`domain`字段，添加到浏览器时会自动添加。

添加的内容根据调用`set.cookies()`方法的对象 url 而定。

比如一个 Tab 对象当前 url 为`'https://www.baidu.com'`，添加无指定域名的 cookies 时，会自动添加该字段，内容为`'www.baidu.com'`。

<!-- https://www.drissionpage.cn/tutorials/TgeBrowser -->

# 🌐 连接 TgeBrowser 指纹浏览器

## 简介

TgeBrowser 提供 API 接口启动浏览器，可配合 DrissionPage 进行自动化控制。

[TgeBrowser 官网](https://www.tgebrowser.com)

**适用场景：** 批量操作、数据采集、自动化测试

---

## 安装依赖

```bash
pip install DrissionPage requests
```

---

## 快速开始

### 完整示例代码

```python
import requests
import time
from DrissionPage import ChromiumPage, ChromiumOptions

# ========== 配置 ==========
API_BASE_URL = "http://127.0.0.1:50326"
API_KEY = "your_api_key_here"  # 在 TgeBrowser 客户端获取

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# ========== 步骤 1: 创建浏览器环境 ==========
print("1. 创建浏览器环境...")
response = requests.post(
    f"{API_BASE_URL}/api/browser/create",
    json={
        "browserName": "自 动化测试",  # 环境名称
        "proxy": {
            "protocol": "socks5",
            "host": "proxy.example.com",
            "port": 8888,
            "username": "username",
            "password": "password",
        },
        "fingerprint": {
          "os": "Windows",
          "platformVersion": 11,
          "kernel": "135",
          "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.9.2537 Safari/537.36",
          "canvas": True,
          "speechVoices": True,
          "clientRects": True,
          "fonts": ["Arial", "Courier New"],
          "disableTLS": [],
          "resolution": "1920x1080",
          "ram": 8,
          "cpu": 4,
          "language": "en-US",
           "languageBaseIp": True,
          "timezone": "Europe/Amsterdam",
          "timezoneBaseIp": True,
          "hardwareAcceleration": True,
          "disableSandbox": False,
          "startupParams": "",
          "deviceName": "DESKTOP-ABCD",
          "portScanProtection": ""
        },
        "startInfo": {
          "startPage": {
            "mode": "custom",
            "value": [
                "https://www.baidu.com"
            ]
          },
          "otherConfig": {
            "openConfigPage": False,
            "checkPage": True,
            "extensionTab": True
          }
        }
    },
    headers=headers
)

env_id = response.json()["data"]["envId"]
print(f"   环境创建成功，ID: {env_id}")

# ========== 步骤 2: 启动浏览器 ==========
print("2. 启动浏览器...")
response = requests.post(
    f"{API_BASE_URL}/api/browser/start",
    json={"envId": env_id},
    headers=headers
)

debug_port = response.json()["data"]["port"]
print(f"   浏览器已启动，调试端口: {debug_port}")

# ========== 步骤 3: 连接 DrissionPage ==========
print("3. 连接 DrissionPage...")
time.sleep(3)  # 等待浏览器完全启动

# 方式1: 通过端口连接（推荐）
co = ChromiumOptions().set_local_port(debug_port)
page = ChromiumPage(addr_or_opts=co)

# 方式2: 直接使用端口号
# from DrissionPage import Chromium
# page = Chromium(debug_port)

# 方式3: 使用地址:端口
# page = Chromium(f'127.0.0.1:{debug_port}')

# 方式4: 使用 WebSocket URL（需要先获 取 ws_url）
# ws_url = response.json()["data"]["ws"]
# page = Chromium(ws_url)

print("   DrissionPage 连接成功")

# ========== 步骤 4: 执行自动化操作 ==========
print("4. 执行自动化操作...")

# 访问网页
page.get('https://www.example.com')
print(f"   当前页面: {page.title}")

# 更多操作示例
page.get_screenshot('screenshot.png')  # 截图
print("   已保存截图")

print("\n完成！")
```

### 代码说明

#### 步骤 1: 创建浏览器环境

```python
response = requests.post(
    f"{API_BASE_URL}/api/browser/create",
    json={
        "browserName": "自动化测试",  # 环境名称
        "proxy": {
            "protocol": "socks5",
            "host": "proxy.example.com",
            "port": 8888,
            "username": "username",
            "password": "password",
        },
        "fingerprint": {
          "os": "Windows",
          "platformVersion": 11,
          "kernel": "135",
          "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.9.2537 Safari/537.36",
          "canvas": True,
          "speechVoices": True,
          "clientRects": True,
          "fonts": ["Arial", "Courier New"],
          "disableTLS": [],
          "resolution": "1920x1080",
          "ram": 8,
          "cpu": 4,
          "language": "en-US",
           "languageBaseIp": True,
          "timezone": "Europe/Amsterdam",
          "timezoneBaseIp": True,
          "hardwareAcceleration": True,
          "disableSandbox": False,
          "startupParams": "",
          "deviceName": "DESKTOP-ABCD",
          "portScanProtection": ""
        },
        "startInfo": {
          "startPage": {
            "mode": "custom",
            "value": [
                "https://www.baidu.com"
            ]
          },
          "otherConfig": {
            "openConfigPage": False,
            "checkPage": True,
            "extensionTab": True
          }
        }
    },
    headers=headers
)
env_id = response.json()["data"]["envId"]
```

**说明：**

- 调用 `/api/browser/create` 接口创建浏览器环境
- `browserName` - 给环境起个名字，方便识别
- `proxy` - 代理
- 返回 `envId` - 环境ID，后续操作都需要用到

#### 步骤 2: 启动浏览器

```python
response = requests.post(
    f"{API_BASE_URL}/api/browser/start",
    json={"envId": env_id},
    headers=headers
)
debug_port = response.json()["data"]["port"]
```

**说明：**

- 调用 `/api/browser/start` 接口启动浏览器
- 传入刚才创建的 `envId`
- 返回 `port` - 调试端口，DrissionPage 需要用这个端口连接

#### 步骤 3: 连接 DrissionPage（多种方式）

**方式 1: 使用 ChromiumOptions（推荐）**

```python
from DrissionPage import ChromiumPage, ChromiumOptions

time.sleep(3)  # 等待浏览器完全启动
co = ChromiumOptions().set_local_port(debug_port)
page = ChromiumPage(addr_or_opts=co)
```

**方式 2: 直接使用端口号**

```python
from DrissionPage import Chromium

time.sleep(3)
page = Chromium(debug_port)
```

**方式 3: 使用地址:端口**

```python
from DrissionPage import Chromium

time.sleep(3)
page = Chromium(f'127.0.0.1:{debug_port}')
```

**方式 4: 使用 WebSocket URL**

```python
from DrissionPage import Chromium

# 先获取 WebSocket URL
ws_url = response.json()["data"]["ws"]

time.sleep(3)
page = Chromium(ws_url)
```

**说明：**

- `time.sleep(3)` - 等待 3 秒，确保浏览器完全启动
- `debug_port` - 从 API 返回的调试端口
- `ws_url` - 从 API 返回的 WebSocket 连接地址
- 所有方式效果相同，选择最适合的即可

#### 步骤 4: 使用 DrissionPage 操作

```python
page.get('https://www.example.com')  # 访问网页
page.title  # 获取页面标题
page.get_screenshot('screenshot.png')  # 截图
```

**说明：**

- 现在可以使用 DrissionPage 的所有功能进行自动化操作

---

## 连接浏览器的多种方式

TgeBrowser API 返回的浏览器信息包含多个连接方式，可以根据需要选择：

```python
# API 返回的数据
{
  "success": true,
  "data": {
    "envId": 900,
    "browserName": "测试环境",
    "port": 34721,           # 调试端口
    "ws": "ws://127.0.0.1:34721/devtools/browser/xxx",  # WebSocket URL
    "http": "http://127.0.0.1:34721/json/version",
    "pid": 32512
  }
}
```

### 方式对比

| 方式 | 代码 | 说明 |
| --- | --- | --- |
| ChromiumOptions | `ChromiumPage(ChromiumOptions().set_local_port(port))` | 最灵活，可设置更多选项 |
| 端口号 | `Chromium(34721)` | 最简洁 |
| 地址:端口 | `Chromium('127.0.0.1:34721')` | 支持远程连接 |
| WebSocket | `Chromium('ws://127.0.0.1:34721/devtools/browser/xxx')` | 直接使用完整地址 |

### 完整示例

```python
import requests
import time
from DrissionPage import Chromium, ChromiumPage, ChromiumOptions

API_BASE_URL = "http://127.0.0.1:50326"
API_KEY = "your_api_key"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# 创建并启动浏览器
response = requests.post(
    f"{API_BASE_URL}/api/browser/create",
    json={"browserName": "连接测试", "proxy": {"protocol": "direct"}},
    headers=headers
)
env_id = response.json()["data"]["envId"]

response = requests.post(
    f"{API_BASE_URL}/api/browser/start",
    json={"envId": env_id},
    headers=headers
)

# 获取连接信息
data = response.json()["data"]
port = data["port"]
ws_url = data["ws"]

print(f"调试端口: {port}")
print(f"WebSocket: {ws_url}")

time.sleep(3)

# ========== 方式 1: ChromiumOptions ==========
co = ChromiumOptions().set_local_port(port)
page1 = ChromiumPage(addr_or_opts=co)
print(f"方式1 连接成功: {page1.title}")

# ========== 方式 2: 端口号 ==========
page2 = Chromium(port)
print(f"方式2 连接成功: {page2.title}")

# ========== 方式 3: 地址:端口 ==========
page3 = Chromium(f'127.0.0.1:{port}')
print(f"方式3 连接成功: {page3.title}")

# ========== 方式 4: WebSocket URL ==========
page4 = Chromium(ws_url)
print(f"方式4 连接成功: {page4.title}")

# 所有方式都可以正常使用
page1.get('https://www.baidu.com')
```

### 选择建议

- **开发调试** → 使用方式 2（最简洁）：`Chromium(port)`
- **需要配置** → 使用方式 1：`ChromiumOptions()` 可以设置更多选项
- **远程连接** → 使用方式 3：支持指定 IP 地址
- **已有 URL** → 使用方式 4：直接使用完整 WebSocket 地址

---

---

## DrissionPage 常用操作

### 页面操作

```python
# 访问网页
page.get('https://www.example.com')

# 获取页面信息
title = page.title
url = page.url

# 截图
page.get_screenshot('screenshot.png')

# 执行 JavaScript
result = page.run_js('return document.title')

# 刷新
page.refresh()
```

### 元素定位

```python
# 通过 ID
element = page.ele('#username')

# 通过 Class
element = page.ele('.button')

# 通过文本
element = page.ele('text:登录')

# 通过属性
element = page.ele('@name=email')

# 获取多个元素
elements = page.eles('tag:li')
```

### 元素操作

```python
# 输入文本
page.ele('#username').input('user123')

# 点击
page.ele('#login-btn').click()

# 获取文本
text = page.ele('.title').text

# 获取属性
href = page.ele('tag:a').attr('href')
```

### 等待

```python
# 等待元素出现
page.wait.ele_displayed('#result', timeout=10)

# 等待页面加载
page.wait.doc_loaded()

# 固定等待
page.wait(3)
```

## 参考资料

- [DrissionPage 官方文档](https://drissionpage.cn/)
- [TgeBrowser API 文档](https://docs.tgebrowser.com/docs.html)
- [快速开始](https://docs.tgebrowser.com/start.html)

<!-- https://www.drissionpage.cn/tutorials/barrack -->

# 🏪 小店

## 欢迎光顾作者的 B 站小店

作者的 B 站小店会陆续上线一些实用工具、离线文档、案例代码等，欢迎光临。

![](/assets/images/barrack-d92b34e66fbfb806f484614a6b8f8833.png)

---

## 商品

[骚神插件](https://gf.bilibili.com/item/detail/1108443001)

[DrissionPage 离线文档](https://gf.bilibili.com/item/detail/1108367001)