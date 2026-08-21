# NMEA 0183 船舶模拟系统

基于 Python 的 BS 架构 NMEA 0183 船舶导航数据模拟系统，支持船舶运动模拟、目标配置管理、传感器偏差仿真、多接口 TCP/UDP 数据输出、SQLite 数据持久化和实时日志监控。双击 EXE 即可启动，自动打开浏览器。

## 功能概览

### 1. 船舶模拟

- UTC 时间同步（只读，实时更新）
- 起始虚拟定位（经纬度），模拟运行时不可编辑
- 航向、航速设定
- 水深及随机变化量
- 风向风速及变化量
- 温湿度及变化量
- 气压参数
- 本船 MMSI（船舶信息区域）
- GGA 卫星数、HDOP、海拔高度
- VBW 对水速度
- 本船 VDO 报文类型多选（Type 1/5/24）和分片数配置
- 实时位置推算（基于航向航速）
- 配置持久化（SQLite），刷新页面不丢失

### 2. 目标配置

- **AIS 船舶目标**：每艘船独立配置 MMSI、船名、呼号、IMO号、船舶类型、目的地、吃水、航速、航向、相对方位、距离
- **航标目标**：配置 MMSI、名称、航标类型、方位、距离
- **特种目标**：5种特殊AIS设备仿真
  - 气象站（Type 8）— 广播气象数据（风速/风向/气压/温湿度/能见度）
  - 搜救飞机（Type 9）— 位置报告（高度/速度/航向）
  - 基站（Type 4）— 时间报告
  - SART（Type 14）— 安全告警广播
  - 航线广播（Type 8）— 区域信息
- 每个目标独立配置 VDM 报文类型（多选）和分片数（1=不分片，2-4=多片）
- 目标初始位置基于本船起始坐标 + 方位 + 距离计算
- 模拟运行后目标按自身航速航向独立移动
- 支持目标的增删改查操作

### 3. 传感器偏差设置

- AIS 传感器偏差：位置偏差(m)、速度偏差(kn)、航向偏差(°)
- 雷达传感器偏差：位置偏差(m)、方位偏差(°)、速度偏差(kn)、航向偏差(°)
- AIS 和雷达偏差独立计算，同一目标在两种输出中数据有差异
- 每次数据输出时独立随机生成偏差值
- 偏差值可在前端"偏差设置"页面配置并持久化

### 4. 接口管理

- TCP/UDP 协议接口创建、编辑、删除
- 本机 IP 自动检测，下拉选择（支持多网卡）
- 端口冲突校验（同协议端口不可重复，系统端口 8972 不可用）
- 15 种 NMEA 0183 语句输出：RMC、GGA、GLL、ZDA、VTG、VBW、MWV、DPT、DBT、MDA、VDM、VDO、HDT、TTM、TLL
- 连接状态实时监控（已连接/连接中/错误/未连接）
- 接口统计（总连接次数、中断次数、发送数据条数）
- 中断日志记录
- 实时 NMEA 数据流输出
- 接口为对外输出方，TCP 监听等待客户端连接，UDP 广播发送

### 5. 日志面板

- 毫秒级时间戳
- 按级别过滤（全部/数据/信息/警告/错误）
- 按接口过滤
- NMEA 数据语法高亮
- 最多保留 500 条记录

### 6. 标签页持久化

- 刷新页面后自动停留在当前标签页（localStorage 记忆）

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | Python 3.10+, Flask, Flask-SocketIO (threading 模式) |
| 前端 | HTML5, CSS3, 原生 JavaScript, Socket.IO Client |
| 数据库 | SQLite (持久化船舶配置、目标配置和接口配置) |
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

1. 切换到「船舶模拟」标签，配置船舶参数和本船VDO报文，点击「开始模拟」
2. 切换到「目标配置」标签，配置 AIS 船舶目标、航标目标、特种目标
3. 切换到「偏差设置」标签，配置 AIS 和雷达传感器偏差值
4. 切换到「接口管理」标签，点击「新建」创建接口
5. 选择协议（TCP/UDP）、选择本机 IP、填写端口、勾选 NMEA 数据格式
6. 点击「创建并连接」，系统自动启动接口并开始输出 NMEA 数据
7. 在日志面板查看实时数据输出

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

