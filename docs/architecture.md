# 定向纠错框架

本工程采用三层结构：

1. MinerU 产物层
   - 复用现有 `_verification`、`_pages`、`_mineru_pages`
   - 读取页级 `content_list.json`、Markdown、页拆分 PDF
2. 大模型复核层
   - `qwen3-vl-235b-a22b-instruct` 主审
   - `abab6.5-chat` 互评
   - `gemini-2.5-flash` 最终裁决
3. 程序化修正层
   - 规则判断是否允许自动修改
   - DOM 最小化 patch
   - 输出审计报告与待人工确认列表

当前版本先落可运行框架：

- 扫描案例目录
- 读取旧验证报告
- 从 MinerU 中间产物构造证据包
- 生成三阶段复核任务骨架
- 生成 patch plan / needs review 审计文件

真正的模型调用和 HTML 精准单元格修改已预留到独立模块，不再把所有逻辑堆到单个脚本里。
