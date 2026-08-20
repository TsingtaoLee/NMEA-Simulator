import re
import math
from collections import defaultdict

with open('nmea_output.txt', 'r', encoding='utf-8') as f:
    lines = [l.strip() for l in f if l.strip()]

# === 1. Checksum verification ===
print("=" * 60)
print("1. CHECKSUM VERIFICATION")
print("=" * 60)
cs_pass = 0
cs_fail = 0
for line in lines:
    m = re.match(r'\$(.+)\*([0-9A-F]{2})$', line)
    if not m:
        cs_fail += 1
        continue
    body, cs = m.group(1), m.group(2)
    calc = 0
    for ch in body:
        calc ^= ord(ch)
    calc_hex = f"{calc:02X}"
    if calc_hex == cs:
        cs_pass += 1
    else:
        cs_fail += 1
        if cs_fail <= 3:
            print(f"  FAIL: {line[:60]} calc={calc_hex} actual={cs}")
print(f"  Result: {cs_pass} pass, {cs_fail} fail out of {len(lines)} sentences")

# === 2. Parse each sentence type ===
groups = defaultdict(list)
for line in lines:
    m = re.match(r'\$([A-Z]{2})([A-Z]{3}),', line)
    if m:
        groups[m.group(2)].append(line)

print("\n" + "=" * 60)
print("2. FORMAT & CONTENT ANALYSIS BY TYPE")
print("=" * 60)

# Helper: parse NMEA fields
def parse_fields(line):
    m = re.match(r'\$(.+)\*([0-9A-F]{2})$', line)
    if not m:
        return None, None
    body = m.group(1)
    parts = body.split(',')
    return parts, m.group(2)

# Helper: parse lat/lon from NMEA format
def parse_lat(lat_str, hemi):
    deg = int(lat_str[:2])
    minute = float(lat_str[2:])
    val = deg + minute / 60
    return -val if hemi == 'S' else val

def parse_lon(lon_str, hemi):
    deg = int(lon_str[:3])
    minute = float(lon_str[3:])
    val = deg + minute / 60
    return -val if hemi == 'W' else val

# --- RMC ---
print("\n--- RMC (Recommended Minimum) ---")
rmc_data = []
for line in groups.get('RMC', []):
    parts, _ = parse_fields(line)
    if parts and parts[0] == 'GPRMC':
        time_str = parts[1]
        status = parts[2]
        lat = parse_lat(parts[3], parts[4])
        lon = parse_lon(parts[5], parts[6])
        sog = float(parts[7])
        cog = float(parts[8])
        date = parts[9]
        mode = parts[12] if len(parts) > 12 else ''
        rmc_data.append({'time': time_str, 'lat': lat, 'lon': lon, 'sog': sog, 'cog': cog, 'status': status, 'mode': mode})
if rmc_data:
    print(f"  Count: {len(rmc_data)}")
    print(f"  Time range: {rmc_data[0]['time']} -> {rmc_data[-1]['time']}")
    print(f"  Status: {rmc_data[0]['status']} (expect A)")
    print(f"  Mode: {rmc_data[0]['mode']} (expect A)")
    print(f"  Lat range: {rmc_data[0]['lat']:.6f} -> {rmc_data[-1]['lat']:.6f} (should change)")
    print(f"  Lon range: {rmc_data[0]['lon']:.6f} -> {rmc_data[-1]['lon']:.6f} (should change)")
    print(f"  SOG: {rmc_data[0]['sog']} (config 12.0)")
    print(f"  COG: {rmc_data[0]['cog']} (config 90.0)")
    lat_changed = abs(rmc_data[-1]['lat'] - rmc_data[0]['lat']) > 0.00001
    lon_changed = abs(rmc_data[-1]['lon'] - rmc_data[0]['lon']) > 0.00001
    print(f"  Position changed: lat={lat_changed}, lon={lon_changed}")

