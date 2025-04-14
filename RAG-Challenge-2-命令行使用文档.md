# RAG-Challenge-2 命令行使用文档

## 概述

RAG-Challenge-2 提供了一套完整的命令行工具，用于处理PDF企业报告并回答相关问题。该系统使用检索增强生成（RAG）技术，结合大型语言模型来解析文档并生成答案。

## 安装

首先，确保已经安装了所有依赖：

```bash
pip install -r requirements.txt
```

## 命令行使用

所有命令都应该在项目根目录下运行。

### 基本用法

```bash
python main.py [命令] [选项]
```

### 可用命令

#### 1. 下载必要模型

下载处理PDF文档所需的docling模型。

```bash
python main.py download-models
```

#### 2. 解析PDF报告

将PDF报告解析为结构化JSON格式。

```bash
python main.py parse-pdfs [选项]
```

**选项：**
- `--parallel/--sequential`: 是否使用并行处理模式（默认：并行）
- `--chunk-size INTEGER`: 每个工作进程处理的PDF数量（默认：2）
- `--max-workers INTEGER`: 并行工作进程数量（默认：10）

**示例：**
```bash
# 使用默认设置（并行模式）,到 data/test_set/目录下执行
python ../../main.py parse-pdfs

# 使用顺序处理模式
python ../../main.py parse-pdfs --sequential

# 自定义并行处理参数
python ../../main.py parse-pdfs --parallel --chunk-size=3 --max-workers=8
```

#### 3. 表格序列化

对已解析报告中的表格进行序列化处理。

```bash
python main.py serialize-tables [选项]
```

**选项：**
- `--max-workers INTEGER`: 表格序列化的工作线程数（默认：10）

**示例：**
```bash
# 使用默认设置
python main.py serialize-tables

# 自定义工作线程数
python main.py serialize-tables --max-workers=5
```

#### 4. 处理已解析的报告

将已解析的报告通过整个处理管道，包括合并、导出Markdown、分块和创建向量数据库。

```bash
python main.py process-reports [选项]
```

**选项：**
- `--config [ser_tab|no_ser_tab]`: 要使用的配置预设（默认：no_ser_tab）
  - `ser_tab`: 使用序列化表格
  - `no_ser_tab`: 不使用序列化表格

**示例：**
```bash
# 不使用序列化表格（默认）
python main.py process-reports

# 使用序列化表格
python main.py process-reports --config=ser_tab
```

#### 5. 处理问题

处理问题并生成答案。

```bash
python main.py process-questions [选项]
```

**选项：**
- `--config [base|pdr|max|max_no_ser_tab|max_nst_o3m|max_st_o3m|ibm_llama70b|ibm_llama8b|gemini_thinking]`: 要使用的配置预设（默认：base）

**配置说明：**
- `base`: 基础配置，使用GPT-4o-mini
- `pdr`: 启用父文档检索，使用GPT-4o
- `max`: 最大配置，包括表格序列化、父文档检索和重排，使用GPT-4o
- `max_no_ser_tab`: 与max相同但不使用表格序列化
- `max_nst_o3m`: 不使用表格序列化，使用Claude 3 Opus Mini（推荐配置）
- `max_st_o3m`: 使用表格序列化，使用Claude 3 Opus Mini
- `ibm_llama70b`: 使用IBM WatsonX的Llama 3.3 70B模型
- `ibm_llama8b`: 使用IBM WatsonX的Llama 3.1 8B模型
- `gemini_thinking`: 使用Google Gemini的Thinking模型

**示例：**
```bash
# 使用基础配置
python main.py process-questions

# 使用推荐配置（max_nst_o3m）
python main.py process-questions --config=max_nst_o3m

# 使用父文档检索配置
python main.py process-questions --config=pdr
```

## 完整处理流程

以下是处理PDF报告并回答问题的完整流程示例：

```bash
# 1. 下载必要的模型
python main.py download-models

# 2. 解析PDF报告
python main.py parse-pdfs --parallel --max-workers=8

# 3. （可选）序列化表格，仅当选择的配置需要时
python main.py serialize-tables

# 4. 处理报告 - 选择适当的配置
python main.py process-reports --config=no_ser_tab

# 5. 处理问题 - 选择适当的配置
python main.py process-questions --config=max_nst_o3m
```

## 输出文件

处理完成后，系统将在`data/test_set`目录中生成以下文件：

- 解析后的报告: `debug_data/01_parsed_reports/`
- 合并后的报告: `debug_data/02_merged_reports/`
- Markdown格式的报告: `debug_data/03_reports_markdown/`
- 分块后的报告: `databases/chunked_reports/`
- 向量数据库: `databases/vector_dbs/`
- 答案文件: `answers_{config_suffix}.json`

## 故障排除

### 找不到模块错误

如果遇到`ModuleNotFoundError: No module named 'src'`错误，请确保从项目根目录运行命令。

### 内存错误

处理大型PDF文件时可能遇到内存错误，可以尝试：
- 减少`max-workers`参数值
- 使用较小的`chunk-size`值
- 增加系统可用内存

### API密钥错误

如果使用需要API密钥的配置（如OpenAI、IBM或Google），请确保在`.env`文件中设置了正确的API密钥：

```
OPENAI_API_KEY=your_openai_api_key
IBM_API_KEY=your_ibm_api_key
GEMINI_API_KEY=your_gemini_api_key
```

# 在文件顶部添加
import ssl
ssl._create_default_https_context = ssl._create_unverified_context 