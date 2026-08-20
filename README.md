# NMEA 0183 船舶模拟系统

基于 Python 的 BS 架构 NMEA 0183 船舶导航数据模拟系统，支持船舶运动模拟、多接口 TCP/UDP 数据输出、SQLite 数据持久化和实时日志监控。双击 EXE 即可启动，自动打开浏览器。

## 功能概览

### 1. 船舶模拟

- UTC 时间同步（只读，实时更新）
- 起始虚拟定位（经纬度），模拟运行时不可编辑
- 航向、航速设定
- 水深及随机变化量
- 风向风速及变化量
- 温湿度及变化量
- 气压参数
- AIS 目标数量、本船 MMSI
- 实时位置推算（基于航向航速）
- 配置持久化（SQLite），刷新页面不丢失

### 2. 接口管理

- TCP/UDP 协议接口创建、编辑、删除
- 本机 IP 自动检测，下拉选择（支持多网卡）
- 端口冲突校验（同协议端口不可重复，系统端口 8972 不可用）
- 15 种 NMEA 0183 语句输出：RMC、GGA、GLL、ZDA、VTG、VBW、MWV、DPT、DBT、MDA、VDM、VDO、HDT、TTM、TLL
- 连接状态实时监控（已连接/连接中/错误/未连接）
- 接口统计（总连接次数、中断次数、发送数据条数）
- 中断日志记录
- 实时 NMEA 数据流输出
- 接口为对外输出方，TCP 监听等待客户端连接，UDP 广播发送

### 3. 日志面板

- 毫秒级时间戳
- 按级别过滤（全部/数据/信息/警告/错误）
- 按接口过滤
- NMEA 数据语法高亮
- 最多保留 500 条记录

### 4. 标签页持久化

- 刷新页面后自动停留在当前标签页（localStorage 记忆）

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | Python 3.10+, Flask, Flask-SocketIO (threading 模式) |
| 前端 | HTML5, CSS3, 原生 JavaScript, Socket.IO Client |
| 数据库 | SQLite (持久化船舶配置和接口配置) |
| 通信 | REST API + WebSocket (Socket.IO) |
| TCP/UDP | Python socket + threading |
| 打包 | PyInstaller (生成单文件 EXE) |

## 项目结构

```
nmea-simulator/
├── app.py                  # Flask 主服务 (端口 8972)
├── db.py                   # SQLite 数据库管理
├── nmea_generator.py       # NMEA 0183 句子生成器 (15种)
├── ship_simulator.py       # 船舶模拟引擎
├── interface_manager.py    # TCP/UDP 接口管理器
├── requirements.txt        # Python 依赖
├── build.spec              # PyInstaller 打包配置
├── build.bat               # Windows 一键打包脚本
├── Dockerfile              # Docker 镜像构建文件
├── templates/
│   └── index.html          # 前端页面
├── static/
│   ├── css/
│   │   └── style.css       # 样式文件
│   └── js/
│       └── app.js          # 前端逻辑
└── README.md
```

## 快速开始

### 方式一：EXE 直接运行（推荐）

1. 双击 `NMEA-Simulator.exe`
2. 系统自动启动服务并打开浏览器
3. 访问 `http://localhost:8972`

> 数据库文件 `nmea_sim.db` 会自动创建在 EXE 同目录下。

### 方式二：Python 源码运行

```bash
cd nmea-simulator
pip install -r requirements.txt
python app.py
```

浏览器访问 `http://localhost:8972`

### 使用流程

1. 切换到「船舶模拟」标签，配置船舶参数，点击「开始模拟」
2. 切换到「接口管理」标签，点击「新建」创建接口
3. 选择协议（TCP/UDP）、选择本机 IP、填写端口、勾选 NMEA 数据格式
4. 点击「创建并连接」，系统自动启动接口并开始输出 NMEA 数据
5. 在日志面板查看实时数据输出

### 打包 EXE

