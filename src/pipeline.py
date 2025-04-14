from dataclasses import dataclass
from pathlib import Path
from pyprojroot import here
import logging
import os
import json
import pandas as pd
import time
from datetime import datetime

from src.pdf_parsing import PDFParser
from src.parsed_reports_merging import PageTextPreparation
from src.text_splitter import TextSplitter
from src.ingestion import VectorDBIngestor
from src.ingestion import BM25Ingestor
from src.questions_processing import QuestionsProcessor
from src.tables_serialization import TableSerializer

@dataclass
class PipelineConfig:
    def __init__(self, root_path: Path, subset_name: str = "subset.csv", questions_file_name: str = "questions.json", pdf_reports_dir_name: str = "pdf_reports", serialized: bool = False, config_suffix: str = ""):
        self.root_path = root_path
        suffix = "_ser_tab" if serialized else ""

        self.subset_path = root_path / subset_name
        self.questions_file_path = root_path / questions_file_name
        self.pdf_reports_dir = root_path / pdf_reports_dir_name
        
        self.answers_file_path = root_path / f"answers{config_suffix}.json"       
        self.debug_data_path = root_path / "debug_data"
        self.databases_path = root_path / f"databases{suffix}"
        
        self.vector_db_dir = self.databases_path / "vector_dbs"
        self.documents_dir = self.databases_path / "chunked_reports"
        self.bm25_db_path = self.databases_path / "bm25_dbs"

        self.parsed_reports_dirname = "01_parsed_reports"
        self.parsed_reports_debug_dirname = "01_parsed_reports_debug"
        self.merged_reports_dirname = f"02_merged_reports{suffix}"
        self.reports_markdown_dirname = f"03_reports_markdown{suffix}"

        self.parsed_reports_path = self.debug_data_path / self.parsed_reports_dirname
        self.parsed_reports_debug_path = self.debug_data_path / self.parsed_reports_debug_dirname
        self.merged_reports_path = self.debug_data_path / self.merged_reports_dirname
        self.reports_markdown_path = self.debug_data_path / self.reports_markdown_dirname

@dataclass
class RunConfig:
    use_serialized_tables: bool = False
    parent_document_retrieval: bool = False
    use_vector_dbs: bool = True
    use_bm25_db: bool = False
    llm_reranking: bool = False
    llm_reranking_sample_size: int = 30
    top_n_retrieval: int = 10
    parallel_requests: int = 10
    team_email: str = "79250515615@yandex.com"
    submission_name: str = "Ilia_Ris vDB + SO CoT"
    pipeline_details: str = ""
    submission_file: bool = True
    full_context: bool = False
    api_provider: str = "openai"
    answering_model: str = "gpt-4o-mini-2024-07-18" #or "gpt-4o-2024-08-06"
    config_suffix: str = ""

