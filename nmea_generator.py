import math
import random
import time
from datetime import datetime, timezone, timedelta

NMEA_FORMATS = [
    {"code": "RMC", "desc": "推荐最小导航信息", "talker": "GP"},
    {"code": "GGA", "desc": "GPS定位数据", "talker": "GP"},
    {"code": "GLL", "desc": "地理位置", "talker": "GP"},
    {"code": "ZDA", "desc": "时间与日期", "talker": "GP"},
    {"code": "VTG", "desc": "对地航速航向", "talker": "GP"},
    {"code": "VBW", "desc": "对水对地速度", "talker": "VD"},
    {"code": "MWV", "desc": "风速风向", "talker": "WI"},
    {"code": "DPT", "desc": "水深", "talker": "SD"},
    {"code": "DBT", "desc": "换能器以下水深", "talker": "SD"},
    {"code": "MDA", "desc": "气象综合数据", "talker": "WI"},
    {"code": "VDM", "desc": "AIS他船信息", "talker": "AI"},
    {"code": "VDO", "desc": "AIS本船信息", "talker": "AI"},
    {"code": "HDT", "desc": "真航向", "talker": "HE"},
    {"code": "TTM", "desc": "雷达跟踪目标", "talker": "RA"},
    {"code": "TLL", "desc": "目标经纬度", "talker": "RA"},
]

FORMAT_CODES = [f["code"] for f in NMEA_FORMATS]

_AIS_CHARS = "0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz"


def nmea_checksum(content):
    cs = 0
    for ch in content:
        cs ^= ord(ch)
    return f"{cs:02X}"


def build_nmea(content):
    return f"${content}*{nmea_checksum(content)}\r\n"


def _format_lat(lat):
    hemi = "N" if lat >= 0 else "S"
    lat = abs(lat)
    deg = int(lat)
    minute = (lat - deg) * 60
    return f"{deg:02d}{minute:07.4f}", hemi


def _format_lon(lon):
    hemi = "E" if lon >= 0 else "W"
    lon = abs(lon)
    deg = int(lon)
    minute = (lon - deg) * 60
    return f"{deg:03d}{minute:07.4f}", hemi


def _from_signed(val, bits):
    if val < 0:
        return val + (1 << bits)
    return val


def _encode_ais_payload(bits):
    result = ""
    for i in range(0, len(bits), 6):
        chunk = bits[i:i + 6]
        if len(chunk) < 6:
            chunk = chunk.ljust(6, "0")
        result += _AIS_CHARS[int(chunk, 2)]
    return result