# --- GGA ---
print("\n--- GGA (GPS Fix) ---")
gga_data = []
for line in groups.get('GGA', []):
    parts, _ = parse_fields(line)
    if parts and parts[0] == 'GPGGA':
        lat = parse_lat(parts[2], parts[3])
        lon = parse_lon(parts[4], parts[5])
        fix = parts[6]
        sats = int(parts[7])
        hdop = float(parts[8])
        alt = float(parts[9])
        gga_data.append({'lat': lat, 'lon': lon, 'fix': fix, 'sats': sats, 'hdop': hdop, 'alt': alt})
if gga_data:
    print(f"  Count: {len(gga_data)}")
    print(f"  Fix quality: {gga_data[0]['fix']} (expect 1)")
    print(f"  Satellites: {gga_data[0]['sats']} (config 10)")
    print(f"  HDOP: {gga_data[0]['hdop']} (config 0.8)")
    print(f"  Altitude: {gga_data[0]['alt']} (config 35.0)")
    print(f"  Lat[0] vs Lat[-1]: {gga_data[0]['lat']:.6f} vs {gga_data[-1]['lat']:.6f}")

# --- GLL ---
print("\n--- GLL (Geographic Position) ---")
gll_data = []
for line in groups.get('GLL', []):
    parts, _ = parse_fields(line)
    if parts and parts[0] == 'GPGLL':
        lat = parse_lat(parts[1], parts[2])
        lon = parse_lon(parts[3], parts[4])
        gll_data.append({'lat': lat, 'lon': lon})
if gll_data:
    print(f"  Count: {len(gll_data)}")
    print(f"  Lat[0]: {gll_data[0]['lat']:.6f} (should match RMC/GGA)")
    print(f"  Lon[0]: {gll_data[0]['lon']:.6f}")

# --- ZDA ---
print("\n--- ZDA (Time & Date) ---")
zda_data = []
for line in groups.get('ZDA', []):
    parts, _ = parse_fields(line)
    if parts and parts[0] == 'GPZDA':
        zda_data.append({'time': parts[1], 'day': parts[2], 'month': parts[3], 'year': parts[4]})
if zda_data:
    print(f"  Count: {len(zda_data)}")
    print(f"  Date: {zda_data[0]['day']}/{zda_data[0]['month']}/{zda_data[0]['year']}")
    print(f"  Time range: {zda_data[0]['time']} -> {zda_data[-1]['time']}")

# --- VTG ---
print("\n--- VTG (Track Made Good) ---")
vtg_data = []
for line in groups.get('VTG', []):
    parts, _ = parse_fields(line)
    if parts and parts[0] == 'GPVTG':
        cog_t = float(parts[1])
        sog_kn = float(parts[5])
        sog_kmh = float(parts[7])
        vtg_data.append({'cog': cog_t, 'sog_kn': sog_kn, 'sog_kmh': sog_kmh})
if vtg_data:
    print(f"  Count: {len(vtg_data)}")
    print(f"  COG: {vtg_data[0]['cog']} (should match RMC cog)")
    print(f"  SOG kn: {vtg_data[0]['sog_kn']} (should match RMC sog)")
    print(f"  SOG kmh: {vtg_data[0]['sog_kmh']} (expect {vtg_data[0]['sog_kn']*1.852:.1f})")

# --- VBW ---
print("\n--- VBW (Speed Through Water) ---")
vbw_data = []
for line in groups.get('VBW', []):
    parts, _ = parse_fields(line)
    if parts and parts[0] == 'VDVBW':
        ws = float(parts[1])
        gs = float(parts[4])
        vbw_data.append({'water_speed': ws, 'ground_speed': gs})
if vbw_data:
    print(f"  Count: {len(vbw_data)}")
    print(f"  Water speed: {vbw_data[0]['water_speed']} (should match SOG when water_speed=0)")
    print(f"  Ground speed: {vbw_data[0]['ground_speed']} (should match SOG)")

# --- MWV ---
print("\n--- MWV (Wind) ---")
mwv_data = []
for line in groups.get('MWV', []):
    parts, _ = parse_fields(line)
    if parts and parts[0] == 'WIMWV':
        wd = float(parts[1])
        ws = float(parts[3])
        mwv_data.append({'wind_dir': wd, 'wind_speed': ws})
