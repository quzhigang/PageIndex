# PageIndex 📄

PageIndex 是一个专门用于从 PDF 文档中提取高精度、层级化目录结构（Table of Contents, TOC）的 Python 库。它为检索增强生成（RAG）场景提供了“无需向量（Vectorless）”的全新思路，通过对文档结构的深度理解，实现更符合人类阅读习惯的精准检索与推理。

## 🌟 核心特性

- **高精度目录提取**：利用 LLM 智能解析 PDF，不仅能提取原有的目录，还能为没有目录的文档自动生成层级结构。
- **物理页面映射**：将层级标题精确映射到 PDF 的物理页码，确保检索定位的准确性。
- **Vectorless RAG**：不同于传统的切片和向量化方案，PageIndex 支持基于推理的原文检索，保留文档上下文的完整性。
- **多模态支持**：支持直接在页面图像上进行推理（Vision-based），无需复杂的 OCR 流程。
- **灵活的配置**：支持添加节点 ID、摘要、全文内容以及文档整体描述。

## 🚀 快速开始

### 安装

```bash
git clone https://github.com/VectifyAI/PageIndex.git
cd PageIndex
pip install -r requirements.txt
```

### 基础用法

PageIndex 支持处理 PDF 和 Markdown 文件。

#### 1. 通过代码调用 (PDF)

```python
from pageindex.page_index import page_index

# 配置参数
pdf_path = "your_document.pdf"
model = "gpt-4o"

# 提取文档结构
result = page_index(
    doc=pdf_path,
    model=model,
    if_add_node_summary='yes',
    if_add_doc_description='yes'
)

# 查看结果
print(f"文档名称: {result['doc_name']}")
print(f"文档描述: {result['doc_description']}")
for node in result['structure']:
    print(f"{node['structure']} {node['title']} (第 {node['physical_index']} 页)")
```

#### 2. 通过命令行运行

你也可以直接使用 `run_pageindex.py` 脚本来处理文档：

```bash
# 处理 PDF 文档
python run_pageindex.py --pdf_path uploads/your_document.pdf --model gpt-4o

# 处理 Markdown 文档
python run_pageindex.py --md_path uploads/your_document.md --model gpt-4o
```

## 🧪 示例库 (Cookbooks)

我们在 `cookbook` 目录下提供了多个实用示例，帮助您快速上手：

- [**基础 RAG 快速入门**](./cookbook/pageIndex_chat_quickstart.ipynb)：展示如何结合 PageIndex 进行简单的问答。
- [**Vectorless RAG**](./cookbook/pageindex_RAG_simple.ipynb)：深入了解无需向量化的推理原生 RAG 流程。
- [**Vision-based RAG**](./cookbook/vision_RAG_pageindex.ipynb)：直接基于页面图像进行推理，规避 OCR 误差。
- [**Agentic Retrieval**](./cookbook/agentic_retrieval.ipynb)：构建基于代理的智能检索系统。

## 📂 项目结构

- `pageindex/`: 核心代码库。
- `cookbook/`: 示例 Jupyter Notebooks。
- `results/`: 存储解析后的 JSON 结构示例。
- `uploads/`: 用于测试的输入文档。
- `tutorials/`: 更多深入教程。

## 🛠️ 技术细节

PageIndex 通过以下步骤处理 PDF：
1. **TOC 检测**：识别文档是否自带目录。
2. **结构转换**：将原始文本目录转换为结构化的 JSON 数据。
3. **偏移修正**：自动计算物理页码与逻辑页码之间的偏移。
4. **层级递归补全**：对于缺失目录的部分，通过 LLM 递归生成细分层级。

---
由 [Vectify AI](https://github.com/VectifyAI) 驱动。
