# PageIndex 📄

PageIndex 是一个专门用于从 PDF和md文档中提取高精度、层级化目录结构（Table of Contents, TOC）的 Python 库。它为检索增强生成（RAG）场景提供了“无需向量（Vectorless）”的全新思路，通过对文档结构的深度理解，实现更符合人类阅读习惯的精准检索与推理。

## 🌟 核心特性

- **高精度目录提取**：利用 LLM 智能解析PDF和MD文档，不仅能提取原有的目录，还能为没有目录的文档自动生成层级结构。
- **物理页面映射**：将层级标题精确映射到 PDF和MD文档 的物理页码，确保检索定位的准确性。
- **Vectorless RAG**：不同于传统的切片和向量化方案，PageIndex 支持基于推理的原文检索，保留文档上下文的完整性。
- **多模态支持**：支持直接在页面图像上进行推理（Vision-based），无需复杂的 OCR 流程。
- **灵活的配置**：支持添加节点 ID、摘要、全文内容以及文档整体描述。

## 🚀 快速开始

### 安装

```bash
cd PageIndex
pip install -r requirements.txt
```

## 🖥️ 网页界面 (UI) 与 API

PageIndex 提供了直观的 Streamlit 网页界面以及 REST API，方便进行文档处理和自动化集成。

### 启动方式

**网页界面 (UI)**:
```bash
streamlit run app.py
```

**REST API**:
```bash
python api.py
```

### 主要功能

-   **文档处理**：支持 PDF/Markdown 文件批量上传、自动解析目录、生成摘要及物理页码映射。
-   **已处理清单**：集中管理已解析的文档，支持查看详细信息及删除操作。
-   **智能对话 (RAG)**：
    -   **跨文档检索**：模型会自动识别与问题相关的文档。
    -   **精准定位**：基于 PageIndex 的层级结构，直接定位到具体章节或页面。
    -   **推理原生回答**：整合多处上下文，给出引经据典的详细回答。

### REST API 使用说明

启动 `api.py` 后，可以通过以下接口进行文档检索：

- **Endpoint**: `POST /query`
- **Body**: `{"q": "用户的问题"}`
- **示例**:
  ```bash
  curl -X POST "http://localhost:8000/query" -H "Content-Type: application/json" -d '{"q": "什么是PageIndex？"}'
  ```
- **返回**: 包含 AI 回答、参考来源以及推理过程的 JSON 对象。

## 🧪 示例库 (Cookbooks)

我们在 `cookbook` 目录下提供了多个实用示例，帮助您快速上手：

- [**基础 RAG 快速入门**](./cookbook/pageIndex_chat_quickstart.ipynb)：展示如何结合 PageIndex 进行简单的问答。
- [**Vectorless RAG**](./cookbook/pageindex_RAG_simple.ipynb)：深入了解无需向量化的推理原生 RAG 流程。
- [**Vision-based RAG**](./cookbook/vision_RAG_pageindex.ipynb)：直接基于页面图像进行推理，规避 OCR 误差。
- [**Agentic Retrieval**](./cookbook/agentic_retrieval.ipynb)：构建基于代理的智能检索系统。

## 📂 项目结构

- `pageindex/`: 核心代码库。
- `cookbook/`: 示例 Jupyter Notebooks。
- `results/`: 存储解析后的文档JSON结构。
- `uploads/`: 存储上传的输入文档。
- `tutorials/`: 更多深入教程。

## 🛠️ 技术细节

PageIndex 通过以下步骤处理 PDF：
1. **TOC 检测**：识别文档是否自带目录。
2. **结构转换**：将原始文本目录转换为结构化的 JSON 数据。
3. **偏移修正**：自动计算物理页码与逻辑页码之间的偏移。
4. **层级递归补全**：对于缺失目录的部分，通过 LLM 递归生成细分层级。
