# doubao2api 部署到 Render 完整指南

## 📦 文件说明

本目录包含的文件：
- `render.yaml` - Render 一键部署配置文件
- `upload_server.py` - 二维码上传识别服务完整代码
- `requirements-ext.txt` - 新增功能需要的依赖包列表

---

## 🔧 第一步：项目准备

1. 访问原项目仓库：https://github.com/wangchuxiaoji-oss/doubao2api
2. 点击右上角 Fork，将仓库复制到你的 GitHub 账号下
3. 克隆你 Fork 后的仓库到本地，将本目录的三个文件全部复制到项目根目录中
4. 打开项目的 `pyproject.toml`，在 `dependencies` 数组中追加以下依赖：
```toml
dependencies = [
    # ... 原有依赖保持不变 ...
    "pyzbar>=0.1.9",
    "opencv-python-headless>=4.8.0",
    "fastapi>=0.104.0",
    "uvicorn>=0.24.0",
    "python-multipart>=0.0.6",
    "numpy>=1.24.0",
]
```

5. 修改项目启动入口：如果需要同时保留原有 doubao2api 服务和二维码上传接口，你可以修改 `server.py` 整合 FastAPI，或者将 `upload_server.py` 的路由挂载到原有服务中。
   最简单的方式是修改 `render.yaml` 中的 `startCommand` 为双进程启动：
   ```yaml
   startCommand: (python -m doubao2api.server & python -m uvicorn upload_server:app --host 0.0.0.0 --port 8000)
   ```
   > 注意：如果端口冲突，可以将二维码服务运行在 8001 端口，或者使用 FastAPI 子应用挂载方式。

6. 将所有修改提交并推送到你的 GitHub 仓库。

---

## 🚀 第二步：部署到 Render

1. 访问 https://render.com，使用 GitHub 账号注册/登录
2. 点击右上角 **New +** → 选择 **Build and deploy from a Git repository**
3. 在仓库列表中选择你刚才 Fork 并修改好的 doubao2api 仓库
4. 填写部署配置：
   - **Name**: 自定义服务名称（例如 doubao2api-yourname）
   - **Region**: 选择 `Singapore` 或 `Oregon`（新加坡/美国俄勒冈，延迟低且网络可以访问豆包）
   - **Instance Type**: 选择 **Free** 免费实例
   - 其他配置保持默认，Render 会自动识别到项目根目录的 `render.yaml` 配置文件并自动填充。
5. 点击 **Create Web Service**，等待构建和部署完成（大约需要 3-5 分钟）

---

## 💾 第三步：配置 Disk 持久化存储（关键步骤）

Render 免费实例是容器化运行的，重启后所有容器内的文件都会丢失，必须配置持久化 Disk 来保存登录 Session：

1. 在 Render 控制台打开你刚创建的 doubao2api 服务页面
2. 点击顶部菜单的 **Disks** 标签
3. 点击 **Attach Disk** 按钮
4. 填写 Disk 配置：
   - **Name**: `session-storage`
   - **Mount Path**: 填写 `/data`（和 render.yaml 中的配置完全一致）
   - **Disk Size**: 选择 1GB（免费额度完全足够存储 sessions）
5. 点击 **Save**，Render 会自动重启服务并挂载磁盘。

> ✅ 挂载完成后，所有 `/data` 目录下的文件会永久保留，即使实例重启也不会丢失，你的登录 Session 状态就不会丢了。

---

## 🧪 第四步：测试接口

部署完成后，Render 会给你分配一个默认域名，类似：`https://doubao2api-abc123.onrender.com`

### 1. 测试健康检查
访问 `https://你的服务域名/health`，应该返回：
```json
{
  "status": "ok",
  "session_dir": "/data/sessions"
}
```

### 2. 测试上传二维码接口
准备好豆包登录页面的二维码截图，使用 curl 命令测试：
```bash
curl -X POST -F "file=@你的二维码图片路径.png" https://你的服务域名/upload_qr
```

### 预期输出
- 二维码识别成功，正在扫码：
  ```json
  {"status":"scanned"}
  ```
- 扫码确认，登录成功：
  ```json
  {
    "status": "confirmed",
    "sessionid": "xxxxxxx",
    "cookies": {...},
    "session_file_id": "xxxx-xxxx-xxxx",
    "session_save_path": "/data/sessions/xxx.json"
  }
  ```
- 二维码过期：
  ```json
  {"status": "expired", "message": "二维码已过期"}
  ```
- 识别失败：
  ```json
  {"status": "error", "message": "图片中未识别到二维码"}
  ```

---

## ⚠️ 注意事项

1. Render 免费实例如果连续 15 分钟没有访问会自动休眠，首次访问唤醒需要大约 50 秒，这是免费计划的正常限制。
2. 豆包的反爬机制可能会检测到异常扫码行为，建议不要短时间内批量登录多个账号，避免账号被临时限制。
3. 免费实例的带宽和内存有限，适合个人小范围使用，高并发场景建议升级付费实例。