### 船舶模拟

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ship/state` | 获取船舶模拟状态 |
| GET | `/api/ship/defaults` | 获取默认配置 |
| GET | `/api/ship/saved-config` | 获取数据库中保存的配置 |
| POST | `/api/ship/start` | 启动模拟（带配置参数，保存到数据库） |
| POST | `/api/ship/stop` | 停止模拟 |
| POST | `/api/ship/config` | 更新模拟配置 |

### 目标配置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/targets/ais` | 获取 AIS 船舶目标列表 |
| POST | `/api/targets/ais` | 新增 AIS 船舶目标 |
| PUT | `/api/targets/ais/{id}` | 更新 AIS 船舶目标 |
| DELETE | `/api/targets/ais/{id}` | 删除 AIS 船舶目标 |
| GET | `/api/targets/aton` | 获取航标目标列表 |
| POST | `/api/targets/aton` | 新增航标目标 |
| PUT | `/api/targets/aton/{id}` | 更新航标目标 |
| DELETE | `/api/targets/aton/{id}` | 删除航标目标 |
| GET | `/api/targets/special` | 获取特种目标列表 |
| POST | `/api/targets/special` | 新增特种目标 |
| PUT | `/api/targets/special/{id}` | 更新特种目标 |
| DELETE | `/api/targets/special/{id}` | 删除特种目标 |

### 接口管理

| 方法 | 路径 | 说明 |
|------|------|------|
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

### 船舶模拟参数

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
| mmsi | 200123456 | 本船 MMSI |
| satellites | 8 | GGA 卫星数 |
| hdop | 0.8 | GGA 水平精度因子 |
| altitude | 34.7 | GGA 海拔高度 (m) |
| water_speed | 0.0 | VBW 对水速度 (kn)，0 时等于对地速度 |
| ship_name | SIM VESSEL | 本船船名（AIS Type 5/24） |
| callsign | SIMCALL | 本船呼号（AIS Type 5/24） |
| imo_number | 1234567 | 本船 IMO 号（AIS Type 5） |
| ship_type_ais | 36 | 本船 AIS 船舶类型 |
| destination | SHANGHAI | 本船目的地（AIS Type 5） |
| draught | 5.0 | 本船吃水 (m)（AIS Type 5） |
| vdo_msg_types | 1 | 本船 VDO 报文类型（多选，逗号分隔：1,5,24） |
| vdo_fragment_count | 1 | 本船 VDO 分片数（1=不分片） |

### 传感器偏差参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| ais_pos_dev | 10.0 | AIS 位置偏差 (m)，GPS定位误差 |
| ais_speed_dev | 0.1 | AIS 速度偏差 (kn)，SOG测量误差 |
| ais_heading_dev | 1.0 | AIS 航向偏差 (°)，COG/HDG误差 |
| radar_pos_dev | 30.0 | 雷达位置偏差 (m)，雷达定位误差 |
| radar_bearing_dev | 1.5 | 雷达方位偏差 (°)，方位角误差 |
| radar_speed_dev | 0.3 | 雷达速度偏差 (kn)，测速误差 |
| radar_heading_dev | 2.0 | 雷达航向偏差 (°)，航向计算误差 |

## 数据生成逻辑

### 目标定位

1. **初始位置计算**：目标位置 = 本船起始经纬度 + 方位(bearing) + 距离(distance)
2. **后续移动**：目标按自身配置的航速(speed)和航向(heading)独立移动
3. **真实值维护**：ship_simulator 维护每个目标的真实经纬度、速度、航向

### 传感器偏差仿真

```
目标真实值（ship_simulator维护）
    ├── AIS输出 = 真实值 + AIS偏差（每次独立随机）
    │   ├── 位置偏差: ±ais_pos_dev (默认10m)
    │   ├── 速度偏差: ±ais_speed_dev (默认0.1kn)
    │   └── 航向偏差: ±ais_heading_dev (默认1°)
    └── 雷达输出 = 真实值 + 雷达偏差（每次独立随机）
        ├── 位置偏差: ±radar_pos_dev (默认30m)
        ├── 方位偏差: ±radar_bearing_dev (默认1.5°)
        ├── 速度偏差: ±radar_speed_dev (默认0.3kn)
        └── 航向偏差: ±radar_heading_dev (默认2°)
```

