#!/usr/bin/env python3
"""Generate a truthful, local XiaoHongShu daily draft.

The collector is deliberately stdlib-only.  Rendering the four carousel cards
requires Pillow at run time; if it is unavailable the command fails clearly
instead of writing an SVG or a fake PNG with a misleading extension.
"""

from __future__ import annotations

import argparse
import html
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from datetime import date as Date
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo


BEIJING = ZoneInfo("Asia/Shanghai")
SCHEMA_VERSION = 2
DEFAULT_LEDGER_RELATIVE = Path("metrics") / "ledger.json"
DEFAULT_OUTPUT_RELATIVE = Path("drafts") / "xiaohongshu"
EXPERIMENT_META_RELATIVE = Path("metrics") / "experiment.json"
IMAGE_SIZE = (1242, 1660)
IMAGE_NAMES = ("cover.png", "progress.png", "metrics.png", "tomorrow.png")
MONEY_QUANTUM = Decimal("0.01")
PUBLIC_URLS = {
    "homepage": "https://ai-coding-radar.github.io/",
    "robots": "https://ai-coding-radar.github.io/robots.txt",
    "sitemap": "https://ai-coding-radar.github.io/sitemap.xml",
}
GH_CONFIG_DIR = Path.home() / ".config" / "gh-ai-coding-radar"


class DailyReportError(ValueError):
    """Raised when an input is invalid or a draft cannot be generated safely."""


def _parse_date(value: Any) -> Date:
    if isinstance(value, datetime):
        return value.astimezone(BEIJING).date()
    if isinstance(value, Date):
        return value
    try:
        return Date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise DailyReportError("date must be an ISO date (YYYY-MM-DD)") from exc


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(BEIJING)


def _date_matches(value: Any, target: Date) -> bool:
    parsed = _parse_timestamp(value)
    return parsed is not None and parsed.date() == target


def _safe_text(value: Any, *, max_length: int = 500) -> str:
    """Keep evidence as a printable, single-line string."""
    text = unicodedata.normalize("NFC", str(value if value is not None else ""))
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return re.sub(r"\s+", " ", text).strip()[:max_length]


def _markdown_text(value: Any, *, max_length: int = 500) -> str:
    text = html.escape(_safe_text(value, max_length=max_length), quote=False)
    return text.replace("`", "\\`").replace("[", "\\[").replace("]", "\\]")


def _money(value: Any, *, field: str) -> Decimal:
    if isinstance(value, bool) or value is None or value == "":
        if value in (None, ""):
            return Decimal("0")
        raise DailyReportError(f"ledger {field} must be a non-negative number")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DailyReportError(f"ledger {field} must be a non-negative number") from exc
    if not parsed.is_finite() or parsed < 0:
        raise DailyReportError(f"ledger {field} must be a non-negative number")
    return parsed.quantize(MONEY_QUANTUM)


def _money_number(value: Decimal) -> Any:
    value = value.quantize(MONEY_QUANTUM)
    return int(value) if value == value.to_integral_value() else float(value)


def format_money(value: Decimal) -> str:
    value = value.quantize(MONEY_QUANTUM)
    return f"¥{int(value)}" if value == value.to_integral_value() else f"¥{value:.2f}"


def _default_ledger() -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "currency": "CNY",
        "settled_revenue": 0,
        "cost": 0,
        "pending_revenue": 0,
        "estimated_revenue": 0,
        "entries": [],
    }


def _write_text_if_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_file():
        try:
            if path.read_text(encoding="utf-8") == content:
                return
        except (OSError, UnicodeError):
            pass
    path.write_text(content, encoding="utf-8")


