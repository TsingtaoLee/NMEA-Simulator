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
        self._aton_index = 0
        self._ais_seq_id = 0
        self._ttm_index = 0
        self._tll_index = 0

    @staticmethod
    def _encode_ais_text(text, num_bits):
        max_chars = num_bits // 6
        text = text.upper().ljust(max_chars)[:max_chars]
        bits = ""
        for ch in text:
            val = ord(ch) - 32
            if val < 0 or val > 63:
                val = 0
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
            val = ord(ch) - 32
            if val < 0 or val > 63:
                val = 0
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
        mode = s.get("ais_fragment_mode", 0)
        msg_type = s.get("ais_fragment_type", 5)
        if mode == 0:
            return self._gen_vdm_type1(s)
        if mode == 1 and s.utc_time.second % 2 != 0:
            return self._gen_vdm_type1(s)
        return self._gen_vdm_fragmented(s, msg_type)

    def _gen_vdm_type1(self, s):
        targets = s.get("ais_targets", [])
        if not targets:
            return None
        tgt = targets[self._vdm_index % len(targets)]
        self._vdm_index += 1
        payload = self._ais_type1_payload(
            tgt["mmsi"], tgt["latitude"], tgt["longitude"],
            tgt["speed"], tgt.get("cog", tgt.get("heading", 0)),
            tgt.get("heading", 0), s.utc_time.second
        )
        body = f"AIVDM,1,1,,B,{payload},0"
        return build_nmea(body)

    def _gen_vdm_fragmented(self, s, msg_type):
        mc = s.get("ais_fragment_count", 0)
        if msg_type == 21:
            atons = s.get("aton_targets", [])
            if not atons:
                return None
            aton = atons[self._aton_index % len(atons)]
            self._aton_index += 1
            bits = self._ais_type21_payload(
                aton["mmsi"], aton["name"], aton["latitude"],
                aton["longitude"], aton.get("aton_type", 1), s.utc_time.second
            )
            fragments = self._split_ais_payload(bits, manual_count=mc)
            return self._build_fragment_sentences("AIVDM", fragments, "B")
        targets = s.get("ais_targets", [])
        if not targets:
            return None
        tgt = targets[self._vdm_index % len(targets)]
        self._vdm_index += 1
        own_mmsi = s.get("mmsi", 200000000)
        if msg_type == 5:
            bits = self._ais_type5_payload(
                tgt["mmsi"], "SIM TARGET", "TGT01",
                random.randint(1000000, 9999999), 36,
                s.get("water_depth", 50.0), "PORT SHANGHAI"
            )
            fragments = self._split_ais_payload(bits, manual_count=mc)
            return self._build_fragment_sentences("AIVDM", fragments, "B")
        if msg_type == 6:
            data = self._gen_data_bits(92, mc)
            bits = self._ais_type6_payload(tgt["mmsi"], own_mmsi, data)
            fragments = self._split_ais_payload(bits, manual_count=mc)
            return self._build_fragment_sentences("AIVDM", fragments, "B")
        if msg_type == 8:
            data = self._gen_data_bits(60, mc)
            bits = self._ais_type8_payload(tgt["mmsi"], data)
            fragments = self._split_ais_payload(bits, manual_count=mc)
            return self._build_fragment_sentences("AIVDM", fragments, "B")
        if msg_type == 12:
            text = self._gen_safety_text(72, mc)
            bits = self._ais_type12_payload(tgt["mmsi"], own_mmsi, text)
            fragments = self._split_ais_payload(bits, manual_count=mc)
            return self._build_fragment_sentences("AIVDM", fragments, "B")
        if msg_type == 14:
            text = self._gen_safety_text(40, mc)
            bits = self._ais_type14_payload(tgt["mmsi"], text)
            fragments = self._split_ais_payload(bits, manual_count=mc)
            return self._build_fragment_sentences("AIVDM", fragments, "B")
        if msg_type == 24:
            parts = self._ais_type24_payloads(
                tgt["mmsi"], "SIM TARGET", "TGT01", 36
            )
            sentences = []
            for payload, fill in parts:
                body = f"AIVDM,1,1,,B,{_encode_ais_payload(payload)},{fill}"
                sentences.append(build_nmea(body))
            return sentences
        return None

    def _gen_vdo(self, s):
        mode = s.get("ais_fragment_mode", 0)
        msg_type = s.get("ais_fragment_type", 5)
        if mode == 0 or msg_type == 21:
            return self._gen_vdo_type1(s)
        if mode == 1 and s.utc_time.second % 2 != 0:
            return self._gen_vdo_type1(s)
        return self._gen_vdo_fragmented(s, msg_type)

    def _gen_vdo_type1(self, s):
        payload = self._ais_type1_payload(
            s.get("mmsi", 200000000), s.latitude, s.longitude,
            s.speed, s.heading, s.heading, s.utc_time.second
        )
        body = f"AIVDO,1,1,,A,{payload},0"
        return build_nmea(body)

    def _gen_vdo_fragmented(self, s, msg_type):
        mc = s.get("ais_fragment_count", 0)
        own_mmsi = s.get("mmsi", 200000000)
        targets = s.get("ais_targets", [])
        tgt_mmsi = targets[0]["mmsi"] if targets else 201000001
        if msg_type == 5:
            bits = self._ais_type5_payload(
                own_mmsi, "SIM OWN SHIP", "OWN01",
                random.randint(1000000, 9999999), 36,
                s.get("water_depth", 50.0), "DESTINATION PORT"
            )
            fragments = self._split_ais_payload(bits, manual_count=mc)
            return self._build_fragment_sentences("AIVDO", fragments, "A")
        if msg_type == 6:
            data = self._gen_data_bits(92, mc)
            bits = self._ais_type6_payload(own_mmsi, tgt_mmsi, data)
            fragments = self._split_ais_payload(bits, manual_count=mc)
            return self._build_fragment_sentences("AIVDO", fragments, "A")
        if msg_type == 8:
            data = self._gen_data_bits(60, mc)
            bits = self._ais_type8_payload(own_mmsi, data)
            fragments = self._split_ais_payload(bits, manual_count=mc)
            return self._build_fragment_sentences("AIVDO", fragments, "A")
        if msg_type == 12:
            text = self._gen_safety_text(72, mc)
            bits = self._ais_type12_payload(own_mmsi, tgt_mmsi, text)
            fragments = self._split_ais_payload(bits, manual_count=mc)
            return self._build_fragment_sentences("AIVDO", fragments, "A")
        if msg_type == 14:
            text = self._gen_safety_text(40, mc)
            bits = self._ais_type14_payload(own_mmsi, text)
            fragments = self._split_ais_payload(bits, manual_count=mc)
            return self._build_fragment_sentences("AIVDO", fragments, "A")
        if msg_type == 24:
            parts = self._ais_type24_payloads(
                own_mmsi, "SIM OWN SHIP", "OWN01", 36
            )
            sentences = []
            for payload, fill in parts:
                body = f"AIVDO,1,1,,A,{_encode_ais_payload(payload)},{fill}"
                sentences.append(build_nmea(body))
            return sentences
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
        bearing = _calc_bearing(s.latitude, s.longitude, tgt["latitude"], tgt["longitude"])
        dist = _calc_distance_nm(s.latitude, s.longitude, tgt["latitude"], tgt["longitude"])
        tgt_cog = tgt.get("cog", tgt.get("heading", 0))
        cpa, tcpa = _calc_cpa_tcpa(
            s.latitude, s.longitude, s.speed, s.heading,
            tgt["latitude"], tgt["longitude"], tgt["speed"], tgt_cog
        )
        num = idx + 1
        body = (
            f"RATTM,{num:02d},{dist:.1f},{bearing:.1f},T,"
            f"{tgt['speed']:.1f},{tgt_cog:.1f},T,"
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
        dist = _calc_distance_nm(s.latitude, s.longitude, tgt["latitude"], tgt["longitude"])
        lat_str, lat_h = _format_lat(tgt["latitude"])
        lon_str, lon_h = _format_lon(tgt["longitude"])
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