if mwv_data:
    print(f"  Count: {len(mwv_data)}")
    print(f"  Wind dir range: {min(d['wind_dir'] for d in mwv_data):.1f} - {max(d['wind_dir'] for d in mwv_data):.1f} (config 180 +/-30)")
    print(f"  Wind speed range: {min(d['wind_speed'] for d in mwv_data):.1f} - {max(d['wind_speed'] for d in mwv_data):.1f} (config 10 +/-2)")
    dir_changed = abs(mwv_data[-1]['wind_dir'] - mwv_data[0]['wind_dir']) > 0.01
    spd_changed = abs(mwv_data[-1]['wind_speed'] - mwv_data[0]['wind_speed']) > 0.01
    print(f"  Wind varied: dir={dir_changed}, speed={spd_changed}")

# --- DPT ---
print("\n--- DPT (Depth) ---")
dpt_data = []
for line in groups.get('DPT', []):
    parts, _ = parse_fields(line)
    if parts and parts[0] == 'SDDPT':
        depth = float(parts[1])
        dpt_data.append({'depth': depth})
if dpt_data:
    print(f"  Count: {len(dpt_data)}")
    print(f"  Depth range: {min(d['depth'] for d in dpt_data):.1f} - {max(d['depth'] for d in dpt_data):.1f} (config 50 +/-5)")
    print(f"  Depth[0]: {dpt_data[0]['depth']}, Depth[-1]: {dpt_data[-1]['depth']}")

# --- DBT ---
print("\n--- DBT (Depth Below Transducer) ---")
dbt_data = []
for line in groups.get('DBT', []):
    parts, _ = parse_fields(line)
    if parts and parts[0] == 'SDDBT':
        d_ft = float(parts[1])
        d_m = float(parts[3])
        d_fa = float(parts[5])
        dbt_data.append({'d_ft': d_ft, 'd_m': d_m, 'd_fa': d_fa})
if dbt_data:
    print(f"  Count: {len(dbt_data)}")
    print(f"  Depth m: {dbt_data[0]['d_m']:.1f} (should match DPT)")
    print(f"  Depth ft: {dbt_data[0]['d_ft']:.1f} (expect {dbt_data[0]['d_m']*3.2808:.1f})")
    print(f"  Depth fa: {dbt_data[0]['d_fa']:.1f} (expect {dbt_data[0]['d_m']*0.5468:.1f})")

# --- MDA ---
print("\n--- MDA (Meteorological) ---")
mda_data = []
for line in groups.get('MDA', []):
    parts, _ = parse_fields(line)
    if parts and parts[0] == 'WIMDA':
        p_in = float(parts[1])
        p_bar = float(parts[3])
        temp = float(parts[5])
        hum = float(parts[9])
        dew = float(parts[11])
        wd = float(parts[13])
        ws_kn = float(parts[17])
        ws_ms = float(parts[19])
        mda_data.append({'p_in': p_in, 'p_bar': p_bar, 'temp': temp, 'hum': hum, 'dew': dew, 'wd': wd, 'ws_kn': ws_kn, 'ws_ms': ws_ms})
if mda_data:
    print(f"  Count: {len(mda_data)}")
    print(f"  Pressure inHg: {mda_data[0]['p_in']} (expect {1013*0.02953:.2f})")
    print(f"  Pressure bar: {mda_data[0]['p_bar']} (expect {1013/1000:.3f})")
    print(f"  Temp: {mda_data[0]['temp']} (config 22 +/-2)")
    print(f"  Humidity: {mda_data[0]['hum']} (config 65 +/-5)")
    print(f"  Wind dir: {mda_data[0]['wd']} (should match MWV)")
    print(f"  Wind speed kn: {mda_data[0]['ws_kn']} (should match MWV)")
    print(f"  Wind speed ms: {mda_data[0]['ws_ms']} (expect {mda_data[0]['ws_kn']*0.5144:.1f})")

# --- HDT ---
print("\n--- HDT (Heading True) ---")
hdt_data = []
for line in groups.get('HDT', []):
    parts, _ = parse_fields(line)
    if parts and parts[0] == 'HEHDT':
        hdt_data.append({'heading': float(parts[1])})
