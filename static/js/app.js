/* ===== NMEA 0183 船舶模拟系统 — 前端逻辑 ===== */

// ---- State ----
let interfaces = [];
let selectedIfaceId = null;
let viewMode = 'empty';
let isEditing = false;
let logEntries = [];
let activeLogFilter = 'all';
let logIfaceFilter = null;
let nmeaFormats = [];
let localIps = ["0.0.0.0"];
let socket = null;
let sidebarCollapsed = false;
let shipRunning = false;

// ---- DOM ----
const $ = (id) => document.getElementById(id);

// ---- Utility ----
function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function showToast(type, message, duration = 3000) {
    const container = $('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

function formatNmea(raw) {
    if (!raw) return '';
    const starIdx = raw.lastIndexOf('*');
    if (starIdx < 4) return escapeHtml(raw);
    const checksum = raw.substring(starIdx + 1);
    const before = raw.substring(0, starIdx);
    const commaIdx = before.indexOf(',');
    if (commaIdx < 2) return escapeHtml(raw);
    const prefix = before.substring(0, commaIdx);
    const payload = before.substring(commaIdx);
    return `<span class="nmea-prefix">${escapeHtml(prefix)}</span><span class="nmea-payload">${escapeHtml(payload)}</span>*<span class="nmea-checksum">${escapeHtml(checksum)}</span>`;
}

const STATUS_LABELS = {
    connected: { text: '已连接', cls: 'connected' },
    connecting: { text: '连接中', cls: 'connecting' },
    error: { text: '错误', cls: 'error' },
    disconnected: { text: '未连接', cls: 'disconnected' },
};

async function api(url, method = 'GET', body = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(url, opts);
    const data = await res.json();
    if (!res.ok) {
        const msg = data.errors ? data.errors.join('; ') : (data.error || '请求失败');
        throw new Error(msg);
    }
    return data;
}

// ---- Clock ----
function updateClock() {
    const now = new Date();
    const h = String(now.getUTCHours()).padStart(2, '0');
    const m = String(now.getUTCMinutes()).padStart(2, '0');
    const s = String(now.getUTCSeconds()).padStart(2, '0');
    $('clock').textContent = `${h}:${m}:${s} UTC`;
}

// ---- Tab Switching ----
function switchTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`.tab-btn[data-tab="${tab}"]`)?.classList.add('active');
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    if (tab === 'ship') {
        $('viewShip').classList.add('active');
    } else if (tab === 'targets') {
        $('viewTargets').classList.add('active');
        loadTargets();
    } else if (tab === 'deviation') {
        $('viewDeviation').classList.add('active');
    } else {
        $('viewIface').classList.add('active');
    }
    localStorage.setItem('nmea_active_tab', tab);
}

document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

// ---- Socket.IO ----
function initSocket() {
    socket = io();

    socket.on('connect', () => {
        console.log('Socket.IO 已连接');
    });

    socket.on('disconnect', () => {
        console.log('Socket.IO 已断开');
    });

    socket.on('log', (entry) => {
        addLogEntry(entry);
    });

    socket.on('ship_update', (state) => {
        updateShipDisplay(state);
    });

    socket.on('interface_update', (msg) => {
        if (msg.action === 'create') {
            interfaces.push(msg.data);
            renderInterfaceList();
        } else if (msg.action === 'update') {
            const idx = interfaces.findIndex(i => i.id === msg.data.id);
            if (idx >= 0) {
                interfaces[idx] = msg.data;
                if (selectedIfaceId === msg.data.id && viewMode === 'detail') {
                    renderDetailView(msg.data);
                }
            }
            renderInterfaceList();
        } else if (msg.action === 'delete') {
            interfaces = interfaces.filter(i => i.id !== msg.data.id);
            if (selectedIfaceId === msg.data.id) {
                selectedIfaceId = null;
                switchView('empty');
            }
            renderInterfaceList();
        }
    });

    socket.on('interface_status', (data) => {
        const idx = interfaces.findIndex(i => i.id === data.id);
        if (idx >= 0) {
            interfaces[idx] = data;
            renderInterfaceList();
            if (selectedIfaceId === data.id && viewMode === 'detail') {
                renderDetailView(data);
            }
        }
    });
}

// ---- Ship Simulation ----
function updateShipDisplay(state) {
    $('rtUtc').textContent = state.utc_time || '—';
    $('rtLat').textContent = state.latitude != null ? `${state.latitude.toFixed(4)}°` : '—';
    $('rtLon').textContent = state.longitude != null ? `${state.longitude.toFixed(4)}°` : '—';
    $('rtHeading').textContent = state.heading != null ? `${state.heading.toFixed(1)}°` : '—';
    $('rtSpeed').textContent = state.speed != null ? `${state.speed.toFixed(1)} kn` : '—';
    $('rtDepth').textContent = state.water_depth != null ? `${state.water_depth.toFixed(1)} m` : '—';
    $('rtWind').textContent = state.wind_speed != null ? `${state.wind_speed.toFixed(1)} kn` : '—';
    $('rtTempHum').textContent = state.temperature != null
        ? `${state.temperature.toFixed(1)}°C / ${state.humidity.toFixed(0)}%` : '—';

    if (state.ais_target_count != null) {
        $('cfg_ais_target_count').value = state.ais_target_count;
    }
    if (state.aton_target_count != null) {
        $('cfg_aton_target_count').value = state.aton_target_count;
    }
    if (state.special_target_count != null) {
        $('cfg_special_target_count').value = state.special_target_count;
    }

    const dot = $('simStatusDot');
    const text = $('simStatusText');
    const btnStart = $('btnStartSim');
    const btnStop = $('btnStopSim');

    shipRunning = !!state.running;
    const latInputs = document.querySelectorAll('#cfg_start_latitude, #cfg_start_longitude');

    if (state.running) {
        dot.className = 'status-dot running';
        text.textContent = '模拟运行中';
        btnStart.textContent = '应用配置';
        btnStop.disabled = false;
        latInputs.forEach(el => el.disabled = true);
    } else {
        dot.className = 'status-dot stopped';
        text.textContent = '模拟未启动';
        btnStart.textContent = '开始模拟';
        btnStop.disabled = true;
        latInputs.forEach(el => el.disabled = false);
    }
}

function getCheckedValues(containerId) {
    return Array.from(document.querySelectorAll(`#${containerId} input[type="checkbox"]:checked`)).map(i => i.value);
}

