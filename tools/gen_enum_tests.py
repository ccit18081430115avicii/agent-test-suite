
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全自动①：边界值/组合覆盖/变异/模糊 生成 tests_enum.json
针对“读取一行包含两个整数并输出其和”的示例程序，可按需替换为你的业务。
"""
import json, itertools

def add_oracle(a: int, b: int) -> str:
    return f"{a + b}\n"

def cases():
    numbers = [0, 1, 2, 9, 10, 99, 100, 10**6, -1, -999999]
    whites  = [" ", "  ", "\t", "   "]
    # 边界 + 组合覆盖
    for a, b in itertools.product(numbers, numbers):
        for ws in whites:
            yield f"{a}{ws}{b}\n", add_oracle(a, b)

    # 变异/模糊样例（格式扰动/非法输入）
    weird_inputs = [
        "001 2\n",
        "1    2\n",
        "1\t\t2\n",
        " 1 2 \n",
        "1\n2\n",
        "1,2\n",
        "a b\n",
        "\n",
    ]
    for s in weird_inputs:
        if "," in s or "a" in s:
            yield s, "ERR\n"
        else:
            parts = s.split()
            if len(parts) >= 2 and all(p.lstrip("-").isdigit() for p in parts[:2]):
                yield s, add_oracle(int(parts[0]), int(parts[1]))

def main():
    tests = []
    for i, (inp, exp) in enumerate(cases(), 1):
        tests.append({
            "name": f"auto-enum-{i}",
            "input": inp,
            "expected": exp,
            "timeout": 2,
            "normalize": {"strip": True, "collapse_ws": True}
        })
    with open("tests_enum.json", "w", encoding="utf-8") as f:
        json.dump(tests, f, ensure_ascii=False, indent=2)
    print(f"已生成 {len(tests)} 条枚举用例到 tests_enum.json")

if __name__ == "__main__":
    main()