if hdt_data:
    print(f"  Count: {len(hdt_data)}")
    print(f"  Heading: {hdt_data[0]['heading']} (should match RMC cog and VTG cog)")

# --- VDM ---
print("\n--- VDM (AIS Other Ships) ---")
vdm_payloads = []
for line in groups.get('VDM', []):
    parts, _ = parse_fields(line)
    if parts and parts[0] == 'AIVDM':
        payload = parts[5]
        vdm_payloads.append(payload)
if vdm_payloads:
    print(f"  Count: {len(vdm_payloads)}")
    print(f"  Unique payloads: {len(set(vdm_payloads))}")
    print(f"  Payload length: {len(vdm_payloads[0])} chars = {len(vdm_payloads[0])*6} bits (expect 28/168)")
    # Check how many unique targets (by MMSI)
    # First 6 bits = msg type (1), next 2 = repeat (0), next 30 = MMSI
    # So bits 8-37 = MMSI, which is chars 1-6 (bits 6-41), need to extract
    target_mmsis = set()
    for p in vdm_payloads:
        bits = ""
        for ch in p:
            idx = "0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz".index(ch)
            bits += format(idx, "06b")
        mmsi_bits = bits[8:38]
        mmsi = int(mmsi_bits, 2)
        target_mmsis.add(mmsi)
    print(f"  Unique target MMSIs: {len(target_mmsis)}")
    for m in sorted(target_mmsis):
        print(f"    MMSI: {m}")
    print(f"  All MMSIs >= 201000000: {all(m >= 201000000 for m in target_mmsis)}")

# --- VDO ---
print("\n--- VDO (AIS Own Ship) ---")
vdo_payloads = []
for line in groups.get('VDO', []):
    parts, _ = parse_fields(line)
    if parts and parts[0] == 'AIVDO':
        payload = parts[5]
        vdo_payloads.append(payload)
if vdo_payloads:
    print(f"  Count: {len(vdo_payloads)}")
    print(f"  Payload length: {len(vdo_payloads[0])} chars = {len(vdo_payloads[0])*6} bits")
    # Extract own ship MMSI
    p = vdo_payloads[0]
    bits = ""
    for ch in p:
        idx = "0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz".index(ch)
        bits += format(idx, "06b")
    own_mmsi = int(bits[8:38], 2)
    print(f"  Own ship MMSI: {own_mmsi} (config 200123456)")

# --- TTM ---
print("\n--- TTM (Tracked Target) ---")
ttm_data = []
for line in groups.get('TTM', []):
    parts, _ = parse_fields(line)
    if parts and parts[0] == 'RATTM':
        num = int(parts[1])
        dist = float(parts[2])
        bearing = float(parts[3])
        spd = float(parts[5])
        cog = float(parts[6])
        cpa = float(parts[8])
        tcpa = float(parts[9])
        ttm_data.append({'num': num, 'dist': dist, 'bearing': bearing, 'spd': spd, 'cog': cog, 'cpa': cpa, 'tcpa': tcpa})
if ttm_data:
    print(f"  Count: {len(ttm_data)}")
    nums = set(d['num'] for d in ttm_data)
    print(f"  Target numbers: {sorted(nums)} (expect 5 unique)")
    print(f"  Distance range: {min(d['dist'] for d in ttm_data):.1f} - {max(d['dist'] for d in ttm_data):.1f} nm (expect 0.5-8)")
    print(f"  Speed range: {min(d['spd'] for d in ttm_data):.1f} - {max(d['spd'] for d in ttm_data):.1f} kn (near 12.0)")
    print(f"  Course range: {min(d['cog'] for d in ttm_data):.1f} - {max(d['cog'] for d in ttm_data):.1f} deg (near 90 +/-60)")
    print(f"  CPA range: {min(d['cpa'] for d in ttm_data):.1f} - {max(d['cpa'] for d in ttm_data):.1f} nm")
    # Show first few targets
    seen = set()
    for d in ttm_data[:15]:
        if d['num'] not in seen:
            seen.add(d['num'])
            print(f"    Target {d['num']}: dist={d['dist']:.1f}nm, brg={d['bearing']:.1f}T, spd={d['spd']:.1f}kn, cog={d['cog']:.1f}T")

