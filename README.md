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
- AIS 船舶目标数量、航标目标数量、本船 MMSI
- AIS 报文分片模拟（7 种报文类型、3 种模式、4 种分片数）
- GGA 卫星数、HDOP、海拔高度
- VBW 对水速度
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
├── analyze_data.py         # 数据验证脚本（校验和/格式/一致性）
├── collect_data.py         # 数据采集脚本（TCP 连接采集）
├── requirements.txt        # Python 依赖
├── build.spec              # PyInstaller 打包配置
├── build.bat               # Windows 一键打包脚本
├── Dockerfile              # Docker 镜像构建文件
├── docker-compose.yml      # Docker Compose 编排文件
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
| GGA | GPS 定位数据（卫星数/HDOP/海拔） | GP |
| GLL | 地理位置 | GP |
| ZDA | 时间与日期 | GP |
| VTG | 对地航速航向 | GP |
| VBW | 对水/对地速度 | VD |
| MWV | 风速风向 | WI |
| DPT | 水深 | SD |
| DBT | 换能器以下水深 | SD |
| MDA | 气象综合数据（气压/温湿度/风向风速） | WI |
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
| wind_dir_variation | 30.0 | 风向变化量 (°) |
| wind_speed_variation | 2.0 | 风速变化量 (kn) |
| temperature | 22.0 | 温度 (°C) |
| humidity | 65.0 | 湿度 (%) |
| temp_variation | 2.0 | 温度变化量 (°C) |
| humidity_variation | 5.0 | 湿度变化量 (%) |
| pressure | 1013.0 | 气压 (hPa) |
| ais_target_count | 5 | AIS 船舶目标数量 |
| aton_target_count | 2 | 航标目标数量（Type 21 使用） |
| mmsi | 200123456 | 本船 MMSI |
| satellites | 10 | GGA 卫星数 |
| hdop | 0.8 | GGA 水平精度因子 |
| altitude | 35.0 | GGA 海拔高度 (m) |
| water_speed | 0.0 | VBW 对水速度 (kn)，0 时等于对地速度 |
| ais_fragment_mode | 0 | 报文分片模式：0=关闭 1=混合 2=纯分片 |
| ais_fragment_type | 5 | 分片报文类型：5/6/8/12/14/21/24 |
| ais_fragment_count | 0 | 分片数：0=自动 2/3/4=手动 |

## NMEA 数据协议规范

### AIS VDM/VDO

**基本位置报告（Type 1）**

- 载荷长度：168 bits（28 字符），符合 ITU-R M.1371
- MMSI 编码：30 位掩码（0x3FFFFFFF），本船 MMSI 200123456
- 目标 MMSI：≥ 201000000，与本船距离 0.5-8 nm
- 目标航向：基于本船航向 ±60°
- 目标航速：接近本船速度（±5 kn）
- VDM 通道 B（他船），VDO 通道 A（本船）

**报文分片模拟**

支持 7 种 AIS 报文类型的多分片输出：

| 类型 | 名称 | 固定/可变 | 默认分片 | 说明 |
|------|------|-----------|----------|------|
| Type 5 | 静态与航次数据 | 固定 424 bits | 2 | IMO 号、船名、呼号、尺寸、吃水、目的地、ETA |
| Type 6 | 寻址二进制报文 | 可变 | 自动 | 源 MMSI + 目标 MMSI + DAC/FID + 数据 |
| Type 8 | 广播二进制报文 | 可变 | 自动 | 源 MMSI + DAC/FID + 数据 |
| Type 12 | 寻址安全报文 | 可变 | 自动 | 源 MMSI + 目标 MMSI + 安全文本 |
| Type 14 | 安全广播报文 | 可变 | 自动 | 源 MMSI + 安全文本 |
| Type 21 | 航标报告 | 固定 332 bits | 1 | 航标 MMSI（99 开头）、名称、位置 |
| Type 24 | 静态数据报告 | 特殊 | 1+1 | Part A（船名）+ Part B（船型/呼号）两条独立消息 |

分片模式：
- **关闭**：仅输出 Type 1 位置报告
- **混合模式**：奇数秒 Type 1，偶数秒分片报文交替输出
- **纯分片模式**：仅输出选定类型的分片报文

分片数控制：
- **自动**：根据载荷大小按 56 字符/句自动拆分
- **手动 2/3/4 片**：均匀拆分为指定片数（可变类型自动调整数据长度）

目标分离：
- AIS 船舶目标（Type 1/5/6/8/12/14/24）：MMSI 201000000-775999999，与本船距离 0.5-8 nm
- 航标目标（Type 21）：MMSI 990000000+，与本船距离 0.5-5 nm

### 雷达 TTM/TLL

- TTM 和 TLL 使用独立索引，目标编号 1-N（N 为 AIS 目标数量）
- 同一编号目标在 TTM 和 TLL 中距离一致（偏差 0%）
- TTM 包含：目标距离、方位、航速、航向、CPA/TCPA
- TLL 包含：目标经纬度、距离、UTC 时间

### 跨字段一致性

不同字段输出相同物理量时保持一致或偏差 < 5%：

| 物理量 | 对比字段 | 一致性 |
|--------|----------|--------|
| 位置 | RMC / GGA / GLL | 完全一致 |
| 航向 | RMC COG / VTG COG / HDT | 完全一致 |
| 速度 | RMC SOG / VTG SOG / VBW | 完全一致 |
| 水深 | DPT / DBT | 完全一致 |
| 风向风速 | MWV / MDA | 偏差 < 0.5° |

## 数据验证

项目内置数据验证工具，可采集并验证 NMEA 输出数据：

```bash
# 1. 启动服务
python app.py

# 2. 创建接口后，采集 1 分钟数据
python collect_data.py

# 3. 验证数据（校验和/格式/跨字段一致性/目标一致性）
python analyze_data.py
```

验证内容包括：
- 校验和验证（XOR 校验，100% 通过率）
- 15 种 NMEA 语句格式与内容检查
- 跨字段数据一致性（位置/航向/速度/水深/风向）
- VDM/TTM/TLL 目标数据一致性（编号、距离、MMSI）

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
    environment:
      - NMEA_DB_PATH=/data/nmea_sim.db
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

数据库文件位于运行目录（Python 源码目录或 EXE 同目录），删除后重启会自动重建。Docker 环境下通过 `NMEA_DB_PATH` 环境变量指定路径。

## 许可证

MIT License