def _write_bytes_if_changed(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_file():
        try:
            if path.read_bytes() == content:
                return
        except OSError:
            pass
    path.write_bytes(content)


def _replace_directory(destination: Path, files: Mapping[str, Any]) -> None:
    """Stage a complete draft before replacing the dated directory."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{destination.name}-", dir=destination.parent) as temporary:
        staging = Path(temporary) / destination.name
        staging.mkdir()
        for name, content in files.items():
            path = staging / name
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(str(content), encoding="utf-8")
        if destination.exists():
            existing = {path.name: path.read_bytes() for path in destination.iterdir() if path.is_file()}
            staged = {path.name: path.read_bytes() for path in staging.iterdir() if path.is_file()}
            if existing == staged:
                return
            backup = destination.parent / f".{destination.name}.previous"
            if backup.exists():
                raise DailyReportError(f"stale draft backup exists: {backup}")
            destination.rename(backup)
            try:
                staging.rename(destination)
            except OSError:
                backup.rename(destination)
                raise
            for path in backup.iterdir():
                path.unlink()
            backup.rmdir()
        else:
            staging.rename(destination)


def _validate_destination(destination: Path, report: Mapping[str, Any]) -> None:
    """Fail if a generated draft cannot be safely reused by the scheduler."""
    expected = {"title.txt", "caption.md", "facts.json", *IMAGE_NAMES}
    present = {path.name for path in destination.iterdir() if path.is_file()}
    if present != expected:
        raise DailyReportError(f"draft contract mismatch: expected {sorted(expected)}, found {sorted(present)}")
    try:
        stored = json.loads((destination / "facts.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DailyReportError("generated facts.json is invalid") from exc
    if stored.get("money") != report.get("money"):
        raise DailyReportError("generated money facts do not match the report")
    for name in IMAGE_NAMES:
        data = (destination / name).read_bytes()
        if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 24:
            raise DailyReportError(f"generated image is not a PNG: {name}")
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        if (width, height) != IMAGE_SIZE:
            raise DailyReportError(f"generated image has unexpected dimensions: {name}")


def ensure_ledger(path: Path) -> Dict[str, Any]:
    """Create/load the one explicit money source used by the report."""
    if not path.exists():
        ledger = _default_ledger()
        _write_text_if_changed(path, json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
        return ledger
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DailyReportError(f"cannot read ledger: {path}") from exc
    if not isinstance(value, dict):
        raise DailyReportError("ledger must be a JSON object")
    return value


def _entry_kind(entry: Mapping[str, Any]) -> str:
    return _safe_text(entry.get("kind", entry.get("type", "")), max_length=40).lower().replace("-", "_")


def _entry_status(entry: Mapping[str, Any]) -> str:
    return _safe_text(entry.get("status", ""), max_length=30).lower().replace("-", "_")


def _entry_amount(entry: Mapping[str, Any]) -> Decimal:
    if "amount" not in entry:
        raise DailyReportError("ledger entry is missing amount")
    return _money(entry["amount"], field="entry amount")


def _classify_entry(entry: Mapping[str, Any]) -> Optional[str]:
    """Return settled_revenue, pending_revenue, estimated_revenue, or cost."""
    kind = _entry_kind(entry)
    status = _entry_status(entry)
    if kind in {"cost", "expense", "spend", "fee"}:
        return "cost"
    if kind in {"pending", "pending_revenue"} or status in {"pending", "unsettled", "awaiting"}:
        return "pending_revenue"
    if kind in {"estimated", "estimated_revenue", "forecast"} or status in {"estimated", "forecast"}:
        return "estimated_revenue"
    if kind in {"settled_revenue", "revenue"} and status == "settled":
        return "settled_revenue"
    return None


def summarize_ledger(ledger: Mapping[str, Any], target: Date) -> Dict[str, Any]:
    """Summarize explicit ledger fields; never infer money from activity data."""
    currency = _safe_text(ledger.get("currency", "CNY"), max_length=12) or "CNY"
    entries = ledger.get("entries", []) or []
    if not isinstance(entries, list):
        raise DailyReportError("ledger entries must be a JSON array")
    cumulative = {key: Decimal("0") for key in ("settled_revenue", "pending_revenue", "estimated_revenue", "cost")}
    today = {key: Decimal("0") for key in cumulative}
    warnings: List[str] = []
    entry_count = 0
    if entries:
        for entry in entries:
            if not isinstance(entry, dict):
                raise DailyReportError("each ledger entry must be a JSON object")
            if not entry.get("date"):
                raise DailyReportError("each ledger entry requires an ISO date")
            entry_date = _parse_date(entry["date"])
            category = _classify_entry(entry)
            amount = _entry_amount(entry)
            if category is None:
                if _entry_kind(entry) in {"revenue", "income"}:
                    warnings.append("未标明 settled/pending/estimated 的收入条目未计入收益")
                continue
            if category == "settled_revenue" and not _safe_text(entry.get("receipt", ""), max_length=200):
                raise DailyReportError("settled revenue requires a minimal receipt reference")
            cumulative[category] += amount
            entry_count += 1
            if entry_date == target:
                today[category] += amount
        for key in cumulative:
            if key in ledger and _money(ledger[key], field=key) != cumulative[key]:
                warnings.append(f"账本 {key} 与 entries 合计不一致，已按 entries 计算")
    else:
        for key in cumulative:
            cumulative[key] = _money(ledger.get(key, 0), field=key)

    def block(values: Mapping[str, Decimal]) -> Dict[str, Any]:
        net = values["settled_revenue"] - values["cost"]
        return {
            "settled_revenue": _money_number(values["settled_revenue"]),
            "pending_revenue": _money_number(values["pending_revenue"]),
            "estimated_revenue": _money_number(values["estimated_revenue"]),
            "cost": _money_number(values["cost"]),
            "net": _money_number(net),
        }

    return {
        "currency": currency,
        "source": "metrics/ledger.json",
        "today": block(today),
        "cumulative": block(cumulative),
        "entry_count": entry_count,
        "warnings": warnings,
    }


def _git_commits(project_root: Path, target: Date) -> Tuple[List[Dict[str, str]], List[str]]:
    command = ["git", "-C", str(project_root), "log", "HEAD", "--date=iso-strict", "--pretty=format:%H%x09%cI%x09%s"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=15)
    except (OSError, subprocess.SubprocessError) as exc:
        return [], [f"Git history unavailable: {_safe_text(exc, max_length=180)}"]
    if result.returncode != 0:
        return [], [f"Git history unavailable: {_safe_text(result.stderr or result.stdout, max_length=180)}"]
    commits: List[Dict[str, str]] = []
    seen = set()
    for line in result.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        commit_hash, timestamp, subject = parts
        parsed = _parse_timestamp(timestamp)
        if not parsed or parsed.date() != target or commit_hash in seen:
            continue
        seen.add(commit_hash)
        commits.append({"hash": _safe_text(commit_hash, max_length=64), "timestamp": parsed.isoformat(), "subject": _safe_text(subject, max_length=180)})
    commits.sort(key=lambda item: (item["timestamp"], item["hash"]))
    return commits, []


def _load_jsonl(path: Path, target: Date) -> Tuple[List[Dict[str, Any]], int, List[str]]:
    selected: List[Dict[str, Any]] = []
    warnings: List[str] = []
    total = 0
    if not path.exists():
        return selected, total, [f"未找到运行日志：{path.name}"]
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return selected, total, [f"运行日志不可读：{_safe_text(exc, max_length=120)}"]
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            warnings.append(f"运行日志第 {line_number} 行不是有效 JSON，已跳过")
            continue
        if not isinstance(value, dict):
            warnings.append(f"运行日志第 {line_number} 行不是对象，已跳过")
            continue
        total += 1
        parsed = _parse_timestamp(value.get("time"))
        if parsed and parsed.date() == target:
            selected.append({"time": parsed.isoformat(), "status": _safe_text(value.get("status", "unknown"), max_length=30), "detail": _safe_text(value.get("detail", ""), max_length=220)})
    selected.sort(key=lambda item: item["time"])
    return selected, total, warnings


def _load_state(path: Path, target: Date) -> Tuple[List[Dict[str, Any]], int, List[str]]:
    if not path.exists():
        return [], 0, [f"未找到状态文件：{path.name}"]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [], 0, [f"状态文件不可读：{_safe_text(exc, max_length=120)}"]
    seen = value.get("seen", {}) if isinstance(value, dict) else {}
    if not isinstance(seen, dict):
        return [], 0, ["状态文件中的 seen 不是对象"]
    selected = []
    for raw in seen.values():
        if not isinstance(raw, dict) or not _date_matches(raw.get("detected_at"), target):
            continue
        detected = _parse_timestamp(raw.get("detected_at"))
        selected.append({"source_key": _safe_text(raw.get("source_key", "unknown"), max_length=50), "product": _safe_text(raw.get("product", ""), max_length=100), "version": _safe_text(raw.get("version", ""), max_length=80), "detected_at": detected.isoformat() if detected else ""})
    selected.sort(key=lambda item: (item["detected_at"], item["source_key"], item["version"]))
    return selected, len(seen), []


def _experiment_start(project_root: Path, target: Date) -> Tuple[Date, List[str]]:
    path = project_root / EXPERIMENT_META_RELATIVE
    if path.exists():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict) and value.get("start_date"):
                start = _parse_date(value["start_date"])
                if start > target:
                    raise DailyReportError("experiment start_date cannot be in the future")
                return start, []
        except DailyReportError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DailyReportError("experiment start metadata is invalid") from exc
        raise DailyReportError("experiment start metadata is missing start_date")
    try:
        _write_text_if_changed(path, json.dumps({"schema_version": SCHEMA_VERSION, "start_date": target.isoformat(), "timezone": "Asia/Shanghai"}, ensure_ascii=False, indent=2) + "\n")
        return target, []
    except OSError as exc:
        return target, [f"无法保存实验起始日期：{_safe_text(exc, max_length=120)}"]


def _site_facts(project_root: Path) -> Dict[str, Any]:
    output = project_root / "output"
    files = {name: (output / name).is_file() for name in ("index.html", "robots.txt", "sitemap.xml")}
    urls = 0
    if files["sitemap.xml"]:
        try:
            urls = len(re.findall(r"<loc>[^<]+</loc>", (output / "sitemap.xml").read_text(encoding="utf-8")))
        except (OSError, UnicodeError):
            pass
    http_status: Dict[str, Optional[int]] = {}
    http_error: Optional[str] = None
    for name, url in PUBLIC_URLS.items():
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "AI-Coding-Radar-Daily/1.0"})
            with urllib.request.urlopen(request, timeout=10) as response:
                http_status[name] = response.status
        except (OSError, urllib.error.URLError, ValueError) as exc:
            http_status[name] = None
            http_error = _safe_text(exc, max_length=160)
    http_ok = bool(http_status) and all(status == 200 for status in http_status.values())
    return {
        "public_url": PUBLIC_URLS["homepage"],
        "local_build_ready": all(files.values()),
        "files": files,
        "sitemap_url_count": urls,
        "http_checked": True,
        "http_ok": http_ok,
        "http_status": http_status,
        "note": "公开首页、robots.txt 和 sitemap.xml 均返回 HTTP 200" if http_ok else f"公网检查未全部成功：{http_error or 'non-200 response'}",
    }


def _actions_facts(project_root: Path, target: Date) -> Dict[str, Any]:
    command = [
        "gh",
        "run",
        "list",
        "--repo",
        "ai-coding-radar/ai-coding-radar.github.io",
        "--limit",
        "100",
        "--json",
        "databaseId,name,event,status,conclusion,createdAt,updatedAt,url",
    ]
    try:
        environment = dict(os.environ)
        if GH_CONFIG_DIR.is_dir():
            environment["GH_CONFIG_DIR"] = str(GH_CONFIG_DIR)
        result = subprocess.run(command, cwd=project_root, env=environment, capture_output=True, text=True, check=False, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "today_count": 0, "success_count": 0, "failure_count": 0, "runs": [], "note": f"GitHub Actions 不可读：{_safe_text(exc, max_length=140)}"}
    if result.returncode != 0:
        detail = _safe_text(result.stderr or result.stdout, max_length=160)
        return {"available": False, "today_count": 0, "success_count": 0, "failure_count": 0, "runs": [], "note": f"GitHub Actions 不可读：{detail or 'gh failed'}"}
    try:
        values = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"available": False, "today_count": 0, "success_count": 0, "failure_count": 0, "runs": [], "note": "GitHub Actions 返回了无效 JSON"}
    selected = []
    for raw in values if isinstance(values, list) else []:
        if not isinstance(raw, dict) or not _date_matches(raw.get("createdAt"), target):
            continue
        selected.append({
            "id": raw.get("databaseId"),
            "name": _safe_text(raw.get("name", ""), max_length=80),
            "event": _safe_text(raw.get("event", ""), max_length=30),
            "status": _safe_text(raw.get("status", ""), max_length=30),
            "conclusion": _safe_text(raw.get("conclusion", ""), max_length=30),
            "created_at": _parse_timestamp(raw.get("createdAt")).isoformat(),
            "url": _safe_text(raw.get("url", ""), max_length=260),
        })
    selected.sort(key=lambda item: (item["created_at"], item["id"] or 0))
    success_count = sum(item["conclusion"] == "success" for item in selected)
    failure_count = sum(item["conclusion"] not in {"", "success", "skipped"} for item in selected)
    return {
        "available": True,
        "today_count": len(selected),
        "success_count": success_count,
        "failure_count": failure_count,
        "runs": selected,
        "note": f"今日 GitHub Actions {len(selected)} 次，成功 {success_count} 次",
    }


def _search_facts(project_root: Path) -> Dict[str, Any]:
    for relative in (Path("metrics/search.json"), Path("metrics/search-console.json")):
        path = project_root / relative
        if not path.exists():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            explicit_note = _safe_text(value.get("note", ""), max_length=400)
            sitemap = value.get("sitemap") if isinstance(value.get("sitemap"), dict) else {}
            status = _safe_text(sitemap.get("status", ""), max_length=80)
            note = explicit_note or (
                f"Search Console sitemap 状态：{status}"
                if status
                else "来自显式本地搜索数据文件"
            )
            return {"available": True, "source": str(relative), "data": value, "note": note}
    return {"available": False, "source": None, "impressions": None, "clicks": None, "note": "未找到 Search Console 导出，未推断流量或收录"}


def _completed(commits: Sequence[Mapping[str, str]], runs: Sequence[Mapping[str, Any]], releases: Sequence[Mapping[str, Any]], site: Mapping[str, Any], actions: Mapping[str, Any]) -> List[str]:
    lines: List[str] = []
    if commits:
        lines.append(f"完成 {len(commits)} 个 Git 变更：{commits[-1]['subject']}")
    if releases:
        products = Counter(item.get("product", "未知工具") for item in releases)
        lines.append("自动发现 " + "、".join(f"{name} {count} 项" for name, count in products.items()))
    if runs:
        status = Counter(item.get("status", "unknown") for item in runs)
        lines.append(f"自动运行 {len(runs)} 次（" + "、".join(f"{key} {value}" for key, value in sorted(status.items())) + "）")
    if actions.get("available") and actions.get("today_count"):
        lines.append(f"GitHub Actions 成功 {actions['success_count']}/{actions['today_count']} 次")
    if not lines and site.get("local_build_ready"):
        lines.append("核对本地站点构建产物")
    return lines[:3]


def _facts_json(target: Date, day_index: int, commits: List[Dict[str, str]], runs: List[Dict[str, Any]], run_total: int, releases: List[Dict[str, Any]], state_total: int, money: Dict[str, Any], site: Dict[str, Any], search: Dict[str, Any], actions: Dict[str, Any], warnings: List[str]) -> Dict[str, Any]:
    status_counts = Counter(str(item.get("status", "unknown")) for item in runs)
    return {
        "schema_version": SCHEMA_VERSION,
        "date": target.isoformat(),
        "timezone": "Asia/Shanghai",
        "day_index": day_index,
        "completed": _completed(commits, runs, releases, site, actions),
        "git": {"today_count": len(commits), "commits": commits},
        "runs": {"today_count": len(runs), "total_count": run_total, "status_counts": {key: status_counts[key] for key in sorted(status_counts)}, "entries": runs},
        "state": {"today_new_count": len(releases), "total_count": state_total, "records": releases},
        "site": site,
        "actions": actions,
        "search": search,
        "money": money,
        "warnings": warnings + list(money.get("warnings", [])),
    }


def _caption(report: Mapping[str, Any]) -> str:
    money = report["money"]
    today = money["today"]
    cumulative = money["cumulative"]
    lines = [
        f"# Day {report['day_index']}｜把一台电脑交给 AI 的第 {report['day_index']} 天",
        "",
        f"这是自动化副业实验的 {report['date']} 日报（Asia/Shanghai）。只写仓库和显式账本里的事实。",
        "",
        "## 今日完成",
    ]
    lines.extend(f"- {_markdown_text(item)}" for item in report["completed"])
    if not report["completed"]:
        lines.append("- 今天没有检测到可核对的完成项")
    lines.extend([
        "",
        "## 自动化与流量事实",
        f"- 今日 Git 提交：{report['git']['today_count']} 个；累计状态记录：{report['state']['total_count']} 条，今日新增 {report['state']['today_new_count']} 条。",
        f"- 今日自动运行：{report['runs']['today_count']} 次；日志总记录：{report['runs']['total_count']} 次。",
        *([f"- 最近运行备注：{_markdown_text(report['runs']['entries'][-1].get('detail', ''))}"] if report["runs"]["entries"] and report["runs"]["entries"][-1].get("detail") else []),
        f"- 本地站点构建：{'就绪' if report['site']['local_build_ready'] else '不完整'}；sitemap 本地 URL：{report['site']['sitemap_url_count']} 条。",
        f"- 公网站点：{_markdown_text(report['site']['note'])}。",
        f"- GitHub Actions：{_markdown_text(report['actions']['note'])}。",
        f"- 搜索/收录：{_markdown_text(report['search']['note'])}。",
        "",
        "## 收益账本",
        f"- 今日已结算到账：**{format_money(Decimal(str(today['settled_revenue'])))}**",
        f"- 今日 pending：{format_money(Decimal(str(today['pending_revenue'])))}；estimated：{format_money(Decimal(str(today['estimated_revenue'])))}",
        f"- 累计已结算到账：**{format_money(Decimal(str(cumulative['settled_revenue'])))}**",
        f"- 累计成本：**{format_money(Decimal(str(cumulative['cost'])))}**",
        "收益只认 `metrics/ledger.json` 中实际到账且标记为 settled 的条目；部署、曝光、点击、预计佣金和节省时间都不是收益。",
        "",
        "## 明天系统动作",
        "继续抓取官方源、更新站点，并在 20:00 生成下一份草稿；未核验到普通创作者官方发布接口，不自动登录或发布。",
    ])
    warnings = report.get("warnings", [])
    if warnings:
        lines.extend(["", "## 数据提醒"])
        lines.extend(f"- {_markdown_text(warning)}" for warning in warnings[:8])
    return "\n".join(lines).rstrip() + "\n"


def _require_pillow() -> Tuple[Any, Any, Any]:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise DailyReportError("生成四张真实 PNG 需要 Pillow；请先安装 Pillow（未写入伪 PNG）") from exc
    return Image, ImageDraw, ImageFont


def _font(ImageFont: Any, size: int) -> Any:
    candidates = (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for candidate in candidates:
        try:
            if Path(candidate).exists():
                return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_text(draw: Any, xy: Tuple[int, int], text: str, font: Any, fill: str, **kwargs: Any) -> None:
    try:
        draw.text(xy, text, font=font, fill=fill, **kwargs)
    except UnicodeEncodeError:
        # DejaVu's fallback font has no CJK glyphs on some minimal systems.
        draw.text(xy, text.encode("ascii", "replace").decode("ascii"), font=font, fill=fill, **kwargs)


def _wrap_lines(text: str, width: int = 22) -> List[str]:
    return textwrap.wrap(_safe_text(text), width=width, break_long_words=False, break_on_hyphens=False)


def _render_card(Image: Any, ImageDraw: Any, ImageFont: Any, title: str, kicker: str, number: str, body: Sequence[str], accent: str, footer: str) -> bytes:
    image = Image.new("RGB", IMAGE_SIZE, "#f4efdf")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((42, 42, 1200, 1618), radius=22, outline="#151515", width=5)
    draw.rectangle((42, 42, 1200, 64), fill=accent)
    draw.ellipse((970, 120, 1120, 270), fill=accent, outline="#151515", width=4)
    kicker_font = _font(ImageFont, 31)
    title_font = _font(ImageFont, 76)
    number_font = _font(ImageFont, 156)
    body_font = _font(ImageFont, 43)
    footer_font = _font(ImageFont, 27)
    _draw_text(draw, (92, 136), kicker, kicker_font, "#ff5a36")
    _draw_text(draw, (92, 250), title, title_font, "#151515")
    _draw_text(draw, (92, 485), number, number_font, accent)
    y = 820
    for paragraph in body:
        for line in _wrap_lines(paragraph):
            _draw_text(draw, (96, y), line, body_font, "#151515")
            y += 68
        y += 24
    draw.line((92, 1430, 1148, 1430), fill="#151515", width=4)
    _draw_text(draw, (92, 1474), footer, footer_font, "#5b5b55")
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False)
    return output.getvalue()


def _render_images(report: Mapping[str, Any], pillow: Tuple[Any, Any, Any]) -> Dict[str, bytes]:
    Image, ImageDraw, ImageFont = pillow
    money = report["money"]["today"]
    return {
        "cover.png": _render_card(Image, ImageDraw, ImageFont, "AI 今天干了什么", f"DAY {report['day_index']} · 自动化副业实验", format_money(Decimal(str(money["settled_revenue"]))), (f"今日真实收益 {format_money(Decimal(str(money['settled_revenue'])))}", "不出门，也不手动发帖"), "#d8ff47", f"{report['date']} · 只认实际到账"),
        "progress.png": _render_card(Image, ImageDraw, ImageFont, "今天做了什么", "仓库证据", str(report["git"]["today_count"]), (f"Git 提交 {report['git']['today_count']} 个", f"稳定版新增 {report['state']['today_new_count']} 条"), "#ff5a36", "事实来自 Git、状态文件和运行日志"),
        "metrics.png": _render_card(Image, ImageDraw, ImageFont, "自动化状态", "无人值守", str(report["runs"]["today_count"]), (f"今日运行 {report['runs']['today_count']} 次", f"累计状态记录 {report['state']['total_count']} 条"), "#8ec5ff", "搜索数据缺失时明确写未找到，不做推断"),
        "tomorrow.png": _render_card(Image, ImageDraw, ImageFont, "真实收益", "只认账本", format_money(Decimal(str(money["settled_revenue"]))), (f"pending {format_money(Decimal(str(money['pending_revenue'])))} · estimated {format_money(Decimal(str(money['estimated_revenue'])))}", "没有实际到账就记录为 ¥0"), "#ffcc66", "明天：继续自动抓取、更新和生成草稿"),
    }


def generate_daily_report(target_date: Any = None, project_root: Optional[Path] = None, output_dir: Optional[Path] = None, ledger_path: Optional[Path] = None) -> Path:
    """Generate ``drafts/xiaohongshu/YYYY-MM-DD`` and return its path."""
    pillow = _require_pillow()
    target = _parse_date(target_date if target_date is not None else datetime.now(BEIJING))
    root = Path(project_root or Path(__file__).resolve().parents[1]).resolve()
    destination_root = Path(output_dir) if output_dir is not None else root / DEFAULT_OUTPUT_RELATIVE
    destination = destination_root / target.isoformat()
    ledger_file = Path(ledger_path) if ledger_path is not None else root / DEFAULT_LEDGER_RELATIVE

    commits, commit_warnings = _git_commits(root, target)
    runs, run_total, run_warnings = _load_jsonl(root / "logs" / "runs.jsonl", target)
    releases, state_total, state_warnings = _load_state(root / "state" / "seen.json", target)
    ledger = summarize_ledger(ensure_ledger(ledger_file), target)
    start, start_warnings = _experiment_start(root, target)
    site = _site_facts(root)
    search = _search_facts(root)
    actions = _actions_facts(root, target)
    warnings = commit_warnings + run_warnings + state_warnings + start_warnings
    report = _facts_json(target, max(1, (target - start).days + 1), commits, runs, run_total, releases, state_total, ledger, site, search, actions, warnings)

    title = f"自动化副业实验｜Day {report['day_index']}｜{target.isoformat()}\n"
    caption = _caption(report)
    facts = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    images = _render_images(report, pillow)

    files: Dict[str, Any] = {"title.txt": title, "caption.md": caption, "facts.json": facts}
    files.update(images)
    _replace_directory(destination, files)
    _validate_destination(destination, report)
    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", dest="target_date", help="Beijing date, YYYY-MM-DD")
    parser.add_argument("--project-root", type=Path, help="Repository root (default: this project)")
    parser.add_argument("--output-dir", type=Path, help="Draft parent (default: drafts/xiaohongshu)")
    parser.add_argument("--ledger-path", type=Path, help="Override ledger path for tests or a separate checkout")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        print(generate_daily_report(args.target_date, args.project_root, args.output_dir, args.ledger_path))
    except DailyReportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