# 配置日志格式
def setup_logging(log_level=logging.INFO):
    """设置日志配置"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        ]
    )
    return logging.getLogger('pipeline')

class Pipeline:
    def __init__(self, root_path: Path, subset_name: str = "subset.csv", questions_file_name: str = "questions.json", pdf_reports_dir_name: str = "pdf_reports", run_config: RunConfig = RunConfig()):
        self.logger = setup_logging()
        self.logger.info(f"初始化Pipeline，运行配置: {run_config}")
        self.run_config = run_config
        self.paths = self._initialize_paths(root_path, subset_name, questions_file_name, pdf_reports_dir_name)
        self._convert_json_to_csv_if_needed()

    def _initialize_paths(self, root_path: Path, subset_name: str, questions_file_name: str, pdf_reports_dir_name: str) -> PipelineConfig:
        """Initialize paths configuration based on run config settings"""
        self.logger.debug(f"初始化路径配置，root_path: {root_path}")
        return PipelineConfig(
            root_path=root_path,
            subset_name=subset_name,
            questions_file_name=questions_file_name,
            pdf_reports_dir_name=pdf_reports_dir_name,
            serialized=self.run_config.use_serialized_tables,
            config_suffix=self.run_config.config_suffix
        )

    def _convert_json_to_csv_if_needed(self):
        """
        Checks if subset.json exists in root dir and subset.csv is absent.
        If so, converts the JSON to CSV format.
        """
        json_path = self.paths.root_path / "subset.json"
        csv_path = self.paths.root_path / "subset.csv"
        
        if json_path.exists() and not csv_path.exists():
            self.logger.info(f"发现subset.json但未找到subset.csv，正在转换格式")
            try:
                with open(json_path, 'r') as f:
                    data = json.load(f)
                
                df = pd.DataFrame(data)
                
                df.to_csv(csv_path, index=False)
                self.logger.info(f"JSON转CSV成功: {csv_path}")
                
            except Exception as e:
                self.logger.error(f"JSON转CSV出错: {str(e)}", exc_info=True)

    @staticmethod
    def download_docling_models(): 
        logger = setup_logging()
        logger.info("开始下载docling模型")
        start_time = time.time()
        parser = PDFParser(output_dir=here())
        parser.parse_and_export(input_doc_paths=[here() / "src/dummy_report.pdf"])
        logger.info(f"docling模型下载完成，耗时: {time.time() - start_time:.2f}秒")

    def parse_pdf_reports_sequential(self):
        self.logger.info("开始顺序解析PDF报告")
        start_time = time.time()
        
        pdf_parser = PDFParser(
            output_dir=self.paths.parsed_reports_path,
            csv_metadata_path=self.paths.subset_path
        )
        pdf_parser.debug_data_path = self.paths.parsed_reports_debug_path
        
        self.logger.info(f"解析目标目录: {self.paths.pdf_reports_dir}")    
        pdf_parser.parse_and_export(doc_dir=self.paths.pdf_reports_dir)
        
        elapsed_time = time.time() - start_time
        self.logger.info(f"PDF报告解析完成，保存至 {self.paths.parsed_reports_path}，耗时: {elapsed_time:.2f}秒")

    def parse_pdf_reports_parallel(self, chunk_size: int = 2, max_workers: int = 10):
        """Parse PDF reports in parallel using multiple processes.
        
        Args:
            chunk_size: Number of PDFs to process in each worker
            num_workers: Number of parallel worker processes to use
        """
        self.logger.info(f"开始并行解析PDF报告，分块大小: {chunk_size}，最大工作进程: {max_workers}")
        start_time = time.time()
        
        pdf_parser = PDFParser(
            output_dir=self.paths.parsed_reports_path,
            csv_metadata_path=self.paths.subset_path
        )
        pdf_parser.debug_data_path = self.paths.parsed_reports_debug_path

        input_doc_paths = list(self.paths.pdf_reports_dir.glob("*.pdf"))
        self.logger.info(f"找到{len(input_doc_paths)}个PDF文件待处理")
        
        pdf_parser.parse_and_export_parallel(
            input_doc_paths=input_doc_paths,
            optimal_workers=max_workers,
            chunk_size=chunk_size
        )
        
        elapsed_time = time.time() - start_time
        self.logger.info(f"PDF报告并行解析完成，保存至 {self.paths.parsed_reports_path}，耗时: {elapsed_time:.2f}秒")

    def serialize_tables(self, max_workers: int = 10):
        """Process tables in files using parallel threading"""
        self.logger.info(f"开始序列化表格，最大工作线程: {max_workers}")
        start_time = time.time()
        
        serializer = TableSerializer()
        
        file_count = len(list(self.paths.parsed_reports_path.glob("*.json")))
        self.logger.info(f"发现{file_count}个文件需要处理")
        
        serializer.process_directory_parallel(
            self.paths.parsed_reports_path,
            max_workers=max_workers
        )
        
        elapsed_time = time.time() - start_time
        self.logger.info(f"表格序列化完成，耗时: {elapsed_time:.2f}秒")

    def merge_reports(self):
        """Merge complex JSON reports into a simpler structure with a list of pages, where all text blocks are combined into a single string."""
        self.logger.info("开始合并报告文件")
        start_time = time.time()
        
        ptp = PageTextPreparation(use_serialized_tables=self.run_config.use_serialized_tables)
        self.logger.info(f"使用序列化表格: {self.run_config.use_serialized_tables}")
        
        result = ptp.process_reports(
            reports_dir=self.paths.parsed_reports_path,
            output_dir=self.paths.merged_reports_path
        )
        
        elapsed_time = time.time() - start_time
        self.logger.info(f"报告合并完成，处理了{len(result)}个文件，保存至 {self.paths.merged_reports_path}，耗时: {elapsed_time:.2f}秒")

    def export_reports_to_markdown(self):
        """Export processed reports to markdown format for review."""
        self.logger.info("开始导出报告至Markdown格式")
        start_time = time.time()
        
        ptp = PageTextPreparation(use_serialized_tables=self.run_config.use_serialized_tables)
        
        ptp.export_to_markdown(
            reports_dir=self.paths.parsed_reports_path,
            output_dir=self.paths.reports_markdown_path
        )
        
        elapsed_time = time.time() - start_time
        self.logger.info(f"报告导出至Markdown完成，保存至 {self.paths.reports_markdown_path}，耗时: {elapsed_time:.2f}秒")

    def chunk_reports(self, include_serialized_tables: bool = False):
        """Split processed reports into smaller chunks for better processing."""
        self.logger.info(f"开始分块报告，包含序列化表格: {include_serialized_tables}")
        start_time = time.time()
        
        text_splitter = TextSplitter()
        
        serialized_tables_dir = None
        if include_serialized_tables:
            serialized_tables_dir = self.paths.parsed_reports_path
            self.logger.info(f"使用序列化表格目录: {serialized_tables_dir}")
        
        text_splitter.split_all_reports(
            self.paths.merged_reports_path,
            self.paths.documents_dir,
            serialized_tables_dir
        )
        
        elapsed_time = time.time() - start_time
        self.logger.info(f"报告分块完成，保存至 {self.paths.documents_dir}，耗时: {elapsed_time:.2f}秒")

    def create_vector_dbs(self):
        """Create vector databases from chunked reports."""
        self.logger.info("开始创建向量数据库")
        start_time = time.time()
        
        input_dir = self.paths.documents_dir
        output_dir = self.paths.vector_db_dir
        
        vdb_ingestor = VectorDBIngestor()
        vdb_ingestor.process_reports(input_dir, output_dir)
        
        elapsed_time = time.time() - start_time
        self.logger.info(f"向量数据库创建完成，保存至 {output_dir}，耗时: {elapsed_time:.2f}秒")
    
    def create_bm25_db(self):
        """Create BM25 database from chunked reports."""
        self.logger.info("开始创建BM25数据库")
        start_time = time.time()
        
        input_dir = self.paths.documents_dir
        output_file = self.paths.bm25_db_path
        
        bm25_ingestor = BM25Ingestor()
        bm25_ingestor.process_reports(input_dir, output_file)
        
        elapsed_time = time.time() - start_time
        self.logger.info(f"BM25数据库创建完成，保存至 {output_file}，耗时: {elapsed_time:.2f}秒")
    
    def parse_pdf_reports(self, parallel: bool = True, chunk_size: int = 2, max_workers: int = 10):
        self.logger.info(f"开始解析PDF报告，并行处理: {parallel}")
        if parallel:
            self.parse_pdf_reports_parallel(chunk_size=chunk_size, max_workers=max_workers)
        else:
            self.parse_pdf_reports_sequential()
    
    def process_parsed_reports(self):
        """Process already parsed PDF reports through the pipeline:
        1. Merge to simpler JSON structure
        2. Export to markdown
        3. Chunk the reports
        4. Create vector databases
        """
        self.logger.info("开始处理已解析的PDF报告")
        start_time = time.time()
        
        self.logger.info("第1步: 合并报告...")
        self.merge_reports()
        
        self.logger.info("第2步: 导出报告至Markdown...")
        self.export_reports_to_markdown()
        
        self.logger.info("第3步: 分块报告...")
        self.chunk_reports()
        
        self.logger.info("第4步: 创建向量数据库...")
        self.create_vector_dbs()
        
        elapsed_time = time.time() - start_time
        self.logger.info(f"报告处理管道完成，总耗时: {elapsed_time:.2f}秒")
        
    def _get_next_available_filename(self, base_path: Path) -> Path:
        """
        Returns the next available filename by adding a numbered suffix if the file exists.
        Example: If answers.json exists, returns answers_01.json, etc.
        """
        if not base_path.exists():
            return base_path
            
        stem = base_path.stem
        suffix = base_path.suffix
        parent = base_path.parent
        
        counter = 1
        while True:
            new_filename = f"{stem}_{counter:02d}{suffix}"
            new_path = parent / new_filename
            
            if not new_path.exists():
                self.logger.debug(f"生成新的可用文件名: {new_path}")
                return new_path
            counter += 1

    def process_questions(self):
        self.logger.info("开始处理问题")
        start_time = time.time()
        
        self.logger.info(f"配置详情: 父文档检索={self.run_config.parent_document_retrieval}, " +
                         f"LLM重排={self.run_config.llm_reranking}, " + 
                         f"重排样本大小={self.run_config.llm_reranking_sample_size}, " +
                         f"检索Top-N={self.run_config.top_n_retrieval}, " +
                         f"并行请求数={self.run_config.parallel_requests}, " +
                         f"API提供商={self.run_config.api_provider}, " +
                         f"回答模型={self.run_config.answering_model}")
        
        processor = QuestionsProcessor(
            vector_db_dir=self.paths.vector_db_dir,
            documents_dir=self.paths.documents_dir,
            questions_file_path=self.paths.questions_file_path,
            new_challenge_pipeline=True,
            subset_path=self.paths.subset_path,
            parent_document_retrieval=self.run_config.parent_document_retrieval,
            llm_reranking=self.run_config.llm_reranking,
            llm_reranking_sample_size=self.run_config.llm_reranking_sample_size,
            top_n_retrieval=self.run_config.top_n_retrieval,
            parallel_requests=self.run_config.parallel_requests,
            api_provider=self.run_config.api_provider,
            answering_model=self.run_config.answering_model,
            full_context=self.run_config.full_context            
        )
        
        output_path = self._get_next_available_filename(self.paths.answers_file_path)
        self.logger.info(f"答案将保存至: {output_path}")
        
        result = processor.process_all_questions(
            output_path=output_path,
            submission_file=self.run_config.submission_file,
            team_email=self.run_config.team_email,
            submission_name=self.run_config.submission_name,
            pipeline_details=self.run_config.pipeline_details
        )
        
        elapsed_time = time.time() - start_time
        self.logger.info(f"问题处理完成，处理了{len(result)}个问题，总耗时: {elapsed_time:.2f}秒，平均每个问题: {elapsed_time/max(1, len(result)):.2f}秒")
        self.logger.info(f"答案已保存至 {output_path}")


preprocess_configs = {"ser_tab": RunConfig(use_serialized_tables=True),
                      "no_ser_tab": RunConfig(use_serialized_tables=False)}

base_config = RunConfig(
    parallel_requests=10,
    submission_name="Ilia Ris v.0",
    pipeline_details="Custom pdf parsing + vDB + Router + SO CoT; llm = GPT-4o-mini",
    config_suffix="_base"
)

parent_document_retrieval_config = RunConfig(
    parent_document_retrieval=True,
    parallel_requests=20,
    submission_name="Ilia Ris v.1",
    pipeline_details="Custom pdf parsing + vDB + Router + Parent Document Retrieval + SO CoT; llm = GPT-4o",
    answering_model="gpt-4o-2024-08-06",
    config_suffix="_pdr"
)

max_config = RunConfig(
    use_serialized_tables=True,
    parent_document_retrieval=True,
    llm_reranking=True,
    parallel_requests=20,
    submission_name="Ilia Ris v.2",
    pipeline_details="Custom pdf parsing + table serialization + vDB + Router + Parent Document Retrieval + reranking + SO CoT; llm = GPT-4o",
    answering_model="gpt-4o-2024-08-06",
    config_suffix="_max"
)

max_no_ser_tab_config = RunConfig(
    use_serialized_tables=False,
    parent_document_retrieval=True,
    llm_reranking=True,
    parallel_requests=20,
    submission_name="Ilia Ris v.3",
    pipeline_details="Custom pdf parsing + vDB + Router + Parent Document Retrieval + reranking + SO CoT; llm = GPT-4o",
    answering_model="gpt-4o-2024-08-06",
    config_suffix="_max_no_ser_tab"
)

max_nst_o3m_config = RunConfig(
    use_serialized_tables=False,
    parent_document_retrieval=True,
    llm_reranking=True,
    parallel_requests=25,
    submission_name="Ilia Ris v.4",
    pipeline_details="Custom pdf parsing + vDB + Router + Parent Document Retrieval + reranking + SO CoT; llm = o3-mini",
    answering_model="o3-mini-2025-01-31",
    config_suffix="_max_nst_o3m"
)

max_st_o3m_config = RunConfig(
    use_serialized_tables=True,
    parent_document_retrieval=True,
    llm_reranking=True,
    parallel_requests=25,
    submission_name="Ilia Ris v.5",
    pipeline_details="Custom pdf parsing + tables serialization + Router + vDB + Parent Document Retrieval + reranking + SO CoT; llm = o3-mini",
    answering_model="o3-mini-2025-01-31",
    config_suffix="_max_st_o3m"
)

ibm_llama70b_config = RunConfig(
    use_serialized_tables=False,
    parent_document_retrieval=True,
    llm_reranking=False,
    parallel_requests=10,
    submission_name="Ilia Ris v.6",
    pipeline_details="Custom pdf parsing + vDB + Router + Parent Document Retrieval + SO CoT + SO reparser; IBM WatsonX llm = llama-3.3-70b-instruct",
    api_provider="ibm",
    answering_model="meta-llama/llama-3-3-70b-instruct",
    config_suffix="_ibm_llama70b"
)

ibm_llama8b_config = RunConfig(
    use_serialized_tables=False,
    parent_document_retrieval=True,
    llm_reranking=False,
    parallel_requests=10,
    submission_name="Ilia Ris v.7",
    pipeline_details="Custom pdf parsing + vDB + Router + Parent Document Retrieval + SO CoT + SO reparser; IBM WatsonX llm = llama-3.1-8b-instruct",
    api_provider="ibm",
    answering_model="meta-llama/llama-3-1-8b-instruct",
    config_suffix="_ibm_llama8b"
)

gemini_thinking_config = RunConfig(
    use_serialized_tables=False,
    parent_document_retrieval=True,
    llm_reranking=False,
    parallel_requests=1,
    full_context=True,
    submission_name="Ilia Ris v.8",
    pipeline_details="Custom pdf parsing + Full Context + Router + SO CoT + SO reparser; llm = gemini-2.0-flash-thinking-exp-01-21",
    api_provider="gemini",
    answering_model="gemini-2.0-flash-thinking-exp-01-21",
    config_suffix="_gemini_thinking_fc"
)

gemini_flash_config = RunConfig(
    use_serialized_tables=False,
    parent_document_retrieval=True,
    llm_reranking=False,
    parallel_requests=1,
    full_context=True,
    submission_name="Ilia Ris v.9",
    pipeline_details="Custom pdf parsing + Full Context + Router + SO CoT + SO reparser; llm = gemini-2.0-flash",
    api_provider="gemini",
    answering_model="gemini-2.0-flash",
    config_suffix="_gemini_flash_fc"
)

max_nst_o3m_config_big_context = RunConfig(
    use_serialized_tables=False,
    parent_document_retrieval=True,
    llm_reranking=True,
    parallel_requests=5,
    llm_reranking_sample_size=36,
    top_n_retrieval=14,
    submission_name="Ilia Ris v.10",
    pipeline_details="Custom pdf parsing + vDB + Router + Parent Document Retrieval + reranking + SO CoT; llm = o3-mini; top_n = 14; topn for rerank = 36",
    answering_model="o3-mini-2025-01-31",
    config_suffix="_max_nst_o3m_bc"
)

ibm_llama70b_config_big_context = RunConfig(
    use_serialized_tables=False,
    parent_document_retrieval=True,
    llm_reranking=True,
    parallel_requests=5,
    llm_reranking_sample_size=36,
    top_n_retrieval=14,
    submission_name="Ilia Ris v.11",
    pipeline_details="Custom pdf parsing + vDB + Router + Parent Document Retrieval + reranking + SO CoT; llm = llama-3.3-70b-instruct; top_n = 14; topn for rerank = 36",
    api_provider="ibm",
    answering_model="meta-llama/llama-3-3-70b-instruct",
    config_suffix="_ibm_llama70b_bc"
)

gemini_thinking_config_big_context = RunConfig(
    use_serialized_tables=False,
    parent_document_retrieval=True,
    parallel_requests=1,
    top_n_retrieval=30,
    submission_name="Ilia Ris v.12",
    pipeline_details="Custom pdf parsing + vDB + Router + Parent Document Retrieval + SO CoT; llm = gemini-2.0-flash-thinking-exp-01-21; top_n = 30;",
    api_provider="gemini",
    answering_model="gemini-2.0-flash-thinking-exp-01-21",
    config_suffix="_gemini_thinking_bc"
)

configs = {"base": base_config,
           "pdr": parent_document_retrieval_config,
           "max": max_config, 
           "max_no_ser_tab": max_no_ser_tab_config,
           "max_nst_o3m": max_nst_o3m_config, # This configuration returned the best results
           "max_st_o3m": max_st_o3m_config,
           "ibm_llama70b": ibm_llama70b_config, # This one won't work, because ibm api was avaliable only while contest was running
           "ibm_llama8b": ibm_llama8b_config, # This one won't work, because ibm api was avaliable only while contest was running
           "gemini_thinking": gemini_thinking_config}


# You can run any method right from this file with 
# python .\src\pipeline.py
# Just uncomment the method you want to run
# You can also change the run_config to try out different configurations
if __name__ == "__main__":
    root_path = here() / "data" / "test_set"
    pipeline = Pipeline(root_path, run_config=max_nst_o3m_config)
    
    
    # This method parses pdf reports into a jsons. It creates jsons in the debug/data_01_parsed_reports. These jsons used in the next steps. 
    # It also stores raw output of docling in debug/data_01_parsed_reports_debug, these jsons contain a LOT of metadata, and not used anywhere
    # pipeline.parse_pdf_reports_sequential() 
    
    
    # This method should be called only if you want run configs with serialized tables
    # It modifies the jsons in the debug/data_01_parsed_reports, adding a new field "serialized_table" to each table
    # pipeline.serialize_tables(max_workers=5) 
    
    
    # This method converts jsons from the debug/data_01_parsed_reports into much simpler jsons, that is a list of pages in markdown
    # New jsons can be found in debug/data_02_merged_reports
    # pipeline.merge_reports() 


    # This method exports the reports into plain markdown format. They used only for review and for full text search config: gemini_thinking_config
    # New files can be found in debug/data_03_reports_markdown
    # pipeline.export_reports_to_markdown() 
    

    # This method splits the reports into chunks, that are used for vectorization
    # New jsons can be found in databases/chunked_reports
    # pipeline.chunk_reports() 
    
    
    # This method creates vector databases from the chunked reports
    # New files can be found in databases/vector_dbs
    # pipeline.create_vector_dbs() 
    
    
    # This method processes the questions and answers
    # Questions processing logic depends on the run_config
    # pipeline.process_questions() 