# RAG-Challenge-2 使用文档

## 系统概述

RAG-Challenge-2 是一个基于检索增强生成（Retrieval-Augmented Generation, RAG）的企业报告问答系统。该系统可以解析PDF格式的企业报告，提取和处理文本内容，并使用大型语言模型（LLM）回答关于这些报告的问题。

整个系统分为以下几个主要组件：
- PDF解析器：解析企业PDF报告并提取结构化内容
- 文本处理：合并和准备从PDF中提取的文本
- 文本分块：将长文本分割成合适大小的块
- 向量数据库：创建文本块的向量表示用于语义搜索
- 问题处理：检索相关内容并使用LLM生成答案

## 安装指南

### 环境要求
- Python 3.8+ 
- 足够的磁盘空间用于存储PDF报告和处理后的数据
- 网络连接（用于下载模型和API调用）

### 安装步骤

1. 克隆代码库：
```bash
git clone https://github.com/your-username/RAG-Challenge-2.git
cd RAG-Challenge-2
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 设置API密钥（如果需要使用OpenAI、IBM WatsonX或Google Gemini）：
在项目根目录创建`.env`文件并添加您的API密钥：
```
OPENAI_API_KEY=your_openai_api_key
IBM_API_KEY=your_ibm_api_key
GEMINI_API_KEY=your_gemini_api_key
```

## 配置说明

系统提供多种预定义配置，您可以根据需要选择或自定义：

| 配置名称 | 描述 |
|---------|------|
| base | 基础配置，使用GPT-4o-mini |
| pdr | 启用父文档检索，使用GPT-4o |
| max | 最大配置，包括表格序列化、父文档检索和重排 |
| max_nst_o3m | 推荐配置，使用Claude 3 Opus Mini |

### 自定义配置

您可以通过修改`src/pipeline.py`中的配置类来自定义配置：

```python
custom_config = RunConfig(
    use_serialized_tables=True,  # 是否使用序列化表格
    parent_document_retrieval=True,  # 是否启用父文档检索
    llm_reranking=True,  # 是否使用LLM重排
    parallel_requests=20,  # 并行请求数
    api_provider="openai",  # API提供商：openai, ibm, gemini
    answering_model="gpt-4o-2024-08-06",  # 使用的模型
    config_suffix="_custom"  # 配置后缀，用于文件命名
)
```

## 使用步骤

### 准备数据

1. 在`data/test_set/pdf_reports`目录中放置PDF报告文件
2. 在`data/test_set`目录中准备`subset.csv`文件（包含PDF元数据）
3. 在`data/test_set`目录中准备`questions.json`文件（包含要回答的问题）

### 运行完整管道

从项目根目录运行以下命令处理所有步骤：

```bash
python -m src.pipeline
```

或者使用特定配置：

```bash
python main.py run-pipeline --config max_nst_o3m
```

### 单独步骤运行

如果您想单独运行某个步骤，可以在`src/pipeline.py`中取消注释相应的方法，或使用以下命令：

1. **解析PDF报告**：
```bash
python main.py parse-pdfs --config max_nst_o3m
```

2. **序列化表格**（仅当配置需要时）：
```bash
python main.py serialize-tables --config max_nst_o3m
```

3. **合并报告**：
```bash
python main.py merge-reports --config max_nst_o3m
```

4. **导出Markdown格式**：
```bash
python main.py export-to-markdown --config max_nst_o3m
```

5. **分块报告**：
```bash
python main.py chunk-reports --config max_nst_o3m
```

6. **创建向量数据库**：
```bash
python main.py create-vector-dbs --config max_nst_o3m
```

7. **处理问题**：
```bash
python main.py process-questions --config max_nst_o3m
```

## 输出结果

处理完成后，系统将在`data/test_set`目录中生成`answers_{config_suffix}.json`文件，包含所有问题的答案。

每次运行时都会创建一个日志文件`pipeline_YYYYMMDD_HHMMSS.log`，记录处理过程中的详细信息。

## 目录结构

处理过程中生成的数据将保存在以下目录结构中：

```
data/test_set/
├── debug_data/
│   ├── 01_parsed_reports/         # 解析后的报告
│   ├── 01_parsed_reports_debug/   # 解析详细信息（调试用）
│   ├── 02_merged_reports/         # 合并后的报告
│   └── 03_reports_markdown/       # Markdown格式的报告
├── databases/
│   ├── vector_dbs/                # 向量数据库
│   ├── chunked_reports/           # 分块后的报告
│   └── bm25_dbs/                  # BM25数据库（如果使用）
├── pdf_reports/                   # 原始PDF报告
├── subset.csv                     # 报告元数据
├── questions.json                 # 问题列表
└── answers_{config_suffix}.json   # 生成的答案
```

## 故障排除

### 导入错误

如果遇到`ModuleNotFoundError: No module named 'src'`错误，请确保从项目根目录运行命令：

```bash
cd /path/to/RAG-Challenge-2
python -m src.pipeline
```

### 找不到报告错误

如果遇到`No report found with 'Company' company name`错误，请检查：

1. PDF报告文件是否正确放置在`data/test_set/pdf_reports`目录中
2. 是否按顺序运行了所有处理步骤
3. `subset.csv`文件是否包含正确的公司名称和文件名映射

### 内存错误

处理大型PDF报告时可能遇到内存错误，可以尝试：

1. 增加系统内存
2. 调整并行处理参数，减少`max_workers`或`parallel_requests`
3. 使用较小的分块大小

## 高级用法

### 使用不同的语言模型

系统支持多种LLM提供商：
- OpenAI（GPT-4o，GPT-4o-mini等）
- IBM WatsonX（Llama 3系列）
- Google Gemini（Flash，Thinking等）

要更改使用的模型，修改配置中的`api_provider`和`answering_model`参数。

### 自定义处理流程

高级用户可以通过继承`Pipeline`类创建自定义处理流程：

```python
class CustomPipeline(Pipeline):
    def __init__(self, root_path: Path, run_config: RunConfig = RunConfig()):
        super().__init__(root_path, run_config=run_config)
    
    # 添加或覆盖方法
    def custom_process(self):
        self.logger.info("执行自定义处理")
        # 自定义逻辑
```