function collectShipConfig() {
    return {
        start_latitude: parseFloat($('cfg_start_latitude').value),
        start_longitude: parseFloat($('cfg_start_longitude').value),
        heading: parseFloat($('cfg_heading').value),
        speed: parseFloat($('cfg_speed').value),
        water_depth: parseFloat($('cfg_water_depth').value),
        depth_variation: parseFloat($('cfg_depth_variation').value),
        wind_direction: parseFloat($('cfg_wind_direction').value),
        wind_speed: parseFloat($('cfg_wind_speed').value),
        wind_dir_variation: parseFloat($('cfg_wind_dir_variation').value),
        wind_speed_variation: parseFloat($('cfg_wind_speed_variation').value),
        temperature: parseFloat($('cfg_temperature').value),
        humidity: parseFloat($('cfg_humidity').value),
        temp_variation: parseFloat($('cfg_temp_variation').value),
        humidity_variation: parseFloat($('cfg_humidity_variation').value),
        pressure: parseFloat($('cfg_pressure').value),
        mmsi: parseInt($('cfg_mmsi').value),
        satellites: parseInt($('cfg_satellites').value),
        hdop: parseFloat($('cfg_hdop').value),
        altitude: parseFloat($('cfg_altitude').value),
        water_speed: parseFloat($('cfg_water_speed').value),
        ship_name: $('cfg_ship_name').value,
        callsign: $('cfg_callsign').value,
        imo_number: parseInt($('cfg_imo_number').value),
        ship_type_ais: parseInt($('cfg_ship_type_ais').value),
        destination: $('cfg_destination').value,
        draught: parseFloat($('cfg_draught').value),
        vdo_msg_types: getCheckedValues('cfg_vdo_msg_types').join(','),
        vdo_fragment_count: parseInt($('cfg_vdo_fragment_count').value),
        ais_pos_dev: parseFloat($('cfg_ais_pos_dev').value),
        ais_speed_dev: parseFloat($('cfg_ais_speed_dev').value),
        ais_heading_dev: parseFloat($('cfg_ais_heading_dev').value),
        radar_pos_dev: parseFloat($('cfg_radar_pos_dev').value),
        radar_bearing_dev: parseFloat($('cfg_radar_bearing_dev').value),
        radar_speed_dev: parseFloat($('cfg_radar_speed_dev').value),
        radar_heading_dev: parseFloat($('cfg_radar_heading_dev').value),
    };
}

$('btnStartSim').addEventListener('click', async () => {
    const config = collectShipConfig();
    try {
        if (shipRunning) {
            const data = await api('/api/ship/config', 'POST', config);
            updateShipDisplay(data.state);
            showToast('success', '配置已更新');
        } else {
            const data = await api('/api/ship/start', 'POST', config);
            updateShipDisplay(data.state);
            showToast('success', '船舶模拟已启动');
        }
    } catch (e) {
        showToast('error', `操作失败: ${e.message}`);
    }
});

$('btnStopSim').addEventListener('click', async () => {
    try {
        const data = await api('/api/ship/stop', 'POST');
        updateShipDisplay(data.state);
        showToast('info', '船舶模拟已停止');
    } catch (e) {
        showToast('error', `停止失败: ${e.message}`);
    }
});

// ---- Deviation Settings ----
const DEVIATION_DEFAULTS = {
    ais_pos_dev: 10.0, ais_speed_dev: 0.1, ais_heading_dev: 1.0,
    radar_pos_dev: 30.0, radar_bearing_dev: 1.5, radar_speed_dev: 0.3, radar_heading_dev: 2.0,
};

$('btnSaveDeviation').addEventListener('click', async () => {
    const config = collectShipConfig();
    try {
        const data = await api('/api/ship/config', 'POST', config);
        updateShipDisplay(data.state);
        showToast('success', '偏差设置已保存并应用');
    } catch (e) {
        showToast('error', `保存失败: ${e.message}`);
    }
});

$('btnResetDeviation').addEventListener('click', () => {
    Object.entries(DEVIATION_DEFAULTS).forEach(([k, v]) => {
        const el = $('cfg_' + k);
        if (el) el.value = v;
    });
    showToast('info', '已恢复默认偏差值，请点击保存以应用');
});

// ---- Target Configuration ----
let aisTargets = [];
let atonTargets = [];
let specialTargets = [];
let targetFormMode = 'create';
let targetFormType = 'ais';
let targetEditId = null;

const SHIP_TYPE_OPTIONS = [
    {value: 36, label: '乘客船'},
    {value: 37, label: '货船'},
    {value: 52, label: '油轮'},
    {value: 31, label: '拖船'},
    {value: 51, label: '搜救船'},
    {value: 0, label: '其他'},
];

const ATON_TYPE_OPTIONS = [
    {value: 0, label: '未指定'},
    {value: 1, label: '参考点'},
    {value: 2, label: '雷康'},
    {value: 3, label: '固定航标'},
    {value: 5, label: '灯船'},
    {value: 6, label: '灯塔'},
    {value: 7, label: '其他'},
];

const AIS_MSG_TYPE_OPTIONS = [
    {value: 1, label: 'Type 1 (动态)'},
    {value: 5, label: 'Type 5 (静态)'},
    {value: 24, label: 'Type 24 (静态)'},
];

const ATON_MSG_TYPE_OPTIONS = [
    {value: 21, label: 'Type 21 (航标)'},
];

const SPECIAL_TARGET_TYPE_OPTIONS = [
    {value: 'weather', label: '气象站 (Type 8)'},
    {value: 'aircraft', label: '搜救飞机 (Type 9)'},
    {value: 'basestation', label: '基站 (Type 4)'},
    {value: 'sart', label: 'SART (Type 14)'},
    {value: 'route', label: '航线广播 (Type 8)'},
];

// Sub-tab switching
document.querySelectorAll('.sub-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.sub-tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        document.querySelectorAll('.targets-sub-view').forEach(v => v.classList.remove('active'));
        const subtab = btn.dataset.subtab;
        if (subtab === 'ais') {
            $('subViewAis').classList.add('active');
        } else if (subtab === 'aton') {
            $('subViewAton').classList.add('active');
        } else if (subtab === 'special') {
            $('subViewSpecial').classList.add('active');
        }
    });
});

async function loadTargets() {
    try {
        const [ais, aton, special] = await Promise.all([
            api('/api/targets/ais'),
            api('/api/targets/aton'),
            api('/api/targets/special')
        ]);
        aisTargets = ais;
        atonTargets = aton;
        specialTargets = special;
        renderAisTargetsTable();
        renderAtonTargetsTable();
        renderSpecialTargetsTable();
    } catch (e) {
        showToast('error', `加载目标失败: ${e.message}`);
    }
}

function formatMsgTypes(typesStr, options) {
    if (!typesStr) return '—';
    const types = String(typesStr).split(',').filter(Boolean);
    return types.map(t => {
        const opt = options.find(o => String(o.value) === String(t));
        return opt ? opt.label : `Type ${t}`;
    }).join(', ');
}

