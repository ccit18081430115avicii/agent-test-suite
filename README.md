
# Agent Test Suite — 带 LLM 分析的智能测试工具

## 亮点
- 批量用例执行 + 规范化比对（strip / collapse_ws / lower / sort_lines / regex_extract）
- 失败时可调用 LLM 自动分析根因与修复建议
- 一键生成 JUnit 报告，CI/CD 友好
- 用例来源多样：手工、日志/CI沉淀（半自动）、枚举/模糊/LLM（全自动）

## 快速开始
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip pyyaml junit-xml openai
python agent_test_tool.py --init   # 生成 tests.json + sample_prog.py
python agent_test_tool.py --cmd "python sample_prog.py" --tests tests.json --junit reports/junit.xml
```

## 生成用例
- 半自动（日志 → 用例）
```bash
python tools/log2tests.py --in app.log --out tests_from_logs.json --strip
```

- 全自动①（枚举/变异/模糊）
```bash
python tools/gen_enum_tests.py  # 输出 tests_enum.json
```

- 全自动②（LLM）
```bash
export OPENAI_API_KEY=...  # 或配置 OPENAI_BASE_URL/AGENT_MODEL
python tools/gen_llm_inputs.py     # tests_llm.json
# 或
python tools/gen_llm_io.py         # tests_llm_clean.json
```

## 运行与报告
```bash
python agent_test_tool.py --cmd "python sample_prog.py" --tests tests_enum.json --junit reports/junit.xml
```

## 设计原则
- 把 LLM 当“生成器”，不用它当“判官”。期望由参考实现/规约计算，或用 metamorphic/属性测试校验。
- 输入空间系统化：边界值、等价类、pairwise、模糊/变异。
- 去重、失败率阈值、覆盖优先级，控制用例规模与质量。
