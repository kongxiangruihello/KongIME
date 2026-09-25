# KongIME 云服务部署说明（0.12 开发版）

本目录提供服务端代码，不是已经上线的云服务。客户端默认未配置地址。尚未在公网环境验证真实邮件送达、HTTPS 代理或容量；先用于个人测试，扩大使用前需要补齐监控、运营配额、账号注销和灾备。

## 数据与协议

邮箱验证码验证成功即创建账号。验证码有效 10 分钟、最多尝试 5 次；每邮箱每分钟一次、每小时最多 6 次，来源地址每小时最多 30 次。会话有效 30 天，数据库只保存其 SHA-256；验证码保存带服务器密钥的 HMAC。客户端会话保存在本机钥匙串。

每账号保留最近 20 份统一配置，每份最多 32 MB；上传要求 base_revision 与最新版本一致，否则返回 409，不覆盖新版本。服务端按账号筛选全部版本查询。客户端恢复前重新验证配置并保留回退点。自动学习词频不包含；这是手动快照同步，无自动合并。

配置在服务器 SQLite 中以明文 JSON 保存，不是端到端加密。部署者可以读取配置，生产存储与备份应限制访问。不要记录请求正文、验证码、Authorization 头或邮件凭证。

## 本机测试（不发送邮件）

在项目根目录：

```sh
python3 cloud/server.py --db /tmp/kongime-cloud-test/data.sqlite --dev-mailbox /tmp/kongime-cloud-test/mail --port 18862
```

只监听 127.0.0.1。验证码写入上述 mail 目录中按邮箱哈希命名的 JSON。测试客户端需要进程环境变量 KONGIME_CLOUD_URL=http://127.0.0.1:18862 和 KONGIME_CLOUD_DEV=1。这些变量不能写入发布应用；正式客户端只接受 HTTPS 地址。

## 服务端运行条件

Linux、Python 3.11+、Gunicorn、受信任 HTTPS 入口、支持 SMTP over TLS 的邮件账号、持久化磁盘。代码开发测试使用 macOS Python 3.9 标准库；Linux 部署仍需实际验证。

配置下列环境变量，通过服务器的受保护环境文件或秘密管理服务注入，不能写入客户端、源码或聊天：

- KONGIME_CLOUD_DB：持久化数据库绝对路径。
- KONGIME_AUTH_SECRET：随机生成的至少 32 字符密钥。
- KONGIME_SMTP_HOST / KONGIME_SMTP_PORT：邮件服务地址，端口默认 465。
- KONGIME_SMTP_USER / KONGIME_SMTP_PASSWORD / KONGIME_SMTP_FROM：发件凭证和发件地址。

生产入口使用 WSGI factory：

```sh
python3 -m pip install gunicorn
gunicorn --bind 127.0.0.1:18862 --workers 2 --timeout 60 'cloud.server:create_app()'
```

公网只暴露 HTTPS 443，将请求代理至上述 loopback 地址，正文限额设为 33 MB，代理超时至少 60 秒；禁止公网直接访问 18862。开发 CLI 不能当生产服务使用。当前 IP 速率限制使用 REMOTE_ADDR；经普通反向代理会按代理地址共享每小时 30 次额度，适合小范围个人试用，不能据此声称可大规模注册。

部署成功后在客户端“账号与同步 → 服务连接”填写 HTTPS 域名。验证邮箱后先上传一份测试配置，再用另一台设备恢复；确认账号隔离、版本冲突、退出登录和备份恢复后再放入真实词库。邮件账号与域名验证需要你持有的服务账号，目前尚未配置。

数据库备份使用 SQLite backup API 或停服务后备份，不要在活跃写入时只复制部分数据库文件。每个账号理论上可占约 640 MB；本版无总用户容量上限，公网开放注册前需要增加配额与防滥用措施。

## 参考

- [Apple Keychain Services](https://developer.apple.com/documentation/security/keychain-services)
- [Python SMTP_SSL](https://docs.python.org/3.12/library/smtplib.html)
- [Python SQLite 事务](https://docs.python.org/3/library/sqlite3.html)
- [Gunicorn 部署](https://gunicorn.org/deploy/)