function renderAisTargetsTable() {
    const tbody = $('aisTargetsBody');
    const empty = $('aisTargetsEmpty');
    const table = $('aisTargetsTable');
    tbody.innerHTML = '';

    if (aisTargets.length === 0) {
        empty.classList.add('active');
        table.style.display = 'none';
    } else {
        empty.classList.remove('active');
        table.style.display = '';
    }

    $('aisCount').textContent = `${aisTargets.length} 个目标`;

    aisTargets.forEach(t => {
        const shipTypeLabel = (SHIP_TYPE_OPTIONS.find(o => o.value === t.ship_type) || {}).label || t.ship_type;
        const msgTypesLabel = formatMsgTypes(t.msg_types, AIS_MSG_TYPE_OPTIONS);
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(t.mmsi)}</td>
            <td>${escapeHtml(t.ship_name || '—')}</td>
            <td>${escapeHtml(shipTypeLabel)}</td>
            <td>${t.speed.toFixed(1)}</td>
            <td>${t.heading.toFixed(1)}</td>
            <td>${t.bearing.toFixed(1)}</td>
            <td>${t.distance.toFixed(1)}</td>
            <td>${escapeHtml(msgTypesLabel)}</td>
            <td>${t.fragment_count || 1}</td>
            <td><div class="td-actions">
                <button class="td-action-btn edit" onclick="editTarget('ais', ${t.id})">编辑</button>
                <button class="td-action-btn delete" onclick="deleteTarget('ais', ${t.id})">删除</button>
            </div></td>
        `;
        tbody.appendChild(tr);
    });
}

function renderAtonTargetsTable() {
    const tbody = $('atonTargetsBody');
    const empty = $('atonTargetsEmpty');
    const table = $('atonTargetsTable');
    tbody.innerHTML = '';

    if (atonTargets.length === 0) {
        empty.classList.add('active');
        table.style.display = 'none';
    } else {
        empty.classList.remove('active');
        table.style.display = '';
    }

    $('atonCount').textContent = `${atonTargets.length} 个目标`;

    atonTargets.forEach(t => {
        const typeLabel = (ATON_TYPE_OPTIONS.find(o => o.value === t.aton_type) || {}).label || t.aton_type;
        const msgTypesLabel = formatMsgTypes(t.msg_types, ATON_MSG_TYPE_OPTIONS);
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(t.mmsi)}</td>
            <td>${escapeHtml(t.name || '—')}</td>
            <td>${escapeHtml(typeLabel)}</td>
            <td>${t.bearing.toFixed(1)}</td>
            <td>${t.distance.toFixed(1)}</td>
            <td>${escapeHtml(msgTypesLabel)}</td>
            <td>${t.fragment_count || 1}</td>
            <td><div class="td-actions">
                <button class="td-action-btn edit" onclick="editTarget('aton', ${t.id})">编辑</button>
                <button class="td-action-btn delete" onclick="deleteTarget('aton', ${t.id})">删除</button>
            </div></td>
        `;
        tbody.appendChild(tr);
    });
}

const SPECIAL_TYPE_AIS_MAP = {
    weather: 'Type 8',
    aircraft: 'Type 9',
    basestation: 'Type 4',
    sart: 'Type 14',
    route: 'Type 8',
};