AIS 和雷达各自独立计算偏差，同一目标在 VDM/VDO 和 TTM/TLL 输出中的位置、速度、航向数据会有差异。

## NMEA 数据协议规范

### AIS VDM/VDO

**基本位置报告（Type 1）**

- 载荷长度：168 bits（28 字符），符合 ITU-R M.1371
- MMSI 编码：30 位掩码（0x3FFFFFFF），本船 MMSI 200123456
- 目标 MMSI：≥ 201000000，与本船距离 0.5-8 nm
- VDM 通道 B（他船），VDO 通道 A（本船）

**报文类型**

| 类型 | 名称 | 说明 |
|------|------|------|
| Type 1 | 位置报告 | 动态信息（位置/速度/航向） |
| Type 4 | 基站报告 | 时间与位置（特种目标） |
| Type 5 | 静态与航次数据 | IMO号/船名/呼号/吃水/目的地 |
| Type 8 | 广播二进制报文 | 气象数据/航线信息（特种目标） |
| Type 9 | SAR飞机位置报告 | 搜救飞机位置/高度/速度 |
| Type 14 | 安全广播报文 | SART安全告警 |
| Type 21 | 航标报告 | 航标位置/名称/类型 |
| Type 24 | 静态数据报告 | Part A（船名）+ Part B（船型/呼号） |

**报文分片**

每个目标可独立配置分片数：
- 1 = 不分片（单句输出）
- 2-4 = 手动分片（均匀拆分为指定片数）

### 雷达 TTM/TLL

- TTM 和 TLL 使用独立索引，目标编号 1-N（N 为 AIS 目标数量）
- TTM 包含：目标距离、方位、航速、航向、CPA/TCPA
- TLL 包含：目标经纬度、距离、UTC 时间
- TTM 和 TLL 使用独立的雷达偏差值，与 AIS 输出相互独立

### 跨字段一致性

本船传感器数据保持一致：

| 物理量 | 对比字段 | 一致性 |
|--------|----------|--------|
| 位置 | RMC / GGA / GLL | 完全一致 |
| 航向 | RMC COG / VTG COG / HDT | 完全一致 |
| 速度 | RMC SOG / VTG SOG / VBW | 完全一致 |
| 水深 | DPT / DBT | 完全一致 |
| 风向风速 | MWV / MDA | 偏差 < 0.5° |

目标数据通过传感器偏差产生差异：同一目标在 AIS (VDM) 和雷达 (TTM/TLL) 中的位置/速度/航向数据独立偏差。

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
- VDM/TTM/TLL 目标数据一致性

## Docker 部署

### 方式一：Docker 命令行

```bash
docker build -t qdzhuning/nmea-simulator:latest .

docker run -d \
  --name nmea-simulator \
  -p 8972:8972 \
  -e NMEA_DB_PATH=/data/nmea_sim.db \
  -v ./data:/data \
  qdzhuning/nmea-simulator:latest
```

### 方式二：Docker Compose (fnOS)

在 fnOS 中新建 `docker-compose.yml` 文件运行：

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
| ship_config | 船舶模拟配置（所有参数 + 偏差配置 + 运行状态） |
| interfaces | 接口配置（名称、协议、IP、端口、数据格式） |
| ais_targets | AIS 船舶目标（MMSI、船名、航速航向、方位距离、报文类型、分片数） |
| aton_targets | 航标目标（MMSI、名称、类型、方位距离、报文类型、分片数） |
| special_targets | 特种目标（设备类型、气象参数、分片数） |

数据库文件位于运行目录（Python 源码目录或 EXE 同目录），删除后重启会自动重建。Docker 环境下通过 `NMEA_DB_PATH` 环境变量指定路径。

## 许可证

MIT License
