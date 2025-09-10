
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把多种常见日志格式抽取为 tests.json：
支持3种输入：
1) 纯文本行：IN:<...> OUT:<...>
2) JSON 行：{"input": "...", "expected": "..."}  （一行一个 JSON）
3) CI 存档文本块：---CASE---、INPUT:\n...\nEXPECTED:\n...
用法：python tools/log2tests.py --in app.log --out tests.json --name-prefix "regression-" --strip
"""
import argparse, json, re, uuid, sys

pat_text = re.compile(r"IN\s*:\s*(?P<input>.*?)\s*OUT\s*:\s*(?P<expected>.*)$")
pat_ci   = re.compile(r"---CASE---.*?INPUT:\s*(?P<input>.*?)\n+EXPECTED:\s*(?P<expected>.*?)\n(?=---CASE---|$)", re.S)

def parse_lines(raw: str):
    cases = []
    # JSON 行
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and "input" in obj and "expected" in obj:
                cases.append((obj["input"], obj["expected"]))
                continue
        except Exception:
            pass
        # 文本行：IN:... OUT:...
        m = pat_text.search(line)
        if m:
            inp, exp = m.group("input"), m.group("expected")
            if not inp.endswith("\n"): inp += "\n"
            if not exp.endswith("\n"): exp += "\n"
            cases.append((inp, exp))
    # CI 文本块
    for m in pat_ci.finditer(raw):
        cases.append((m.group("input"), m.group("expected")))
    return cases

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True, help="日志/CI/JSON行 文件路径")
    ap.add_argument("--out", dest="out_path", default="tests.json")
    ap.add_argument("--name-prefix", default="regress-")
    ap.add_argument("--strip", action="store_true", help="默认对期望/实际做strip和折叠空白")
    args = ap.parse_args()

    raw = open(args.in_path, "r", encoding="utf-8", errors="ignore").read()
    pairs = parse_lines(raw)
    if not pairs:
        print("未解析到任何 (input, expected)。请检查日志格式。", file=sys.stderr)
        sys.exit(1)

    tests = []
    for i, (inp, exp) in enumerate(pairs, 1):
        tests.append({
            "name": f"{args.name_prefix}{i}-{uuid.uuid4().hex[:6]}",
            "input": inp if inp.endswith("\n") else inp + "\n",
            "expected": exp if exp.endswith("\n") else exp + "\n",
            "timeout": 2,
            "normalize": {"strip": True, "collapse_ws": True} if args.strip else {"strip": True}
        })

    with open(args.out_path, "w", encoding="utf-8") as f:
        json.dump(tests, f, ensure_ascii=False, indent=2)
    print(f"生成 {len(tests)} 条用例到 {args.out_path}")

if __name__ == "__main__":
    main()