function renderSpecialTargetsTable() {
    const tbody = $('specialTargetsBody');
    const empty = $('specialTargetsEmpty');
    const table = $('specialTargetsTable');
    tbody.innerHTML = '';

    if (specialTargets.length === 0) {
        empty.classList.add('active');
        table.style.display = 'none';
    } else {
        empty.classList.remove('active');
        table.style.display = '';
    }

    $('specialCount').textContent = `${specialTargets.length} 个目标`;

    specialTargets.forEach(t => {
        const typeLabel = (SPECIAL_TARGET_TYPE_OPTIONS.find(o => o.value === t.target_type) || {}).label || t.target_type;
        const aisType = SPECIAL_TYPE_AIS_MAP[t.target_type] || '—';
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(t.mmsi)}</td>
            <td>${escapeHtml(t.name || '—')}</td>
            <td>${escapeHtml(typeLabel)}</td>
            <td>${t.bearing.toFixed(1)}</td>
            <td>${t.distance.toFixed(1)}</td>
            <td>${(t.speed || 0).toFixed(1)}</td>
            <td>${escapeHtml(aisType)}</td>
            <td>${t.fragment_count || 1}</td>
            <td><div class="td-actions">
                <button class="td-action-btn edit" onclick="editTarget('special', ${t.id})">编辑</button>
                <button class="td-action-btn delete" onclick="deleteTarget('special', ${t.id})">删除</button>
            </div></td>
        `;
        tbody.appendChild(tr);
    });
}

function showTargetForm(type, target = null) {
    targetFormType = type;
    targetFormMode = target ? 'edit' : 'create';
    targetEditId = target ? target.id : null;

    const typeLabels = { ais: 'AIS 目标', aton: '航标目标', special: '特种目标' };
    const label = typeLabels[type] || '目标';
    const title = target ? `编辑${label}` : `新增${label}`;
    $('targetFormTitle').textContent = title;

    if (type === 'ais') {
        renderAisForm(target);
    } else if (type === 'aton') {
        renderAtonForm(target);
    } else if (type === 'special') {
        renderSpecialForm(target);
    }

    $('targetFormOverlay').style.display = 'flex';
}

function buildCheckboxGroup(containerId, options, selectedValues) {
    const selected = String(selectedValues || '').split(',').filter(Boolean);
    return options.map(o => {
        const checked = selected.includes(String(o.value));
        return `<label class="checkbox-item"><input type="checkbox" value="${o.value}" ${checked ? 'checked' : ''}> ${o.label}</label>`;
    }).join('');
}

function renderAisForm(target = null) {
    const t = target || {};
    const shipTypeOpts = SHIP_TYPE_OPTIONS.map(o =>
        `<option value="${o.value}" ${o.value === (t.ship_type ?? 36) ? 'selected' : ''}>${o.label}</option>`
    ).join('');
    const msgTypesCheckboxes = buildCheckboxGroup('tf_msg_types', AIS_MSG_TYPE_OPTIONS, t.msg_types || '1');
    const fc = t.fragment_count ?? 1;
    const fragmentOpts = [1, 2, 3, 4].map(n =>
        `<option value="${n}" ${n === fc ? 'selected' : ''}>${n}${n === 1 ? ' (不分片)' : ` 片`}</option>`
    ).join('');

    $('targetFormBody').innerHTML = `
        <div class="target-form-hint">相对方位：目标船位置以本船初始位置为基准，按方位(0-360°)+距离(nm)计算。模拟开始后目标按自身航向和航速移动。</div>
        <div class="target-form-section">
            <div class="target-form-section-title"><span class="dot"></span>静态信息</div>
            <div class="target-form-grid">
                <div class="target-form-field">
                    <label>MMSI</label>
                    <input type="number" id="tf_mmsi" value="${t.mmsi ?? 201000001}" step="1">
                </div>
                <div class="target-form-field">
                    <label>船名</label>
                    <input type="text" id="tf_ship_name" value="${escapeHtml(t.ship_name ?? '')}" maxlength="20">
                </div>
                <div class="target-form-field">
                    <label>呼号</label>
                    <input type="text" id="tf_callsign" value="${escapeHtml(t.callsign ?? '')}" maxlength="7">
                </div>
                <div class="target-form-field">
                    <label>IMO 号</label>
                    <input type="number" id="tf_imo_number" value="${t.imo_number ?? 0}" step="1">
                </div>
                <div class="target-form-field">
                    <label>AIS 船舶类型</label>
                    <select id="tf_ship_type">${shipTypeOpts}</select>
                </div>
                <div class="target-form-field">
                    <label>目的地</label>
                    <input type="text" id="tf_destination" value="${escapeHtml(t.destination ?? '')}" maxlength="20">
                </div>
                <div class="target-form-field">
                    <label>吃水 (m)</label>
                    <input type="number" id="tf_draught" value="${t.draught ?? 5.0}" step="0.1" min="0">
                </div>
            </div>
        </div>
        <div class="target-form-section">
            <div class="target-form-section-title"><span class="dot"></span>动态信息</div>
            <div class="target-form-grid-3">
                <div class="target-form-field">
                    <label>航速 (kn)</label>
                    <input type="number" id="tf_speed" value="${t.speed ?? 10.0}" step="0.1" min="0">
                </div>
                <div class="target-form-field">
                    <label>航向 (°)</label>
                    <input type="number" id="tf_heading" value="${t.heading ?? 0.0}" step="0.1" min="0" max="360">
                </div>
                <div class="target-form-field">
                    <label>相对方位 (°)</label>
                    <input type="number" id="tf_bearing" value="${t.bearing ?? 0.0}" step="0.1" min="0" max="360">
                </div>
                <div class="target-form-field">
                    <label>距离 (nm)</label>
                    <input type="number" id="tf_distance" value="${t.distance ?? 3.0}" step="0.1" min="0">
                </div>
            </div>
        </div>
        <div class="target-form-section">
            <div class="target-form-section-title"><span class="dot"></span>VDM 报文配置</div>
            <div class="target-form-grid">
                <div class="target-form-field">
                    <label>报文类型 (多选)</label>
                    <div class="checkbox-group" id="tf_msg_types">${msgTypesCheckboxes}</div>
                </div>
                <div class="target-form-field">
                    <label>分片数</label>
                    <select id="tf_fragment_count">${fragmentOpts}</select>
                </div>
            </div>
        </div>
        <div id="targetFormError" style="display:none;"></div>
        <div class="target-form-actions">
            <button type="button" class="btn btn-primary" id="btnSaveTargetForm">保存</button>
            <button type="button" class="btn btn-secondary" id="btnCancelTargetForm">取消</button>
        </div>
    `;

    $('btnSaveTargetForm').addEventListener('click', () => saveTargetForm('ais'));
    $('btnCancelTargetForm').addEventListener('click', closeTargetForm);
}

function renderAtonForm(target = null) {
    const t = target || {};
    const atonTypeOpts = ATON_TYPE_OPTIONS.map(o =>
        `<option value="${o.value}" ${o.value === (t.aton_type ?? 1) ? 'selected' : ''}>${o.label}</option>`
    ).join('');
    const msgTypesCheckboxes = buildCheckboxGroup('tf_msg_types', ATON_MSG_TYPE_OPTIONS, t.msg_types || '21');
    const fc = t.fragment_count ?? 1;
    const fragmentOpts = [1, 2, 3, 4].map(n =>
        `<option value="${n}" ${n === fc ? 'selected' : ''}>${n}${n === 1 ? ' (不分片)' : ` 片`}</option>`
    ).join('');

    $('targetFormBody').innerHTML = `
        <div class="target-form-hint">航标目标位置以本船初始位置为基准，按方位(0-360°)+距离(nm)计算。航标为固定位置，不随模拟移动。</div>
        <div class="target-form-section">
            <div class="target-form-section-title"><span class="dot"></span>航标信息</div>
            <div class="target-form-grid">
                <div class="target-form-field">
                    <label>MMSI</label>
                    <input type="number" id="tf_mmsi" value="${t.mmsi ?? 991234567}" step="1">
                </div>
                <div class="target-form-field">
                    <label>名称</label>
                    <input type="text" id="tf_name" value="${escapeHtml(t.name ?? '')}" maxlength="20">
                </div>
                <div class="target-form-field">
                    <label>航标类型</label>
                    <select id="tf_aton_type">${atonTypeOpts}</select>
                </div>
            </div>
        </div>
        <div class="target-form-section">
            <div class="target-form-section-title"><span class="dot"></span>位置（相对本船初始位置）</div>
            <div class="target-form-grid">
                <div class="target-form-field">
                    <label>相对方位 (°)</label>
                    <input type="number" id="tf_bearing" value="${t.bearing ?? 0.0}" step="0.1" min="0" max="360">
                </div>
                <div class="target-form-field">
                    <label>距离 (nm)</label>
                    <input type="number" id="tf_distance" value="${t.distance ?? 2.0}" step="0.1" min="0">
                </div>
            </div>
        </div>
        <div class="target-form-section">
            <div class="target-form-section-title"><span class="dot"></span>VDM 报文配置</div>
            <div class="target-form-grid">
                <div class="target-form-field">
                    <label>报文类型 (多选)</label>
                    <div class="checkbox-group" id="tf_msg_types">${msgTypesCheckboxes}</div>
                </div>
                <div class="target-form-field">
                    <label>分片数</label>
                    <select id="tf_fragment_count">${fragmentOpts}</select>
                </div>
            </div>
        </div>
        <div id="targetFormError" style="display:none;"></div>
        <div class="target-form-actions">
            <button type="button" class="btn btn-primary" id="btnSaveTargetForm">保存</button>
            <button type="button" class="btn btn-secondary" id="btnCancelTargetForm">取消</button>
        </div>
    `;

    $('btnSaveTargetForm').addEventListener('click', () => saveTargetForm('aton'));
    $('btnCancelTargetForm').addEventListener('click', closeTargetForm);
}

function renderSpecialForm(target = null) {
    const t = target || {};
    const targetTypeOpts = SPECIAL_TARGET_TYPE_OPTIONS.map(o =>
        `<option value="${o.value}" ${o.value === (t.target_type ?? 'weather') ? 'selected' : ''}>${o.label}</option>`
    ).join('');
    const fc = t.fragment_count ?? 1;
    const fragmentOpts = [1, 2, 3, 4].map(n =>
        `<option value="${n}" ${n === fc ? 'selected' : ''}>${n}${n === 1 ? ' (不分片)' : ` 片`}</option>`
    ).join('');

    $('targetFormBody').innerHTML = `
        <div class="target-form-hint">特种 AIS 设备仿真：气象站广播气象数据、搜救飞机发送位置报告、基站发布时间报告、SART 发送安全告警、航线广播发送区域信息。位置以本船初始位置为基准。</div>
        <div class="target-form-section">
            <div class="target-form-section-title"><span class="dot"></span>基本信息</div>
            <div class="target-form-grid">
                <div class="target-form-field">
                    <label>设备类型</label>
                    <select id="tf_target_type">${targetTypeOpts}</select>
                </div>
                <div class="target-form-field">
                    <label>MMSI</label>
                    <input type="number" id="tf_mmsi" value="${t.mmsi ?? 100000001}" step="1">
                </div>
                <div class="target-form-field">
                    <label>名称</label>
                    <input type="text" id="tf_name" value="${escapeHtml(t.name ?? '')}" maxlength="20">
                </div>
            </div>
        </div>
        <div class="target-form-section">
            <div class="target-form-section-title"><span class="dot"></span>位置（相对本船初始位置）</div>
            <div class="target-form-grid-3">
                <div class="target-form-field">
                    <label>相对方位 (°)</label>
                    <input type="number" id="tf_bearing" value="${t.bearing ?? 0.0}" step="0.1" min="0" max="360">
                </div>
                <div class="target-form-field">
                    <label>距离 (nm)</label>
                    <input type="number" id="tf_distance" value="${t.distance ?? 3.0}" step="0.1" min="0">
                </div>
                <div class="target-form-field">
                    <label>航速 (kn)</label>
                    <input type="number" id="tf_speed" value="${t.speed ?? 0.0}" step="0.1" min="0">
                </div>
                <div class="target-form-field">
                    <label>航向 (°)</label>
                    <input type="number" id="tf_heading" value="${t.heading ?? 0.0}" step="0.1" min="0" max="360">
                </div>
            </div>
        </div>
        <div class="target-form-section">
            <div class="target-form-section-title"><span class="dot"></span>气象/环境参数</div>
            <div class="target-form-grid">
                <div class="target-form-field">
                    <label>高度 (m)</label>
                    <input type="number" id="tf_altitude" value="${t.altitude ?? 1000}" step="1" min="0">
                </div>
                <div class="target-form-field">
                    <label>风速 (m/s)</label>
                    <input type="number" id="tf_wind_speed" value="${t.wind_speed ?? 15}" step="0.1" min="0">
                </div>
                <div class="target-form-field">
                    <label>风向 (°)</label>
                    <input type="number" id="tf_wind_direction" value="${t.wind_direction ?? 180}" step="0.1" min="0" max="360">
                </div>
                <div class="target-form-field">
                    <label>气压 (hPa)</label>
                    <input type="number" id="tf_pressure" value="${t.pressure ?? 1013}" step="0.1">
                </div>
                <div class="target-form-field">
                    <label>温度 (°C)</label>
                    <input type="number" id="tf_temperature" value="${t.temperature ?? 22}" step="0.1">
                </div>
                <div class="target-form-field">
                    <label>湿度 (%)</label>
                    <input type="number" id="tf_humidity" value="${t.humidity ?? 65}" step="0.1" min="0" max="100">
                </div>
                <div class="target-form-field">
                    <label>能见度 (nm)</label>
                    <input type="number" id="tf_visibility" value="${t.visibility ?? 10}" step="0.1" min="0">
                </div>
            </div>
        </div>
        <div class="target-form-section">
            <div class="target-form-section-title"><span class="dot"></span>VDM 报文配置</div>
            <div class="target-form-grid">
                <div class="target-form-field">
                    <label>分片数</label>
                    <select id="tf_fragment_count">${fragmentOpts}</select>
                </div>
            </div>
        </div>
        <div id="targetFormError" style="display:none;"></div>
        <div class="target-form-actions">
            <button type="button" class="btn btn-primary" id="btnSaveTargetForm">保存</button>
            <button type="button" class="btn btn-secondary" id="btnCancelTargetForm">取消</button>
        </div>
    `;

    $('btnSaveTargetForm').addEventListener('click', () => saveTargetForm('special'));
    $('btnCancelTargetForm').addEventListener('click', closeTargetForm);
}

async function saveTargetForm(type) {
    const errDiv = $('targetFormError');
    const errors = [];
    const mmsi = parseInt($('tf_mmsi').value);
    const bearing = parseFloat($('tf_bearing').value);
    const distance = parseFloat($('tf_distance').value);

    if (!mmsi || mmsi < 1) errors.push('MMSI 必须为正整数');
    if (isNaN(bearing) || bearing < 0 || bearing > 360) errors.push('方位范围 0-360');
    if (isNaN(distance) || distance < 0) errors.push('距离无效');

    let data = {};
    let apiUrl = '';
    let typeName = '';

    if (type === 'ais') {
        const msgTypes = getCheckedValues('tf_msg_types');
        if (msgTypes.length === 0) errors.push('至少选择一种报文类型');
        data = {
            mmsi,
            ship_name: $('tf_ship_name').value.trim(),
            callsign: $('tf_callsign').value.trim(),
            imo_number: parseInt($('tf_imo_number').value),
            ship_type: parseInt($('tf_ship_type').value),
            destination: $('tf_destination').value.trim(),
            draught: parseFloat($('tf_draught').value),
            speed: parseFloat($('tf_speed').value),
            heading: parseFloat($('tf_heading').value),
            bearing,
            distance,
            msg_types: msgTypes.join(','),
            fragment_count: parseInt($('tf_fragment_count').value),
        };
        if (isNaN(data.speed) || data.speed < 0) errors.push('航速无效');
        apiUrl = '/api/targets/ais';
        typeName = 'AIS 目标';
    } else if (type === 'aton') {
        const msgTypes = getCheckedValues('tf_msg_types');
        if (msgTypes.length === 0) errors.push('至少选择一种报文类型');
        data = {
            mmsi,
            name: $('tf_name').value.trim(),
            aton_type: parseInt($('tf_aton_type').value),
            bearing,
            distance,
            msg_types: msgTypes.join(','),
            fragment_count: parseInt($('tf_fragment_count').value),
        };
        apiUrl = '/api/targets/aton';
        typeName = '航标目标';
    } else if (type === 'special') {
        data = {
            target_type: $('tf_target_type').value,
            mmsi,
            name: $('tf_name').value.trim(),
            bearing,
            distance,
            speed: parseFloat($('tf_speed').value),
            heading: parseFloat($('tf_heading').value),
            altitude: parseFloat($('tf_altitude').value),
            wind_speed: parseFloat($('tf_wind_speed').value),
            wind_direction: parseFloat($('tf_wind_direction').value),
            pressure: parseFloat($('tf_pressure').value),
            temperature: parseFloat($('tf_temperature').value),
            humidity: parseFloat($('tf_humidity').value),
            visibility: parseFloat($('tf_visibility').value),
            fragment_count: parseInt($('tf_fragment_count').value),
        };
        apiUrl = '/api/targets/special';
        typeName = '特种目标';
    }

    if (errors.length > 0) {
        errDiv.style.display = 'block';
        errDiv.className = 'target-form-error';
        errDiv.innerHTML = errors.map(e => `<div>${escapeHtml(e)}</div>`).join('');
        return;
    }
    errDiv.style.display = 'none';

    try {
        if (targetFormMode === 'edit') {
            await api(`${apiUrl}/${targetEditId}`, 'PUT', data);
            showToast('success', `${typeName}已更新`);
        } else {
            await api(apiUrl, 'POST', data);
            showToast('success', `${typeName}已新增`);
        }
        closeTargetForm();
        await loadTargets();
    } catch (e) {
        errDiv.style.display = 'block';
        errDiv.className = 'target-form-error';
        errDiv.textContent = e.message;
    }
}

function closeTargetForm() {
    $('targetFormOverlay').style.display = 'none';
    $('targetFormBody').innerHTML = '';
}

window.editTarget = function(type, id) {
    let targets;
    if (type === 'ais') targets = aisTargets;
    else if (type === 'aton') targets = atonTargets;
    else if (type === 'special') targets = specialTargets;
    const target = targets.find(t => t.id === id);
    if (target) showTargetForm(type, target);
};

window.deleteTarget = async function(type, id) {
    if (!confirm('确定删除此目标?')) return;
    try {
        await api(`/api/targets/${type}/${id}`, 'DELETE');
        showToast('success', '目标已删除');
        await loadTargets();
    } catch (e) {
        showToast('error', `删除失败: ${e.message}`);
    }
};

$('btnNewAisTarget').addEventListener('click', () => showTargetForm('ais'));
$('btnNewAtonTarget').addEventListener('click', () => showTargetForm('aton'));
$('btnNewSpecialTarget').addEventListener('click', () => showTargetForm('special'));
$('btnCloseTargetForm').addEventListener('click', closeTargetForm);
$('targetFormOverlay').addEventListener('click', (e) => {
    if (e.target === $('targetFormOverlay')) closeTargetForm();
});

// ---- Interface List ----
function renderInterfaceList() {
    const list = $('interfaceList');
    const empty = $('ifaceEmpty');

    // Remove all cards but keep empty element
    list.querySelectorAll('.interface-card').forEach(c => c.remove());

    if (interfaces.length === 0) {
        if (empty) empty.style.display = 'flex';
        return;
    }
    if (empty) empty.style.display = 'none';

    interfaces.forEach(iface => {
        const card = document.createElement('div');
        card.className = 'interface-card';
        if (iface.id === selectedIfaceId) card.classList.add('active');

        const status = iface.status || 'disconnected';
        const protoCls = iface.protocol === 'TCP' ? 'tcp' : 'udp';
        const formatTags = (iface.formats || []).map(f =>
            `<span class="format-tag">${escapeHtml(f)}</span>`
        ).join('');

        card.innerHTML = `
            <div class="iface-card-top">
                <span class="iface-card-name">${escapeHtml(iface.name)}</span>
                <span class="conn-indicator ${status}"></span>
            </div>
            <div class="iface-card-mid">
                <span class="protocol-badge ${protoCls}">${escapeHtml(iface.protocol)}</span>
                <span class="iface-card-addr">${escapeHtml(iface.ip)}:${escapeHtml(iface.port)}</span>
            </div>
            <div class="iface-card-formats">${formatTags}</div>
            <button class="icon-btn iface-card-delete" title="删除">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/>
                </svg>
            </button>
        `;

        card.addEventListener('click', () => selectInterface(iface.id));
        card.querySelector('.iface-card-delete').addEventListener('click', async (e) => {
            e.stopPropagation();
            if (confirm(`确定删除接口「${iface.name}」?`)) {
                try {
                    await api(`/api/interfaces/${iface.id}`, 'DELETE');
                    showToast('success', `接口「${iface.name}」已删除`);
                } catch (err) {
                    showToast('error', `删除失败: ${err.message}`);
                }
            }
        });

        list.appendChild(card);
    });
}

function selectInterface(id) {
    selectedIfaceId = id;
    logIfaceFilter = id;
    renderInterfaceList();

    const iface = interfaces.find(i => i.id === id);
    if (iface) {
        renderDetailView(iface);
        switchView('detail');
        updateLogFilterUI();
    }
}

// ---- View Switching ----
function switchView(mode) {
    viewMode = mode;
    document.querySelectorAll('.view-state').forEach(v => v.classList.remove('active'));
    if (mode === 'empty') {
        $('viewEmpty').classList.add('active');
    } else if (mode === 'detail') {
        $('viewDetail').classList.add('active');
    } else if (mode === 'form') {
        $('viewForm').classList.add('active');
    }
}

// ---- Detail View ----
function renderDetailView(iface) {
    const statusInfo = STATUS_LABELS[iface.status] || STATUS_LABELS.disconnected;
    const formatTags = (iface.formats || []).map(f =>
        `<span class="format-tag" style="color:var(--accent-cyan);border-color:var(--border-light)">${escapeHtml(f)}</span>`
    ).join('');

    const interruptHtml = (iface.interruption_logs || []).map(log => `
        <div class="interrupt-item">
            <span class="interrupt-time">${escapeHtml(log.time)}</span>
            <span class="interrupt-reason">${escapeHtml(log.reason)}</span>
        </div>
    `).join('') || '<div class="interrupt-reason" style="padding:6px 10px;">无中断记录</div>';

    const connBtn = iface.status === 'connected' || iface.status === 'connecting'
        ? `<button class="btn btn-secondary" onclick="disconnectIface('${iface.id}')">断开</button>`
        : `<button class="btn btn-primary" onclick="connectIface('${iface.id}')">连接</button>`;

    $('viewDetail').innerHTML = `
        <div class="detail-header">
            <span class="detail-title">${escapeHtml(iface.name)}</span>
            <div class="detail-header-right">
                <span class="status-badge ${statusInfo.cls}">
                    <span class="dot"></span>${statusInfo.text}
                </span>
                <button class="icon-btn" onclick="closeDetail()" title="关闭">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M18 6L6 18M6 6l12 12"/>
                    </svg>
                </button>
            </div>
        </div>

        <div class="detail-info-grid">
            <div class="detail-info-item">
                <label>通信协议</label>
                <span class="value">${escapeHtml(iface.protocol)}</span>
            </div>
            <div class="detail-info-item">
                <label>本机地址</label>
                <span class="value">${escapeHtml(iface.ip)}:${escapeHtml(iface.port)}</span>
            </div>
        </div>

        <div class="detail-formats">
            <div class="detail-formats-title">数据格式 (${(iface.formats || []).length})</div>
            <div class="detail-format-list">${formatTags}</div>
        </div>

        <div class="detail-stats">
            <div class="stat-card">
                <div class="stat-label">当前状态</div>
                <div class="stat-value" style="font-size:16px;">${statusInfo.text}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">总连接次数</div>
                <div class="stat-value">${iface.total_connections}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">中断次数</div>
                <div class="stat-value" style="color:var(--accent-red)">${iface.interruptions}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">发送数据条数</div>
                <div class="stat-value" style="color:var(--accent-amber)">${iface.data_count}</div>
            </div>
        </div>

        <div class="detail-meta">
            <div class="detail-meta-item"><label>创建时间</label><span class="value">${escapeHtml(iface.created_at || '—')}</span></div>
            <div class="detail-meta-item"><label>接口 ID</label><span class="value">${escapeHtml(iface.id)}</span></div>
            <div class="detail-meta-item"><label>最近连接</label><span class="value">${escapeHtml(iface.last_connected_at || '—')}</span></div>
            <div class="detail-meta-item"><label>最近断开</label><span class="value">${escapeHtml(iface.last_disconnected_at || '—')}</span></div>
        </div>

        <div class="detail-interrupts">
            <div class="detail-interrupts-title">中断日志 (${(iface.interruption_logs || []).length})</div>
            <div class="interrupt-list">${interruptHtml}</div>
        </div>

        <div class="detail-actions">
            ${connBtn}
            <button class="btn btn-secondary" onclick="editIface('${iface.id}')">编辑</button>
            <button class="btn btn-danger" onclick="deleteIfaceFromDetail('${iface.id}')">删除</button>
        </div>
    `;
}

window.closeDetail = function() {
    selectedIfaceId = null;
    logIfaceFilter = null;
    renderInterfaceList();
    switchView('empty');
    updateLogFilterUI();
};

window.connectIface = async function(id) {
    try {
        await api(`/api/interfaces/${id}/connect`, 'POST');
        showToast('success', '接口连接中...');
    } catch (e) {
        showToast('error', `连接失败: ${e.message}`);
    }
};

window.disconnectIface = async function(id) {
    try {
        await api(`/api/interfaces/${id}/disconnect`, 'POST');
        showToast('info', '接口已断开');
    } catch (e) {
        showToast('error', `断开失败: ${e.message}`);
    }
};

window.editIface = function(id) {
    const iface = interfaces.find(i => i.id === id);
    if (iface) {
        isEditing = true;
        renderFormView(iface);
        switchView('form');
    }
};

window.deleteIfaceFromDetail = async function(id) {
    const iface = interfaces.find(i => i.id === id);
    if (!iface) return;
    if (confirm(`确定删除接口「${iface.name}」?`)) {
        try {
            await api(`/api/interfaces/${id}`, 'DELETE');
            selectedIfaceId = null;
            logIfaceFilter = null;
            switchView('empty');
            updateLogFilterUI();
            showToast('success', `接口「${iface.name}」已删除`);
        } catch (e) {
            showToast('error', `删除失败: ${e.message}`);
        }
    }
};

// ---- Form View ----
function renderFormView(iface = null) {
    const isEdit = !!iface;
    const name = isEdit ? iface.name : '';
    const protocol = isEdit ? iface.protocol : 'TCP';
    const ip = isEdit ? iface.ip : (localIps.length > 1 ? localIps[1] : localIps[0]);
    const port = isEdit ? iface.port : 10110;
    const selectedFormats = isEdit ? iface.formats : [];

    const formatChips = nmeaFormats.map(f => {
        const checked = selectedFormats.includes(f.code);
        return `<label class="format-chip ${checked ? 'selected' : ''}" data-code="${f.code}">
            <input type="checkbox" value="${f.code}" ${checked ? 'checked' : ''}>
            ${escapeHtml(f.code)} <small style="opacity:0.6">${escapeHtml(f.desc)}</small>
        </label>`;
    }).join('');

    const ipOptions = localIps.map(ipAddr => {
        const label = ipAddr === '0.0.0.0' ? '所有接口 (0.0.0.0)' : ipAddr;
        return `<option value="${escapeHtml(ipAddr)}" ${ipAddr === ip ? 'selected' : ''}>${escapeHtml(label)}</option>`;
    }).join('');

    $('viewForm').innerHTML = `
        <div class="form-header">
            <span class="form-title">${isEdit ? '编辑接口' : '新建接口'}</span>
        </div>
        <form class="iface-form" id="ifaceForm" onsubmit="return false">
            <div class="iface-form-field">
                <label>接口名称</label>
                <input type="text" id="f_name" value="${escapeHtml(name)}" maxlength="32" placeholder="输入接口名称">
            </div>
            <div class="iface-form-field">
                <label>通信协议</label>
                <div class="protocol-toggle">
                    <input type="radio" name="protocol" id="proto_tcp" value="TCP" ${protocol === 'TCP' ? 'checked' : ''}>
                    <label for="proto_tcp">TCP</label>
                    <input type="radio" name="protocol" id="proto_udp" value="UDP" ${protocol === 'UDP' ? 'checked' : ''}>
                    <label for="proto_udp">UDP</label>
                </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 120px;gap:12px;">
                <div class="iface-form-field">
                    <label>本机 IP 地址</label>
                    <select id="f_ip" class="iface-select">${ipOptions}</select>
                </div>
                <div class="iface-form-field">
                    <label>端口</label>
                    <input type="number" id="f_port" value="${port}" min="1" max="65535">
                </div>
            </div>
            <div class="iface-form-field">
                <label>数据格式 (NMEA 0183)</label>
                <div class="formats-select" id="formatsSelect">${formatChips}</div>
            </div>
            <div id="formError" style="display:none;"></div>
            <div class="form-actions">
                <button type="button" class="btn btn-primary" id="btnSaveIface">${isEdit ? '保存修改' : '创建并连接'}</button>
                <button type="button" class="btn btn-secondary" id="btnCancelIface">取消</button>
            </div>
        </form>
    `;

    // Format chip toggle
    document.querySelectorAll('.format-chip').forEach(chip => {
        const input = chip.querySelector('input');
        chip.addEventListener('click', (e) => {
            e.preventDefault();
            input.checked = !input.checked;
            chip.classList.toggle('selected', input.checked);
        });
    });

    // Save
    $('btnSaveIface').addEventListener('click', saveInterfaceForm);
    $('btnCancelIface').addEventListener('click', () => {
        if (isEdit && iface) {
            renderDetailView(iface);
            switchView('detail');
        } else {
            switchView('empty');
        }
    });
}

function saveInterfaceForm() {
    const name = $('f_name').value.trim();
    const protocol = document.querySelector('input[name="protocol"]:checked').value;
    const ip = $('f_ip').value;
    const port = parseInt($('f_port').value);
    const formats = Array.from(document.querySelectorAll('#formatsSelect input:checked')).map(i => i.value);

    const errDiv = $('formError');
    const errors = [];
    if (!name) errors.push('接口名称不能为空');
    if (!ip) errors.push('IP地址不能为空');
    if (!port || port < 1 || port > 65535) errors.push('端口范围 1-65535');
    if (formats.length === 0) errors.push('至少选择一种数据格式');

    if (errors.length > 0) {
        errDiv.style.display = 'block';
        errDiv.className = 'form-error';
        errDiv.innerHTML = errors.map(e => `<div>${escapeHtml(e)}</div>`).join('');
        return;
    }
    errDiv.style.display = 'none';

    const payload = { name, protocol, ip, port, formats };

    if (isEditing && selectedIfaceId) {
        api(`/api/interfaces/${selectedIfaceId}`, 'PUT', payload)
            .then(data => {
                showToast('success', '接口配置已更新');
                renderDetailView(data.data);
                switchView('detail');
            })
            .catch(e => {
                errDiv.style.display = 'block';
                errDiv.className = 'form-error';
                errDiv.textContent = e.message;
            });
    } else {
        api('/api/interfaces', 'POST', payload)
            .then(data => {
                showToast('success', `接口「${name}」已创建并自动连接`);
                selectedIfaceId = data.data.id;
                logIfaceFilter = data.data.id;
                renderDetailView(data.data);
                switchView('detail');
                updateLogFilterUI();
            })
            .catch(e => {
                errDiv.style.display = 'block';
                errDiv.className = 'form-error';
                errDiv.textContent = e.message;
            });
    }
}

// ---- New Interface Button ----
$('btnNewIface').addEventListener('click', () => {
    isEditing = false;
    renderFormView(null);
    switchView('form');
});

// ---- Sidebar Collapse ----
$('btnCollapse').addEventListener('click', () => {
    sidebarCollapsed = !sidebarCollapsed;
    $('ifaceLayout').classList.toggle('collapsed', sidebarCollapsed);
    const svg = $('btnCollapse').querySelector('svg path');
    if (sidebarCollapsed) {
        svg.setAttribute('d', 'M9 18l6-6-6-6');
    } else {
        svg.setAttribute('d', 'M15 18l-6-6 6-6');
    }
});

// ---- Log Management ----
function addLogEntry(entry) {
    logEntries.push(entry);
    if (logEntries.length > 500) {
        logEntries = logEntries.slice(-500);
    }
    renderLogEntry(entry);
    updateLogCount();
}

function shouldShowLog(entry) {
    if (activeLogFilter !== 'all' && entry.level !== activeLogFilter) return false;
    if (logIfaceFilter && entry.interface_id !== logIfaceFilter) return false;
    return true;
}

function renderLogEntry(entry) {
    if (!shouldShowLog(entry)) return;
    const container = $('logContent');
    const div = document.createElement('div');
    div.className = `log-entry ${entry.level}`;
    div.dataset.ifaceId = entry.interface_id || '';

    const isNmea = entry.nmea_raw && entry.nmea_raw.startsWith('$');
    const msgHtml = isNmea ? formatNmea(entry.nmea_raw) : escapeHtml(entry.message);

    div.innerHTML = `
        <span class="log-time">${escapeHtml(entry.timestamp)}</span>
        <span class="log-level">${escapeHtml(entry.level)}</span>
        <span class="log-message">${msgHtml}</span>
    `;
    container.appendChild(div);

    // Auto scroll
    container.scrollTop = container.scrollHeight;

    // Limit DOM entries
    while (container.children.length > 500) {
        container.removeChild(container.firstChild);
    }
}

function rerenderAllLogs() {
    const container = $('logContent');
    container.innerHTML = '';
    logEntries.forEach(entry => renderLogEntry(entry));
    container.scrollTop = container.scrollHeight;
}

function updateLogCount() {
    const count = logEntries.filter(e => shouldShowLog(e)).length;
    $('logCount').textContent = `${count} 条`;
}

function updateLogFilterUI() {
    const tag = $('logIfaceTag');
    const btnAll = $('btnAllIface');
    if (logIfaceFilter) {
        const iface = interfaces.find(i => i.id === logIfaceFilter);
        if (iface) {
            tag.style.display = 'inline-block';
            tag.textContent = iface.name;
            btnAll.style.display = 'inline-block';
        }
    } else {
        tag.style.display = 'none';
        btnAll.style.display = 'none';
    }
    updateLogCount();
}

// Log filter buttons
document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        activeLogFilter = btn.dataset.level;
        rerenderAllLogs();
        updateLogCount();
    });
});

$('btnAllIface').addEventListener('click', () => {
    logIfaceFilter = null;
    updateLogFilterUI();
    rerenderAllLogs();
});

$('btnClearLog').addEventListener('click', () => {
    logEntries = [];
    $('logContent').innerHTML = '';
    updateLogCount();
    showToast('info', '日志已清空');
});

// ---- Initialization ----
async function init() {
    updateClock();
    setInterval(updateClock, 1000);

    // Restore last active tab
    const savedTab = localStorage.getItem('nmea_active_tab');
    if (savedTab === 'iface') {
        switchTab('iface');
    } else if (savedTab === 'targets') {
        switchTab('targets');
    }

    initSocket();

    // Load NMEA formats
    try {
        const fmtData = await api('/api/nmea-formats');
        nmeaFormats = fmtData;
    } catch (e) {
        console.error('加载NMEA格式失败:', e);
    }

    // Load local IPs
    try {
        const ips = await api('/api/local-ips');
        if (Array.isArray(ips) && ips.length > 0) {
            localIps = ips;
        }
    } catch (e) {
        console.error('加载本机IP失败:', e);
    }

    // Load saved ship config from database
    try {
        const saved = await api('/api/ship/saved-config');
        if (saved) {
            const fields = ['start_latitude', 'start_longitude', 'heading', 'speed',
                'water_depth', 'depth_variation', 'wind_direction', 'wind_speed',
                'wind_dir_variation', 'wind_speed_variation', 'temperature', 'humidity',
                'temp_variation', 'humidity_variation', 'pressure', 'mmsi',
                'satellites', 'hdop', 'altitude', 'water_speed',
                'ship_name', 'callsign', 'imo_number', 'ship_type_ais',
                'destination', 'draught', 'vdo_fragment_count',
                'ais_pos_dev', 'ais_speed_dev', 'ais_heading_dev',
                'radar_pos_dev', 'radar_bearing_dev', 'radar_speed_dev', 'radar_heading_dev'];
            fields.forEach(f => {
                const el = $('cfg_' + f);
                if (el && saved[f] != null) el.value = saved[f];
            });
            // Handle VDO msg_types checkboxes
            const savedVdoTypes = String(saved.vdo_msg_types || '1').split(',').filter(Boolean);
            document.querySelectorAll('#cfg_vdo_msg_types input[type="checkbox"]').forEach(cb => {
                cb.checked = savedVdoTypes.includes(cb.value);
            });
        }
    } catch (e) {
        console.error('加载保存的船舶配置失败:', e);
    }

    // Load ship state
    try {
        const state = await api('/api/ship/state');
        updateShipDisplay(state);
    } catch (e) {
        console.error('加载船舶状态失败:', e);
    }

    // Load interfaces
    try {
        const list = await api('/api/interfaces');
        interfaces = list;
        renderInterfaceList();
    } catch (e) {
        console.error('加载接口列表失败:', e);
    }
}

init();
