"""Parsers for JTWC/ATCF best-track (b-deck) files and JTWC .tcw forecast files.

b-deck row layout (comma separated, 0-indexed):
  0 basin, 1 cyclone no, 2 YYYYMMDDHH, 3 technum, 4 tech ("BEST"), 5 tau,
  6 lat (tenths, e.g. 176N), 7 lon (tenths, e.g. 0848E), 8 vmax kt, 9 mslp hPa,
  10 type, 11 radius threshold (34/50/64), 12 windcode, 13-16 radii NE SE SW NW nm,
  17 pressure of outer closed isobar, 18 radius of outer closed isobar,
  19 radius of max wind nm, 20 gusts, 21 eye, ..., 27 storm name.
There is one row per radius threshold per time, so rows are merged by time.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .model import Fix, Storm


def _coord(token: str) -> float:
    token = token.strip()
    hemi = token[-1]
    value = int(token[:-1]) / 10.0
    return -value if hemi in "SW" else value


def _num(items: list[str], idx: int) -> float | None:
    if idx >= len(items):
        return None
    raw = items[idx].strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_bdeck(text: str) -> tuple[list[Fix], str | None]:
    """Return merged BEST-track fixes and the storm name if present."""
    by_time: dict[datetime, dict] = {}
    name: str | None = None
    for line in text.splitlines():
        parts = line.split(",")
        if len(parts) < 11 or parts[4].strip() != "BEST":
            continue
        if _num(parts, 5) not in (0, None):  # keep analysis (tau 0) rows only
            continue
        try:
            t = datetime.strptime(parts[2].strip(), "%Y%m%d%H").replace(tzinfo=timezone.utc)
            lat, lon = _coord(parts[6]), _coord(parts[7])
        except (ValueError, IndexError):
            continue
        rec = by_time.setdefault(t, {"lat": lat, "lon": lon})
        vmax, mslp = _num(parts, 8), _num(parts, 9)
        if vmax:
            rec["vmax_kt"] = vmax
        if mslp:
            rec["mslp_hpa"] = mslp
        poci = _num(parts, 17)
        if poci:
            rec["poci_hpa"] = poci
        rmw = _num(parts, 19)
        if rmw:
            rec["rmw_nm"] = rmw
        thr = _num(parts, 11)
        radii = [_num(parts, i) or 0.0 for i in (13, 14, 15, 16)]
        if thr in (34, 50, 64) and any(radii):
            rec[f"r{int(thr)}_nm"] = radii
        if len(parts) > 27 and parts[27].strip():
            name = parts[27].strip()
    fixes = [Fix(t=t, **rec) for t, rec in sorted(by_time.items())]
    return fixes, name


_TCW_HEAD = re.compile(r"^\s*(\d{10})\s+(\d{2}[A-Z])\s+(\S+)")
_TCW_ROW = re.compile(
    r"^T(\d{3})\s+(\d+[NS])\s+(\d+[EW])\s+(\d+)"
    r"(?:\s+R034\s+(\d+)\s+NE\s+QD\s+(\d+)\s+SE\s+QD\s+(\d+)\s+SW\s+QD\s+(\d+)\s+NW\s+QD)?"
)


def parse_tcw(text: str) -> tuple[list[Fix], str | None]:
    """Parse the JTWC JMV 3.0 forecast file (`wp2526.tcw`): T000..T120 rows."""
    init: datetime | None = None
    name: str | None = None
    fixes: list[Fix] = []
    for line in text.splitlines():
        if init is None:
            m = _TCW_HEAD.match(line)
            if m:
                init = datetime.strptime(m.group(1), "%Y%m%d%H").replace(tzinfo=timezone.utc)
                name = m.group(3)
                continue
        m = _TCW_ROW.match(line.strip())
        if m and init is not None:
            tau = int(m.group(1))
            rec = {
                "t": init + timedelta(hours=tau),
                "lat": _coord(m.group(2)),
                "lon": _coord(m.group(3)),
                "vmax_kt": float(m.group(4)),
            }
            if m.group(5):
                rec["r34_nm"] = [float(m.group(i)) for i in (5, 6, 7, 8)]
            fixes.append(Fix(**rec))
    return fixes, name


def storm_from_bdeck(text: str, *, storm_id: str, season: int, basin: str, source: str,
                     summary: str = "", reference: dict | None = None,
                     fallback_name: str = "") -> Storm:
    fixes, name = parse_bdeck(text)
    if not fixes:
        raise ValueError(f"no BEST rows found for {storm_id}")
    return Storm(id=storm_id, name=(name or fallback_name).title(), basin=basin, season=season,
                 source=source, summary=summary, fixes=fixes, reference=reference or {})