def _calc_bearing(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _calc_distance_nm(lat1, lon1, lat2, lon2):
    dlat = (lat2 - lat1) * 60
    dlon = (lon2 - lon1) * 60 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.sqrt(dlat ** 2 + dlon ** 2)


def _apply_pos_deviation(lat, lon, dev_meters):
    """对经纬度添加以米为单位的随机位置偏差"""
    if dev_meters <= 0:
        return lat, lon
    meters_to_deg_lat = 1.0 / 111120.0
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    meters_to_deg_lon = 1.0 / (111120.0 * cos_lat)
    dlat = random.uniform(-dev_meters, dev_meters) * meters_to_deg_lat
    dlon = random.uniform(-dev_meters, dev_meters) * meters_to_deg_lon
    return lat + dlat, lon + dlon


def _apply_val_deviation(val, dev):
    """对标量值添加随机偏差"""
    if dev <= 0:
        return val
    return val + random.uniform(-dev, dev)


def _norm_heading(h):
    """归一化航向到0-360"""
    return h % 360


def _calc_cpa_tcpa(o_lat, o_lon, o_sog, o_cog, t_lat, t_lon, t_sog, t_cog):
    rx = (t_lon - o_lon) * 60 * 1852 * math.cos(math.radians(o_lat))
    ry = (t_lat - o_lat) * 60 * 1852
    rvx = t_sog * 0.5144 * math.sin(math.radians(t_cog)) - o_sog * 0.5144 * math.sin(math.radians(o_cog))
    rvy = t_sog * 0.5144 * math.cos(math.radians(t_cog)) - o_sog * 0.5144 * math.cos(math.radians(o_cog))
    rs2 = rvx ** 2 + rvy ** 2
    if rs2 < 1e-6:
        return _calc_distance_nm(o_lat, o_lon, t_lat, t_lon), 0.0
    tcpa_s = -(rx * rvx + ry * rvy) / rs2
    if tcpa_s <= 0:
        return _calc_distance_nm(o_lat, o_lon, t_lat, t_lon), 0.0
    cpa_m = math.sqrt((rx + rvx * tcpa_s) ** 2 + (ry + rvy * tcpa_s) ** 2)
    return cpa_m / 1852, tcpa_s / 60


class NMEAGenerator:
    def __init__(self):
        self._vdm_index = 0
        self._vdm_ais_msg_idx = 0
        self._vdm_aton_msg_idx = 0
        self._vdo_type_index = 0
        self._ais_seq_id = 0
        self._ttm_index = 0
        self._tll_index = 0

    @staticmethod
    def _encode_ais_text(text, num_bits):
        max_chars = num_bits // 6
        text = text.upper().ljust(max_chars)[:max_chars]
        bits = ""
        for ch in text:
            val = (ord(ch) - 64) & 0x3F
            bits += format(val, "06b")
        return bits

    def _ais_type5_payload(self, mmsi, shipname, callsign, imo, ship_type, draught, destination):
        bits = ""
        bits += format(5, "06b")
        bits += "00"
        bits += format(int(mmsi) & 0x3FFFFFFF, "030b")
        bits += format(0, "02b")
        bits += format(int(imo) & 0x3FFFFFF, "030b")
        bits += self._encode_ais_text(callsign, 42)
        bits += self._encode_ais_text(shipname, 120)
        bits += format(ship_type & 0xFF, "08b")
        bits += format(random.randint(10, 50), "09b")
        bits += format(random.randint(10, 50), "09b")
        bits += format(random.randint(3, 10), "06b")
        bits += format(random.randint(3, 10), "06b")
        bits += format(1, "04b")
        eta = datetime.now(timezone.utc) + timedelta(days=random.randint(1, 30))
        bits += format(eta.month & 0xF, "04b")
        bits += format(eta.day & 0x1F, "05b")
        bits += format(eta.hour & 0x1F, "05b")
        bits += format(eta.minute & 0x3F, "06b")
        bits += format(int(draught * 10) & 0xFF, "08b")
        bits += self._encode_ais_text(destination, 120)
        bits += "0"
        bits += "0"
        return bits

    def _ais_type6_payload(self, src_mmsi, dst_mmsi, data_bits):
        bits = ""
        bits += format(6, "06b")
        bits += "00"
        bits += format(int(src_mmsi) & 0x3FFFFFFF, "030b")
        bits += format(random.randint(0, 3), "02b")
        bits += format(int(dst_mmsi) & 0x3FFFFFFF, "030b")
        bits += "0"
        bits += "0"
        bits += format(0, "010b")
        bits += format(0, "010b")
        bits += data_bits
        return bits

    def _ais_type8_payload(self, src_mmsi, data_bits):
        bits = ""
        bits += format(8, "06b")
        bits += "00"
        bits += format(int(src_mmsi) & 0x3FFFFFFF, "030b")
        bits += "00"
        bits += format(0, "010b")
        bits += format(0, "010b")
        bits += data_bits
        return bits

    def _ais_type12_payload(self, src_mmsi, dst_mmsi, text):
        bits = ""
        bits += format(12, "06b")
        bits += "00"
        bits += format(int(src_mmsi) & 0x3FFFFFFF, "030b")
        bits += format(random.randint(0, 3), "02b")
        bits += format(int(dst_mmsi) & 0x3FFFFFFF, "030b")
        bits += "0"
        bits += "0"
        bits += self._encode_ais_text_raw(text)
        return bits

    def _ais_type14_payload(self, src_mmsi, text):
        bits = ""
        bits += format(14, "06b")
        bits += "00"
        bits += format(int(src_mmsi) & 0x3FFFFFFF, "030b")
        bits += "00"
        bits += self._encode_ais_text_raw(text)
        return bits

    def _ais_type21_payload(self, mmsi, name, lat, lon, aton_type, utc_second):
        bits = ""
        bits += format(21, "06b")
        bits += "00"
        bits += format(int(mmsi) & 0x3FFFFFFF, "030b")
        bits += format(aton_type & 0x1F, "05b")
        bits += self._encode_ais_text(name, 180)
        bits += "0"
        lon_raw = _from_signed(int(round(lon * 60 * 10000)), 28) & 0xFFFFFFF
        bits += format(lon_raw, "028b")
        lat_raw = _from_signed(int(round(lat * 60 * 10000)), 27) & 0x7FFFFFF
        bits += format(lat_raw, "027b")
        bits += format(random.randint(5, 20), "09b")
        bits += format(random.randint(5, 20), "09b")
        bits += format(random.randint(3, 8), "06b")
        bits += format(random.randint(3, 8), "06b")
        bits += format(1, "04b")
        bits += format(utc_second & 0x3F, "06b")
        bits += "0"
        bits += format(0, "08b")
        bits += "0"
        bits += "0"
        bits += "0"
        bits += "0"
        return bits

    def _ais_type24_payloads(self, mmsi, shipname, callsign, ship_type):
        part_a = ""
        part_a += format(24, "06b")
        part_a += "00"
        part_a += format(int(mmsi) & 0x3FFFFFFF, "030b")
        part_a += "00"
        part_a += self._encode_ais_text(shipname, 120)
        part_a += format(0, "04b")
        part_b = ""
        part_b += format(24, "06b")
        part_b += "00"
        part_b += format(int(mmsi) & 0x3FFFFFFF, "030b")
        part_b += "01"
        part_b += format(ship_type & 0xFF, "08b")
        part_b += self._encode_ais_text("SIMVENDOR", 42)
        part_b += self._encode_ais_text(callsign, 42)
        part_b += format(random.randint(5, 20), "09b")
        part_b += format(random.randint(5, 20), "09b")
        part_b += format(random.randint(3, 8), "06b")
        part_b += format(random.randint(3, 8), "06b")
        part_b += format(1, "04b")
        return [(part_a, 0), (part_b, 0)]

    @staticmethod
    def _encode_ais_text_raw(text):
        bits = ""
        for ch in text.upper():
            val = (ord(ch) - 64) & 0x3F
            bits += format(val, "06b")
        return bits

    def _gen_data_bits(self, header_bits, target_fragments):
        if target_fragments <= 1:
            return format(0, "024b")
        target_chars = (target_fragments - 1) * 56 + 28
        target_bits = target_chars * 6
        data_bits_needed = max(24, target_bits - header_bits)
        bits = ""
        for i in range(data_bits_needed):
            bits += "01"[i % 2]
        return bits

    def _gen_safety_text(self, header_bits, target_fragments):
        if target_fragments <= 1:
            return "SAFETY MESSAGE"
        target_chars = (target_fragments - 1) * 56 + 28
        target_bits = target_chars * 6
        text_chars = max(14, (target_bits - header_bits) // 6)
        base = "SAFETY ALERT MESSAGE FOR NAVIGATION "
        return (base * (text_chars // len(base) + 1))[:text_chars]

    def _split_ais_payload(self, bits, max_chars=56, manual_count=0):
        if manual_count > 0:
            total_chars = math.ceil(len(bits) / 6)
            chars_per_frag = max(1, math.ceil(total_chars / manual_count))
            max_bits = chars_per_frag * 6
        else:
            max_bits = max_chars * 6
        fragments = []
        for i in range(0, len(bits), max_bits):
            chunk = bits[i:i + max_bits]
            remaining = len(chunk) % 6
            fill_bits = (6 - remaining) if remaining else 0
            payload = _encode_ais_payload(chunk)
            fragments.append((payload, fill_bits))
        return fragments

    def _build_fragment_sentences(self, talker, fragments, channel):
        seq_id = self._ais_seq_id % 10
        self._ais_seq_id += 1
        total = len(fragments)
        sentences = []
        for i, (payload, fill) in enumerate(fragments):
            body = f"{talker},{total},{i+1},{seq_id},{channel},{payload},{fill}"
            sentences.append(build_nmea(body))
        return sentences

    def _ais_type1_payload(self, mmsi, lat, lon, sog, cog, heading, utc_second):
        bits = ""
        bits += format(1, "06b")
        bits += "00"
        bits += format(int(mmsi) & 0x3FFFFFFF, "030b")
        bits += format(0, "04b")
        bits += format(_from_signed(-128, 8) & 0xFF, "08b")
        bits += format(int(round(sog * 10)) & 0x3FF, "010b")
        bits += "0"
        lon_raw = _from_signed(int(round(lon * 60 * 10000)), 28) & 0xFFFFFFF
        bits += format(lon_raw, "028b")
        lat_raw = _from_signed(int(round(lat * 60 * 10000)), 27) & 0x7FFFFFF
        bits += format(lat_raw, "027b")
        bits += format(int(round(cog * 10)) & 0xFFF, "012b")
        bits += format(int(round(heading)) & 0x1FF, "09b")
        bits += format(utc_second & 0x3F, "06b")
        bits += "0000"
        bits += "0"
        bits += "0"
        bits += format(0, "019b")
        return _encode_ais_payload(bits)

    def _ais_type4_payload(self, mmsi, lat, lon, utc_second, year, month, day, hour, minute):
        bits = ""
        bits += format(4, "06b")
        bits += "00"
        bits += format(int(mmsi) & 0x3FFFFFFF, "030b")
        bits += format(year & 0xFFF, "014b")
        bits += format(month & 0xF, "04b")
        bits += format(day & 0x1F, "05b")
        bits += format(hour & 0x1F, "05b")
        bits += format(minute & 0x3F, "06b")
        bits += format(0, "02b")
        bits += "0"
        lon_raw = _from_signed(int(round(lon * 60 * 10000)), 28) & 0xFFFFFFF
        bits += format(lon_raw, "028b")
        lat_raw = _from_signed(int(round(lat * 60 * 10000)), 27) & 0x7FFFFFF
        bits += format(lat_raw, "027b")
        bits += format(0, "04b")
        bits += "0"
        bits += "0"
        bits += format(utc_second & 0x3F, "06b")
        bits += "0"
        bits += "000"
        bits += "0"
        bits += format(0, "023b")
        return _encode_ais_payload(bits)

    def _ais_type9_payload(self, mmsi, lat, lon, alt, sog, cog, utc_second):
        bits = ""
        bits += format(9, "06b")
        bits += "00"
        bits += format(int(mmsi) & 0x3FFFFFFF, "030b")
        bits += format(int(round(alt)), "012b")
        bits += "0"
        # SOG for aircraft is in knots, 1 unit = 1 knot
        bits += format(int(round(sog)) & 0x3FF, "010b")
        bits += "0"
        bits += "0000"
        bits += format(0, "03b")
        lon_raw = _from_signed(int(round(lon * 60 * 10000)), 28) & 0xFFFFFFF
        bits += format(lon_raw, "028b")
        lat_raw = _from_signed(int(round(lat * 60 * 10000)), 27) & 0x7FFFFFF
        bits += format(lat_raw, "027b")
        bits += format(0, "04b")
        bits += "0"
        bits += format(int(round(cog * 10)) & 0xFFF, "012b")
        bits += format(utc_second & 0x3F, "06b")
        bits += "0"
        bits += "0"
        bits += format(0, "020b")
        return _encode_ais_payload(bits)

    def generate(self, fmt, state):
        result = None
        if fmt == "RMC":
            result = self._gen_rmc(state)
        elif fmt == "GGA":
            result = self._gen_gga(state)
        elif fmt == "GLL":
            result = self._gen_gll(state)
        elif fmt == "ZDA":
            result = self._gen_zda(state)
        elif fmt == "VTG":
            result = self._gen_vtg(state)
        elif fmt == "VBW":
            result = self._gen_vbw(state)
        elif fmt == "MWV":
            result = self._gen_mwv(state)
        elif fmt == "DPT":
            result = self._gen_dpt(state)
        elif fmt == "DBT":
            result = self._gen_dbt(state)
        elif fmt == "MDA":
            result = self._gen_mda(state)
        elif fmt == "VDM":
            result = self._gen_vdm(state)
        elif fmt == "VDO":
            result = self._gen_vdo(state)
        elif fmt == "HDT":
            result = self._gen_hdt(state)
        elif fmt == "TTM":
            result = self._gen_ttm(state)
        elif fmt == "TLL":
            result = self._gen_tll(state)
        if result is None:
            return []
        if isinstance(result, list):
            return result
        return [result]

    def _gen_rmc(self, s):
        t = s.utc_time
        hhmmss = t.strftime("%H%M%S") + f".{t.microsecond // 10000:02d}"
        date = t.strftime("%d%m%y")
        lat_str, lat_h = _format_lat(s.latitude)
        lon_str, lon_h = _format_lon(s.longitude)
        body = f"GPRMC,{hhmmss},A,{lat_str},{lat_h},{lon_str},{lon_h},{s.speed:.1f},{s.heading:.1f},{date},,,A"
        return build_nmea(body)

    def _gen_gga(self, s):
        t = s.utc_time
        hhmmss = t.strftime("%H%M%S") + f".{t.microsecond // 10000:02d}"
        lat_str, lat_h = _format_lat(s.latitude)
        lon_str, lon_h = _format_lon(s.longitude)
        sats = s.get("satellites", 8)
        hdop = s.get("hdop", 0.8)
        alt = s.get("altitude", 34.7)
        body = f"GPGGA,{hhmmss},{lat_str},{lat_h},{lon_str},{lon_h},1,{sats:02d},{hdop:.1f},{alt:.1f},M,0.0,M,,"
        return build_nmea(body)

    def _gen_gll(self, s):
        t = s.utc_time
        hhmmss = t.strftime("%H%M%S") + f".{t.microsecond // 10000:02d}"
        lat_str, lat_h = _format_lat(s.latitude)
        lon_str, lon_h = _format_lon(s.longitude)
        body = f"GPGLL,{lat_str},{lat_h},{lon_str},{lon_h},{hhmmss},A,A"
        return build_nmea(body)

    def _gen_zda(self, s):
        t = s.utc_time
        hhmmss = t.strftime("%H%M%S") + f".{t.microsecond // 10000:02d}"
        body = f"GPZDA,{hhmmss},{t.day:02d},{t.month:02d},{t.year},00,00"
        return build_nmea(body)

    def _gen_vtg(self, s):
        spd_kmh = s.speed * 1.852
        body = f"GPVTG,{s.heading:.1f},T,,M,{s.speed:.1f},N,{spd_kmh:.1f},K,A"
        return build_nmea(body)

    def _gen_vbw(self, s):
        ws = s.get("water_speed", s.speed)
        body = f"VDVBW,{ws:.1f},0.0,A,{s.speed:.1f},0.0,A,A"
        return build_nmea(body)

    def _gen_mwv(self, s):
        body = f"WIMWV,{s.wind_direction:.1f},T,{s.wind_speed:.1f},N,A"
        return build_nmea(body)

    def _gen_dpt(self, s):
        body = f"SDDPT,{s.water_depth:.1f},0.0,100.0"
        return build_nmea(body)

    def _gen_dbt(self, s):
        d_ft = s.water_depth * 3.2808
        d_fa = s.water_depth * 0.5468
        body = f"SDDBT,{d_ft:.1f},f,{s.water_depth:.1f},M,{d_fa:.1f},F"
        return build_nmea(body)

    def _gen_mda(self, s):
        p_in = s.get("pressure", 1013.0) * 0.02953
        p_bar = s.get("pressure", 1013.0) / 1000.0
        dew = self._dew_point(s.temperature, s.humidity)
        body = (
            f"WIMDA,{p_in:.2f},I,{p_bar:.3f},B,"
            f"{s.temperature:.1f},C,,C,{s.humidity:.1f},,{dew:.1f},C,"
            f"{s.wind_direction:.0f},T,,M,{s.wind_speed:.1f},N,{s.wind_speed * 0.5144:.1f},M"
        )
        return build_nmea(body)

    def _gen_vdm(self, s):
        sources = []
        for tgt in s.get("ais_targets", []):
            sources.append(("ais", tgt))
        for aton in s.get("aton_targets", []):
            sources.append(("aton", aton))
        for spec in s.get("special_targets", []):
            sources.append(("special", spec))
        if not sources:
            return None
        src_type, target = sources[self._vdm_index % len(sources)]
        self._vdm_index += 1
        if src_type == "ais":
            return self._gen_vdm_ais(target, s)
        elif src_type == "aton":
            return self._gen_vdm_aton(target, s)
        elif src_type == "special":
            return self._gen_vdm_special(target, s)
        return None

    def _gen_vdm_ais(self, tgt, s):
        msg_types = tgt.get("msg_types", [1])
        msg_type = msg_types[self._vdm_ais_msg_idx % len(msg_types)]
        self._vdm_ais_msg_idx += 1
        fc = tgt.get("fragment_count", 1)
        own_mmsi = s.get("mmsi", 200000000)
        if msg_type == 1:
            ais_pos_dev = s.get("ais_pos_dev", 10.0)
            ais_speed_dev = s.get("ais_speed_dev", 0.1)
            ais_heading_dev = s.get("ais_heading_dev", 1.0)
            lat, lon = _apply_pos_deviation(tgt["latitude"], tgt["longitude"], ais_pos_dev)
            speed = max(0, _apply_val_deviation(tgt["speed"], ais_speed_dev))
            true_heading = tgt.get("heading", 0)
            cog = _norm_heading(_apply_val_deviation(true_heading, ais_heading_dev))
            heading = _norm_heading(_apply_val_deviation(true_heading, ais_heading_dev))
            payload = self._ais_type1_payload(
                tgt["mmsi"], lat, lon,
                speed, cog, heading, s.utc_time.second
            )
            return build_nmea(f"AIVDM,1,1,,B,{payload},0")
        if msg_type == 5:
            bits = self._ais_type5_payload(
                tgt["mmsi"], tgt.get("ship_name", ""), tgt.get("callsign", ""),
                tgt.get("imo_number", 0), tgt.get("ship_type", 36),
                tgt.get("draught", 5.0), tgt.get("destination", "")
            )
            fragments = self._split_ais_payload(bits, manual_count=fc)
            return self._build_fragment_sentences("AIVDM", fragments, "B")
        if msg_type == 6:
            data = self._gen_data_bits(92, fc)
            bits = self._ais_type6_payload(tgt["mmsi"], own_mmsi, data)
            fragments = self._split_ais_payload(bits, manual_count=fc)
            return self._build_fragment_sentences("AIVDM", fragments, "B")
        if msg_type == 8:
            data = self._gen_data_bits(60, fc)
            bits = self._ais_type8_payload(tgt["mmsi"], data)
            fragments = self._split_ais_payload(bits, manual_count=fc)
            return self._build_fragment_sentences("AIVDM", fragments, "B")
        if msg_type == 12:
            text = self._gen_safety_text(72, fc)
            bits = self._ais_type12_payload(tgt["mmsi"], own_mmsi, text)
            fragments = self._split_ais_payload(bits, manual_count=fc)
            return self._build_fragment_sentences("AIVDM", fragments, "B")
        if msg_type == 14:
            text = self._gen_safety_text(40, fc)
            bits = self._ais_type14_payload(tgt["mmsi"], text)
            fragments = self._split_ais_payload(bits, manual_count=fc)
            return self._build_fragment_sentences("AIVDM", fragments, "B")
        if msg_type == 24:
            parts = self._ais_type24_payloads(
                tgt["mmsi"], tgt.get("ship_name", ""), tgt.get("callsign", ""),
                tgt.get("ship_type", 36)
            )
            sentences = []
            for payload, fill in parts:
                body = f"AIVDM,1,1,,B,{_encode_ais_payload(payload)},{fill}"
                sentences.append(build_nmea(body))
            return sentences
        return None

    def _gen_vdm_aton(self, aton, s):
        msg_types = aton.get("msg_types", [21])
        msg_type = msg_types[self._vdm_aton_msg_idx % len(msg_types)]
        self._vdm_aton_msg_idx += 1
        fc = aton.get("fragment_count", 1)
        if msg_type == 21:
            bits = self._ais_type21_payload(
                aton["mmsi"], aton["name"], aton["latitude"],
                aton["longitude"], aton.get("aton_type", 1), s.utc_time.second
            )
            fragments = self._split_ais_payload(bits, manual_count=fc)
            return self._build_fragment_sentences("AIVDM", fragments, "B")
        if msg_type == 8:
            data = self._gen_data_bits(60, fc)
            bits = self._ais_type8_payload(aton["mmsi"], data)
            fragments = self._split_ais_payload(bits, manual_count=fc)
            return self._build_fragment_sentences("AIVDM", fragments, "B")
        return None

    def _gen_vdm_special(self, target, s):
        tt = target.get("target_type", "")
        fc = target.get("fragment_count", 1)
        if tt == "basestation":
            payload = self._ais_type4_payload(
                target["mmsi"], target["latitude"], target["longitude"],
                s.utc_time.second, s.utc_time.year, s.utc_time.month,
                s.utc_time.day, s.utc_time.hour, s.utc_time.minute
            )
            return build_nmea(f"AIVDM,1,1,,B,{payload},0")
        if tt == "aircraft":
            payload = self._ais_type9_payload(
                target["mmsi"], target["latitude"], target["longitude"],
                target.get("altitude", 1000), target.get("speed", 150),
                target.get("heading", 0), s.utc_time.second
            )
            return build_nmea(f"AIVDM,1,1,,B,{payload},0")
        if tt == "weather":
            data_bits = self._ais_weather_data_bits(target)
            bits = self._ais_type8_payload(target["mmsi"], data_bits)
            fragments = self._split_ais_payload(bits, manual_count=fc)
            return self._build_fragment_sentences("AIVDM", fragments, "B")
        if tt == "sart":
            text = "SART ACTIVE"
            bits = self._ais_type14_payload(target["mmsi"], text)
            fragments = self._split_ais_payload(bits, manual_count=fc)
            return self._build_fragment_sentences("AIVDM", fragments, "B")
        if tt == "route":
            data_bits = self._ais_route_data_bits(target, s)
            bits = self._ais_type8_payload(target["mmsi"], data_bits)
            fragments = self._split_ais_payload(bits, manual_count=fc)
            return self._build_fragment_sentences("AIVDM", fragments, "B")
        return None

    def _ais_weather_data_bits(self, target):
        bits = ""
        bits += format(1, "010b")
        bits += format(31, "06b")
        bits += format(int(target.get("wind_speed", 15)) & 0x3FF, "010b")
        bits += format(int(target.get("wind_direction", 180)) & 0x1FF, "09b")
        bits += format(int(target.get("pressure", 1013) - 800) & 0x1FF, "09b")
        bits += format(_from_signed(int(round(target.get("temperature", 22) * 10)), 8) & 0xFF, "08b")
        bits += format(int(target.get("humidity", 65)) & 0x7F, "07b")
        bits += format(int(target.get("visibility", 10)) & 0xFF, "08b")
        return bits

    def _ais_route_data_bits(self, target, s):
        bits = ""
        bits += format(1, "010b")
        bits += format(29, "06b")
        bits += format(1, "04b")
        bits += format(5, "05b")
        base_lat = s.latitude
        base_lon = s.longitude
        for i in range(5):
            lat = base_lat + i * 0.05
            lon = base_lon + i * 0.05
            lat_raw = _from_signed(int(round(lat * 60 * 10000)), 27) & 0x7FFFFFF
            lon_raw = _from_signed(int(round(lon * 60 * 10000)), 28) & 0xFFFFFFF
            bits += format(lat_raw, "027b")
            bits += format(lon_raw, "028b")
        return bits

    def _gen_vdo(self, s):
        msg_types_str = str(s.get("vdo_msg_types", "1"))
        msg_types = [int(x) for x in msg_types_str.split(",") if x.strip()]
        if not msg_types:
            msg_types = [1]
        msg_type = msg_types[self._vdo_type_index % len(msg_types)]
        self._vdo_type_index += 1
        fc = s.get("vdo_fragment_count", 1)
        own_mmsi = s.get("mmsi", 200000000)
        if msg_type == 1:
            ais_pos_dev = s.get("ais_pos_dev", 10.0)
            ais_speed_dev = s.get("ais_speed_dev", 0.1)
            ais_heading_dev = s.get("ais_heading_dev", 1.0)
            lat, lon = _apply_pos_deviation(s.latitude, s.longitude, ais_pos_dev)
            speed = max(0, _apply_val_deviation(s.speed, ais_speed_dev))
            cog = _norm_heading(_apply_val_deviation(s.heading, ais_heading_dev))
            heading = _norm_heading(_apply_val_deviation(s.heading, ais_heading_dev))
            payload = self._ais_type1_payload(
                own_mmsi, lat, lon,
                speed, cog, heading, s.utc_time.second
            )
            return build_nmea(f"AIVDO,1,1,,A,{payload},0")
        if msg_type == 5:
            bits = self._ais_type5_payload(
                own_mmsi, s.get("ship_name", "SIM VESSEL"),
                s.get("callsign", "SIMCALL"),
                s.get("imo_number", 1234567),
                s.get("ship_type_ais", 36),
                s.get("draught", 5.0),
                s.get("destination", "SHANGHAI")
            )
            fragments = self._split_ais_payload(bits, manual_count=fc)
            return self._build_fragment_sentences("AIVDO", fragments, "A")
        if msg_type == 24:
            parts = self._ais_type24_payloads(
                own_mmsi, s.get("ship_name", "SIM VESSEL"),
                s.get("callsign", "SIMCALL"), s.get("ship_type_ais", 36)
            )
            sentences = []
            for payload, fill in parts:
                body = f"AIVDO,1,1,,A,{_encode_ais_payload(payload)},{fill}"
                sentences.append(build_nmea(body))
            return sentences
        if msg_type == 6:
            tgt_mmsi = 201000001
            data = self._gen_data_bits(92, fc)
            bits = self._ais_type6_payload(own_mmsi, tgt_mmsi, data)
            fragments = self._split_ais_payload(bits, manual_count=fc)
            return self._build_fragment_sentences("AIVDO", fragments, "A")
        if msg_type == 8:
            data = self._gen_data_bits(60, fc)
            bits = self._ais_type8_payload(own_mmsi, data)
            fragments = self._split_ais_payload(bits, manual_count=fc)
            return self._build_fragment_sentences("AIVDO", fragments, "A")
        if msg_type == 12:
            tgt_mmsi = 201000001
            text = self._gen_safety_text(72, fc)
            bits = self._ais_type12_payload(own_mmsi, tgt_mmsi, text)
            fragments = self._split_ais_payload(bits, manual_count=fc)
            return self._build_fragment_sentences("AIVDO", fragments, "A")
        if msg_type == 14:
            text = self._gen_safety_text(40, fc)
            bits = self._ais_type14_payload(own_mmsi, text)
            fragments = self._split_ais_payload(bits, manual_count=fc)
            return self._build_fragment_sentences("AIVDO", fragments, "A")
        return None

    def _gen_hdt(self, s):
        body = f"HEHDT,{s.heading:.1f},T"
        return build_nmea(body)

    def _gen_ttm(self, s):
        targets = s.get("ais_targets", [])
        if not targets:
            return None
        idx = self._ttm_index % len(targets)
        self._ttm_index += 1
        tgt = targets[idx]
        radar_pos_dev = s.get("radar_pos_dev", 30.0)
        radar_bearing_dev = s.get("radar_bearing_dev", 1.5)
        radar_speed_dev = s.get("radar_speed_dev", 0.3)
        radar_heading_dev = s.get("radar_heading_dev", 2.0)
        r_lat, r_lon = _apply_pos_deviation(tgt["latitude"], tgt["longitude"], radar_pos_dev)
        bearing = _calc_bearing(s.latitude, s.longitude, r_lat, r_lon)
        bearing = _norm_heading(_apply_val_deviation(bearing, radar_bearing_dev))
        dist = _calc_distance_nm(s.latitude, s.longitude, r_lat, r_lon)
        r_speed = max(0, _apply_val_deviation(tgt["speed"], radar_speed_dev))
        true_heading = tgt.get("heading", 0)
        r_cog = _norm_heading(_apply_val_deviation(true_heading, radar_heading_dev))
        cpa, tcpa = _calc_cpa_tcpa(
            s.latitude, s.longitude, s.speed, s.heading,
            r_lat, r_lon, r_speed, r_cog
        )
        num = idx + 1
        body = (
            f"RATTM,{num:02d},{dist:.1f},{bearing:.1f},T,"
            f"{r_speed:.1f},{r_cog:.1f},T,"
            f"{cpa:.1f},{tcpa:.1f},N,,T,A,R,,A,R"
        )
        return build_nmea(body)

    def _gen_tll(self, s):
        targets = s.get("ais_targets", [])
        if not targets:
            return None
        idx = self._tll_index % len(targets)
        self._tll_index += 1
        tgt = targets[idx]
        radar_pos_dev = s.get("radar_pos_dev", 30.0)
        r_lat, r_lon = _apply_pos_deviation(tgt["latitude"], tgt["longitude"], radar_pos_dev)
        dist = _calc_distance_nm(s.latitude, s.longitude, r_lat, r_lon)
        lat_str, lat_h = _format_lat(r_lat)
        lon_str, lon_h = _format_lon(r_lon)
        num = idx + 1
        t = s.utc_time
        hhmmss = t.strftime("%H%M%S") + f".{t.microsecond // 10000:02d}"
        body = f"RATLL,{num:02d},{lat_str},{lat_h},{lon_str},{lon_h},{dist:.1f},N,,{hhmmss},T,R"
        return build_nmea(body)

    @staticmethod
    def _dew_point(temp, rh):
        if rh <= 0:
            return temp
        gamma = math.log(rh / 100) + (17.62 * temp) / (243.12 + temp)
        return (243.12 * gamma) / (17.62 - gamma)
