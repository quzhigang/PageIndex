import os
import json
import asyncio
from fastapi import FastAPI, Query
from pydantic import BaseModel
from pageindex.utils import ConfigLoader, ChatGPT_API, ChatGPT_API_async, get_text_of_pages, remove_fields
import uvicorn

app = FastAPI(title="PageIndex Retrieval API")

class QueryRequest(BaseModel):
    q: str

# 获取配置
config_loader = ConfigLoader()
default_config = config_loader.load()
MODEL_NAME = os.getenv("CHATGPT_MODEL", default_config.model)
RESULTS_DIR = "results"
UPLOAD_DIR = "uploads"

async def select_relevant_docs(query, docs_info, model):
    """让 LLM 根据文档名称和描述选择与查询相关的文档。"""
    prompt = f"""你是一个智能文档路由代理。你有一份包含文档名称和描述的列表。
用户有一个问题。你的任务是选择可能包含答案的节点 ID（文档文件名）。

问题: {query}

文档列表:
{json.dumps(docs_info, indent=2, ensure_ascii=False)}

请仅以以下 JSON 格式回复:
{{
    "relevant_docs": ["filename1.json", "filename2.json"]
}}
如果没有相关文档，返回空列表。"""
    response = await ChatGPT_API_async(model=model, prompt=prompt)
    try:
        content = response.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return json.loads(content).get("relevant_docs", [])
    except Exception:
        return []

async def tree_search(query, tree, model):
    # 准备不包含完整文本的树结构用于检索
    tree_for_search = remove_fields(tree, fields=['text'])
    
    search_prompt = f"""你是一个专业的文档检索专家。你将收到一个用户问题和一个文档的层级树结构。
树中的每个节点都有 `node_id`、`title` 和 `summary`。

你的目标是识别最相关的节点，这些节点包含回答问题所需的信息。
- 优先选择叶子节点（层级底部的节点），因为它们包含实际的页面内容。
- 如果信息分布在不同部分，可以选择多个节点。
- 在 `thinking` 字段中提供你的推理过程。

问题: {query}

文档树结构:
{json.dumps(tree_for_search, indent=2, ensure_ascii=False)}

请仅以以下 JSON 格式回复:
{{
    "thinking": "<逐步推理为什么选择这些节点>",
    "node_list": ["node_id_1", "node_id_2", ...]
}}"""
    response = await ChatGPT_API_async(model=model, prompt=search_prompt)
    try:
        content = response.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return json.loads(content)
    except Exception as e:
        return {"thinking": f"解析失败: {str(e)}", "node_list": []}

def get_node_mapping(structure, mapping=None):
    if mapping is None: mapping = {}
    if isinstance(structure, list):
        for item in structure:
            get_node_mapping(item, mapping)
    elif isinstance(structure, dict):
        if 'node_id' in structure:
            mapping[structure['node_id']] = structure
        if 'nodes' in structure:
            get_node_mapping(structure['nodes'], mapping)
    return mapping

@app.post("/query")
async def query_documents(request: QueryRequest):
    q = request.q
    # 1. 加载所有可用索引
    if not os.path.exists(RESULTS_DIR):
        return {"answer": "未找到任何索引文件，请先上传并处理文档。", "sources": [], "thinking": ""}
    
    available_indices = [f for f in os.listdir(RESULTS_DIR) if f.endswith("_structure.json")]
    if not available_indices:
        return {"answer": "尚未处理任何文档。", "sources": [], "thinking": ""}

    # 2. 筛选相关文档
    docs_info = []
    for idx_file in available_indices:
        try:
            with open(os.path.join(RESULTS_DIR, idx_file), "r", encoding="utf-8") as f:
                data = json.load(f)
                docs_info.append({
                    "filename": idx_file,
                    "doc_name": data.get("doc_name", idx_file),
                    "description": data.get("description", "无描述")
                })
        except Exception:
            continue
    
    relevant_filenames = await select_relevant_docs(q, docs_info, MODEL_NAME)
    
    # 策略：如果没有筛选出文档且文档总量较少，则全部搜索
    if not relevant_filenames:
        if len(available_indices) <= 3:
            relevant_filenames = available_indices
        else:
            return {"answer": "未找到与问题相关的文档。", "sources": [], "thinking": "模型认为没有文档直接相关。"}

    # 3. 在每个相关文档中搜索
    all_relevant_text = ""
    all_reference_nodes = []
    total_thinking = ""
    
    for idx_file in relevant_filenames:
        idx_path = os.path.join(RESULTS_DIR, idx_file)
        if not os.path.exists(idx_path): continue
        
        try:
            with open(idx_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
        except Exception:
            continue
        
        doc_display_name = index_data.get('doc_name', idx_file)
        
        # 对此文档进行树搜索
        search_res = await tree_search(q, index_data['structure'], MODEL_NAME)
        if search_res.get('thinking'):
            total_thinking += f"**[{doc_display_name}]**: {search_res['thinking']}"
        
        node_map = get_node_mapping(index_data['structure'])
        
        pdf_name = index_data.get('doc_name', idx_file.replace("_structure.json", ""))
        pdf_path = os.path.join(UPLOAD_DIR, pdf_name)
        if not os.path.exists(pdf_path):
            for ext in [".pdf", ".md", ".markdown"]:
                if os.path.exists(pdf_path + ext):
                    pdf_path = pdf_path + ext
                    break

        for node_id in search_res.get('node_list', []):
            if node_id in node_map:
                node = node_map[node_id]
                title = node.get('title', '未知')
                start_p = node.get('start_index', '?')
                all_reference_nodes.append(f"[{doc_display_name}] {title} (第{start_p}页)")
                
                if node.get('text'):
                    all_relevant_text += f"--- 文档: {doc_display_name}, 章节: {title} ---{node['text']}"
                elif os.path.exists(pdf_path) and pdf_path.lower().endswith(".pdf"):
                    try:
                        page_text = get_text_of_pages(pdf_path, node['start_index'], node['end_index'], tag=False)
                        all_relevant_text += f"--- 文档: {doc_display_name}, 章节: {title} ---{page_text}"
                    except Exception:
                        pass

    # 4. 整合知识生成回答
    if not all_relevant_text:
        return {
            "answer": "抱歉，检索过程未能从相关文档中提取到足够的原文内容。",
            "sources": all_reference_nodes,
            "thinking": total_thinking
        }
    
    answer_prompt = f"""你是一个专业的研究助手。你有来自多个来源的文档片段。
根据提供的上下文回答用户的问题。
如果来源有冲突的信息，请提及。
在回答中始终引用文档名称。

问题: {q}

上下文:
{all_relevant_text[:15000]}

助手:"""
    
    full_answer = ChatGPT_API(model=MODEL_NAME, prompt=answer_prompt)
    
    return {
        "answer": full_answer,
        "sources": all_reference_nodes,
        "thinking": total_thinking
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