# --- TLL ---
print("\n--- TLL (Target Lat/Lon) ---")
tll_data = []
for line in groups.get('TLL', []):
    parts, _ = parse_fields(line)
    if parts and parts[0] == 'RATLL':
        num = int(parts[1])
        lat = parse_lat(parts[2], parts[3])
        lon = parse_lon(parts[4], parts[5])
        dist = float(parts[6])
        tll_data.append({'num': num, 'lat': lat, 'lon': lon, 'dist': dist})
if tll_data:
    print(f"  Count: {len(tll_data)}")
    nums = set(d['num'] for d in tll_data)
    print(f"  Target numbers: {sorted(nums)}")
    if rmc_data:
        own_lat = rmc_data[0]['lat']
        own_lon = rmc_data[0]['lon']
        print(f"  Own ship: {own_lat:.4f}, {own_lon:.4f}")
    seen = set()
    for d in tll_data[:15]:
        if d['num'] not in seen:
            seen.add(d['num'])
            if rmc_data:
                dist_calc = math.sqrt(((d['lat']-own_lat)*60)**2 + ((d['lon']-own_lon)*60*math.cos(math.radians(own_lat)))**2)
                print(f"    Target {d['num']}: lat={d['lat']:.4f}, lon={d['lon']:.4f}, dist={d['dist']:.1f}nm (calc={dist_calc:.1f}nm)")

# === 3. Cross-field consistency ===
print("\n" + "=" * 60)
print("3. CROSS-FIELD CONSISTENCY")
print("=" * 60)

# Position consistency: RMC vs GGA vs GLL
if rmc_data and gga_data and gll_data:
    print("\n  Position (RMC vs GGA vs GLL) at t=0:")
    print(f"    RMC: lat={rmc_data[0]['lat']:.6f}, lon={rmc_data[0]['lon']:.6f}")
    print(f"    GGA: lat={gga_data[0]['lat']:.6f}, lon={gga_data[0]['lon']:.6f}")
    print(f"    GLL: lat={gll_data[0]['lat']:.6f}, lon={gll_data[0]['lon']:.6f}")
    lat_diff = max(abs(rmc_data[0]['lat']-gga_data[0]['lat']), abs(rmc_data[0]['lat']-gll_data[0]['lat']))
    lon_diff = max(abs(rmc_data[0]['lon']-gga_data[0]['lon']), abs(rmc_data[0]['lon']-gll_data[0]['lon']))
    print(f"    Max lat diff: {lat_diff:.8f} (expect ~0)")
    print(f"    Max lon diff: {lon_diff:.8f} (expect ~0)")

# Heading consistency: RMC vs VTG vs HDT
if rmc_data and vtg_data and hdt_data:
    print("\n  Heading (RMC vs VTG vs HDT) at t=0:")
    print(f"    RMC COG: {rmc_data[0]['cog']:.1f}")
    print(f"    VTG COG: {vtg_data[0]['cog']:.1f}")
    print(f"    HDT:     {hdt_data[0]['heading']:.1f}")
    cog_diff = max(abs(rmc_data[0]['cog']-vtg_data[0]['cog']), abs(rmc_data[0]['cog']-hdt_data[0]['heading']))
    print(f"    Max diff: {cog_diff:.4f} (expect ~0)")

# Speed consistency: RMC vs VTG vs VBW
if rmc_data and vtg_data and vbw_data:
    print("\n  Speed (RMC vs VTG vs VBW) at t=0:")
    print(f"    RMC SOG:      {rmc_data[0]['sog']:.1f} kn")
    print(f"    VTG SOG:      {vtg_data[0]['sog_kn']:.1f} kn")
    print(f"    VBW ground:   {vbw_data[0]['ground_speed']:.1f} kn")
    print(f"    VBW water:    {vbw_data[0]['water_speed']:.1f} kn (should match SOG)")
    spd_diff = max(abs(rmc_data[0]['sog']-vtg_data[0]['sog_kn']), abs(rmc_data[0]['sog']-vbw_data[0]['ground_speed']))
    print(f"    Max diff: {spd_diff:.4f} (expect ~0)")

