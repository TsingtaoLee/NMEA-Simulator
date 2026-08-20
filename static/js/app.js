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
        ais_target_count: parseInt($('cfg_ais_target_count').value),
        mmsi: parseInt($('cfg_mmsi').value),
        satellites: parseInt($('cfg_satellites').value),
        hdop: parseFloat($('cfg_hdop').value),
        altitude: parseFloat($('cfg_altitude').value),
        water_speed: parseFloat($('cfg_water_speed').value),
        ais_fragment_enabled: 0,
        ais_fragment_mode: parseInt($('cfg_ais_fragment_mode').value),
        ais_fragment_type: parseInt($('cfg_ais_fragment_type').value),
        ais_fragment_count: parseInt($('cfg_ais_fragment_count').value),
        aton_target_count: parseInt($('cfg_aton_target_count').value),
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
                'temp_variation', 'humidity_variation', 'pressure', 'ais_target_count', 'mmsi',
                'satellites', 'hdop', 'altitude', 'water_speed',
                'ais_fragment_mode', 'ais_fragment_type', 'ais_fragment_count',
                'aton_target_count'];
            fields.forEach(f => {
                const el = $('cfg_' + f);
                if (el && saved[f] != null) el.value = saved[f];
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