```bash
# 安装打包依赖
pip install pyinstaller
pip install -r requirements.txt

# 执行打包
python -m PyInstaller build.spec --noconfirm
```

生成的 EXE 位于 `dist/NMEA-Simulator.exe`。

也可双击 `build.bat` 一键打包。

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ship/state` | 获取船舶模拟状态 |
| GET | `/api/ship/defaults` | 获取默认配置 |
| GET | `/api/ship/saved-config` | 获取数据库中保存的配置 |
| POST | `/api/ship/start` | 启动模拟（带配置参数，保存到数据库） |
| POST | `/api/ship/stop` | 停止模拟 |
| POST | `/api/ship/config` | 更新模拟配置 |
| GET | `/api/nmea-formats` | 获取 NMEA 格式列表 |
| GET | `/api/local-ips` | 获取本机网卡 IP 列表 |
| GET | `/api/interfaces` | 获取接口列表 |
| POST | `/api/interfaces` | 创建接口（含端口冲突校验） |
| GET | `/api/interfaces/{id}` | 获取接口详情 |
| PUT | `/api/interfaces/{id}` | 更新接口 |
| DELETE | `/api/interfaces/{id}` | 删除接口 |
| POST | `/api/interfaces/{id}/connect` | 连接接口 |
| POST | `/api/interfaces/{id}/disconnect` | 断开接口 |
| GET | `/api/logs` | 获取最近日志 |

## NMEA 0183 语句说明

| 代码 | 说明 | Talker |
|------|------|--------|
| RMC | 推荐最小导航信息（位置/速度/时间） | GP |
| GGA | GPS 定位数据 | GP |
| GLL | 地理位置 | GP |
| ZDA | 时间与日期 | GP |
| VTG | 对地航速航向 | GP |
| VBW | 对水/对地速度 | VD |
| MWV | 风速风向 | WI |
| DPT | 水深 | SD |
| DBT | 换能器以下水深 | SD |
| MDA | 气象综合数据 | WI |
| VDM | AIS 他船信息 | AI |
| VDO | AIS 本船信息 | AI |
| HDT | 真航向 | HE |
| TTM | 雷达跟踪目标 | RA |
| TLL | 目标经纬度 | RA |

## 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| start_latitude | 31.2304 | 起始纬度 |
| start_longitude | 121.4737 | 起始经度 |
| heading | 45.0 | 航向 (°) |
| speed | 12.0 | 航速 (kn) |
| water_depth | 50.0 | 基准水深 (m) |
| depth_variation | 5.0 | 水深随机变化量 (m) |
| wind_direction | 180.0 | 风向 (°) |
| wind_speed | 10.0 | 风速 (kn) |
| temperature | 22.0 | 温度 (°C) |
| humidity | 65.0 | 湿度 (%) |
| pressure | 1013.0 | 气压 (hPa) |
| ais_target_count | 5 | AIS 目标数量 |
| mmsi | 200123456 | 本船 MMSI |

## Docker 部署

### 方式一：Docker 命令行

```bash
docker build -t qdzhuning/nmea-simulator:latest .

docker run -d \
  --name nmea-simulator \
  -p 8972:8972 \
  qdzhuning/nmea-simulator:latest
```

### 方式二：Docker Compose (fnOS)

```yaml
services:
  nmea-simulator:
    image: qdzhuning/nmea-simulator:latest
    container_name: NMEA_Simulator
    ports:
      - "8972:8972"
    volumes:
      - ./volumes/nmea_simulator/data:/data
    restart: unless-stopped
    network_mode: host
```

## 数据存储

系统使用 SQLite 数据库（`nmea_sim.db`）持久化以下数据：

| 表 | 说明 |
|------|------|
| ship_config | 船舶模拟配置（所有参数 + 运行状态） |
| interfaces | 接口配置（名称、协议、IP、端口、数据格式） |

数据库文件位于运行目录（Python 源码目录或 EXE 同目录），删除后重启会自动重建。

## 许可证

MIT License