# Depth consistency: DPT vs DBT
if dpt_data and dbt_data:
    print("\n  Depth (DPT vs DBT) at t=0:")
    print(f"    DPT:    {dpt_data[0]['depth']:.1f} m")
    print(f"    DBT m:  {dbt_data[0]['d_m']:.1f} m")
    depth_diff = abs(dpt_data[0]['depth'] - dbt_data[0]['d_m'])
    print(f"    Diff: {depth_diff:.4f} (expect ~0)")
    print(f"    DBT ft check: {dbt_data[0]['d_m']*3.2808:.1f} vs {dbt_data[0]['d_ft']:.1f}")
    print(f"    DBT fa check: {dbt_data[0]['d_m']*0.5468:.1f} vs {dbt_data[0]['d_fa']:.1f}")

# Wind consistency: MWV vs MDA
if mwv_data and mda_data:
    print("\n  Wind (MWV vs MDA) at t=0:")
    print(f"    MWV dir: {mwv_data[0]['wind_dir']:.1f}, MDA dir: {mda_data[0]['wd']:.1f}")
    print(f"    MWV spd: {mwv_data[0]['wind_speed']:.1f}, MDA spd: {mda_data[0]['ws_kn']:.1f}")
    dir_diff = abs(mwv_data[0]['wind_dir'] - mda_data[0]['wd'])
    spd_diff = abs(mwv_data[0]['wind_speed'] - mda_data[0]['ws_kn'])
    print(f"    Dir diff: {dir_diff:.4f} (expect ~0)")
    print(f"    Spd diff: {spd_diff:.4f} (expect ~0)")

# === 4. VDM vs TTM vs TLL target consistency ===
print("\n" + "=" * 60)
print("4. VDM vs TTM vs TLL TARGET CONSISTENCY")
print("=" * 60)

if vdm_payloads and ttm_data and tll_data:
    print(f"\n  VDM unique targets: {len(target_mmsis)}")
    print(f"  TTM unique targets: {len(set(d['num'] for d in ttm_data))}")
    print(f"  TLL unique targets: {len(set(d['num'] for d in tll_data))}")
    print(f"  Target count match: {len(target_mmsis) == len(set(d['num'] for d in ttm_data)) == len(set(d['num'] for d in tll_data))}")

    # Check TTM and TLL target numbers overlap
    ttm_nums = set(d['num'] for d in ttm_data)
    tll_nums = set(d['num'] for d in tll_data)
    print(f"  TTM target nums: {sorted(ttm_nums)}")
    print(f"  TLL target nums: {sorted(tll_nums)}")
    print(f"  TTM/TLL nums overlap: {ttm_nums == tll_nums}")

    # Compare distances for same target
    ttm_by_num = {}
    for d in ttm_data:
        if d['num'] not in ttm_by_num:
            ttm_by_num[d['num']] = d
    tll_by_num = {}
    for d in tll_data:
        if d['num'] not in tll_by_num:
            tll_by_num[d['num']] = d

    print("\n  Target comparison (TTM vs TLL):")
    for num in sorted(ttm_by_num.keys() & tll_by_num.keys()):
        ttm = ttm_by_num[num]
        tll = tll_by_num[num]
        dist_diff = abs(ttm['dist'] - tll['dist'])
        pct = (dist_diff / max(ttm['dist'], tll['dist'], 0.01)) * 100
        print(f"    Target {num}: TTM dist={ttm['dist']:.1f}nm spd={ttm['spd']:.1f}kn cog={ttm['cog']:.1f}T | TLL dist={tll['dist']:.1f}nm lat={tll['lat']:.4f} lon={tll['lon']:.4f} | dist_diff={dist_diff:.1f}nm ({pct:.1f}%)")

print("\n" + "=" * 60)
print("VERIFICATION COMPLETE")
print("=" * 60)
