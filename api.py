import os
import json
import asyncio
from fastapi import FastAPI, Query
from pydantic import BaseModel
from pageindex.utils import ConfigLoader, ChatGPT_API, ChatGPT_API_async, get_text_of_pages, remove_fields
from pageindex.vector_index import get_vector_index, search_documents
import uvicorn

app = FastAPI(title="PageIndex Retrieval API")

class QueryRequest(BaseModel):
    q: str
    top_k: int = 10  # 向量检索返回的最大结果数

# 获取配置
config_loader = ConfigLoader()
default_config = config_loader.load()
MODEL_NAME = os.getenv("CHATGPT_MODEL", "gpt-4o")
RESULTS_DIR = "results"
UPLOAD_DIR = "uploads"


def get_node_mapping(structure, mapping=None):
    """从树结构中构建 node_id 到节点的映射"""
    if mapping is None: 
        mapping = {}
    if isinstance(structure, list):
        for item in structure:
            get_node_mapping(item, mapping)
    elif isinstance(structure, dict):
        if 'node_id' in structure:
            mapping[structure['node_id']] = structure
        if 'nodes' in structure:
            get_node_mapping(structure['nodes'], mapping)
    return mapping


def load_document_structure(doc_name: str):
    """加载文档的结构 JSON 文件"""
    # 尝试多种可能的文件名格式
    possible_names = [
        f"{doc_name}_structure.json",
        f"{doc_name.replace('.pdf', '')}_structure.json",
        f"{doc_name.replace('.md', '')}_structure.json",
    ]
    
    for name in possible_names:
        path = os.path.join(RESULTS_DIR, name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return None


def get_document_file_path(doc_name: str):
    """获取文档的原始文件路径"""
    # 尝试多种可能的文件扩展名
    for ext in ["", ".pdf", ".md", ".markdown"]:
        path = os.path.join(UPLOAD_DIR, doc_name + ext)
        if os.path.exists(path):
            return path
    
    # 尝试不带扩展名的匹配
    base_name = doc_name.replace("_structure.json", "")
    for ext in ["", ".pdf", ".md", ".markdown"]:
        path = os.path.join(UPLOAD_DIR, base_name + ext)
        if os.path.exists(path):
            return path
    
    return None


@app.post("/query")
async def query_documents(request: QueryRequest):
    """
    使用向量检索进行文档查询
    
    优化后的流程：
    1. 向量检索：快速找到相关节点（毫秒级，0 Token）
    2. 内容提取：根据节点信息提取原文
    3. 答案生成：LLM 基于上下文生成回答
    """
    q = request.q
    top_k = request.top_k
    
    # 检查向量索引状态
    try:
        vector_index = get_vector_index()
        stats = vector_index.get_stats()
        
        if stats["total_nodes"] == 0:
            return {
                "answer": "向量索引为空，请先上传并处理文档。",
                "sources": [],
                "thinking": "向量索引中没有任何节点。"
            }
    except Exception as e:
        return {
            "answer": f"向量索引初始化失败: {str(e)}",
            "sources": [],
            "thinking": "请检查 Embedding 模型配置是否正确。"
        }
    
    # 1. 向量检索（毫秒级，0 Token）
    try:
        search_results = search_documents(q, top_k=top_k)
    except Exception as e:
        return {
            "answer": f"向量检索失败: {str(e)}",
            "sources": [],
            "thinking": "请检查 Embedding 模型服务是否正常运行。"
        }
    
    if not search_results:
        return {
            "answer": "未找到与问题相关的文档内容。",
            "sources": [],
            "thinking": "向量检索未返回任何结果。"
        }
    
    # 2. 内容提取
    all_relevant_text = ""
    all_reference_nodes = []
    thinking_parts = []
    
    # 按文档分组处理结果
    doc_results = {}
    for result in search_results:
        doc_name = result["doc_name"]
        if doc_name not in doc_results:
            doc_results[doc_name] = []
        doc_results[doc_name].append(result)
    
    thinking_parts.append(f"向量检索返回 {len(search_results)} 个相关节点，来自 {len(doc_results)} 个文档")
    
    for doc_name, results in doc_results.items():
        # 加载文档结构
        doc_data = load_document_structure(doc_name)
        if not doc_data:
            thinking_parts.append(f"[{doc_name}] 未找到结构文件，跳过")
            continue
        
        node_map = get_node_mapping(doc_data.get("structure", []))
        doc_file_path = get_document_file_path(doc_name)
        
        for result in results:
            node_id = result["node_id"]
            title = result["title"]
            score = result.get("score", 0)
            
            # 记录参考来源
            start_idx = result.get("start_index", "?")
            all_reference_nodes.append(f"[{doc_name}] {title} (相似度: {score:.3f})")
            
            # 获取节点内容
            node = node_map.get(node_id)
            if node:
                # 优先使用节点中存储的文本
                if node.get("text"):
                    all_relevant_text += f"\n--- 文档: {doc_name}, 章节: {title} ---\n{node['text']}\n"
                # 否则尝试从原始文件提取
                elif doc_file_path and doc_file_path.lower().endswith(".pdf"):
                    try:
                        start_page = node.get("start_index")
                        end_page = node.get("end_index")
                        if start_page and end_page:
                            page_text = get_text_of_pages(doc_file_path, start_page, end_page, tag=False)
                            all_relevant_text += f"\n--- 文档: {doc_name}, 章节: {title} ---\n{page_text}\n"
                    except Exception as e:
                        thinking_parts.append(f"[{doc_name}] 提取页面内容失败: {e}")
                # 使用摘要作为备选
                elif result.get("summary"):
                    all_relevant_text += f"\n--- 文档: {doc_name}, 章节: {title} (摘要) ---\n{result['summary']}\n"
    
    # 3. 答案生成
    if not all_relevant_text.strip():
        return {
            "answer": "检索到相关节点，但未能提取到有效内容。请确保文档已正确处理。",
            "sources": all_reference_nodes,
            "thinking": "\n".join(thinking_parts)
        }
    
    answer_prompt = f"""你是一个专业的研究助手。你有来自多个来源的文档片段。
根据提供的上下文回答用户的问题。
如果来源有冲突的信息，请提及。
在回答中始终引用文档名称。

问题: {q}

上下文:
{all_relevant_text[:15000]}

助手:"""
    
    try:
        full_answer = ChatGPT_API(model=MODEL_NAME, prompt=answer_prompt)
    except Exception as e:
        full_answer = f"答案生成失败: {str(e)}"
    
    return {
        "answer": full_answer,
        "sources": all_reference_nodes,
        "thinking": "\n".join(thinking_parts)
    }


@app.post("/query/raw")
async def query_documents_raw(request: QueryRequest):
    """
    使用向量检索进行文档查询，只返回原始检索结果
    
    此接口不调用大模型生成答案，只返回向量检索的原始结果：
    1. 向量检索：快速找到相关节点（毫秒级，0 Token）
    2. 内容提取：根据节点信息提取原文
    """
    q = request.q
    top_k = request.top_k
    
    # 检查向量索引状态
    try:
        vector_index = get_vector_index()
        stats = vector_index.get_stats()
        
        if stats["total_nodes"] == 0:
            return {
                "status": "error",
                "message": "向量索引为空，请先上传并处理文档。",
                "results": []
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"向量索引初始化失败: {str(e)}",
            "results": []
        }
    
    # 1. 向量检索（毫秒级，0 Token）
    try:
        search_results = search_documents(q, top_k=top_k)
    except Exception as e:
        return {
            "status": "error",
            "message": f"向量检索失败: {str(e)}",
            "results": []
        }
    
    if not search_results:
        return {
            "status": "ok",
            "message": "未找到与问题相关的文档内容。",
            "results": []
        }
    
    # 2. 内容提取
    enriched_results = []
    
    # 按文档分组处理结果
    doc_results = {}
    for result in search_results:
        doc_name = result["doc_name"]
        if doc_name not in doc_results:
            doc_results[doc_name] = []
        doc_results[doc_name].append(result)
    
    for doc_name, results in doc_results.items():
        # 加载文档结构
        doc_data = load_document_structure(doc_name)
        if not doc_data:
            for result in results:
                enriched_results.append({
                    "doc_name": doc_name,
                    "node_id": result["node_id"],
                    "title": result["title"],
                    "score": result.get("score", 0),
                    "summary": result.get("summary", ""),
                    "text": None,
                    "error": "未找到结构文件"
                })
            continue
        
        node_map = get_node_mapping(doc_data.get("structure", []))
        doc_file_path = get_document_file_path(doc_name)
        
        for result in results:
            node_id = result["node_id"]
            title = result["title"]
            score = result.get("score", 0)
            
            enriched_result = {
                "doc_name": doc_name,
                "node_id": node_id,
                "title": title,
                "score": score,
                "summary": result.get("summary", ""),
                "text": None
            }
            
            # 获取节点内容
            node = node_map.get(node_id)
            if node:
                enriched_result["start_index"] = node.get("start_index")
                enriched_result["end_index"] = node.get("end_index")
                
                # 优先使用节点中存储的文本
                if node.get("text"):
                    enriched_result["text"] = node["text"]
                # 否则尝试从原始文件提取
                elif doc_file_path and doc_file_path.lower().endswith(".pdf"):
                    try:
                        start_page = node.get("start_index")
                        end_page = node.get("end_index")
                        if start_page and end_page:
                            page_text = get_text_of_pages(doc_file_path, start_page, end_page, tag=False)
                            enriched_result["text"] = page_text
                    except Exception as e:
                        enriched_result["error"] = f"提取页面内容失败: {str(e)}"
            
            enriched_results.append(enriched_result)
    
    return {
        "status": "ok",
        "query": q,
        "total_results": len(enriched_results),
        "results": enriched_results
    }


@app.get("/index/stats")
async def get_index_stats():
    """获取向量索引统计信息"""
    try:
        vector_index = get_vector_index()
        stats = vector_index.get_stats()
        return {
            "status": "ok",
            "stats": stats
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


@app.post("/index/rebuild")
async def rebuild_index():
    """重建所有文档的向量索引"""
    try:
        vector_index = get_vector_index()
        
        # 获取所有结构文件
        if not os.path.exists(RESULTS_DIR):
            return {"status": "error", "message": "results 目录不存在"}
        
        structure_files = [f for f in os.listdir(RESULTS_DIR) if f.endswith("_structure.json")]
        
        if not structure_files:
            return {"status": "error", "message": "没有找到任何结构文件"}
        
        rebuilt_count = 0
        errors = []
        
        for filename in structure_files:
            try:
                filepath = os.path.join(RESULTS_DIR, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                doc_name = data.get("doc_name", filename.replace("_structure.json", ""))
                doc_description = data.get("doc_description", "")
                structure = data.get("structure", [])
                
                node_count = vector_index.add_document(doc_name, structure, doc_description)
                rebuilt_count += 1
                print(f"已重建 {doc_name} 的索引，共 {node_count} 个节点")
                
            except Exception as e:
                errors.append(f"{filename}: {str(e)}")
        
        return {
            "status": "ok",
            "rebuilt_documents": rebuilt_count,
            "errors": errors if errors else None
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


@app.delete("/index/{doc_name}")
async def delete_document_index(doc_name: str):
    """删除指定文档的向量索引"""
    try:
        vector_index = get_vector_index()
        deleted_count = vector_index.delete_document(doc_name)
        return {
            "status": "ok",
            "deleted_nodes": deleted_count
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


# 保留旧的 LLM 检索接口作为备选
@app.post("/query/llm")
async def query_documents_llm(request: QueryRequest):
    """
    使用 LLM 进行文档检索（旧版接口，保留作为备选）
    
    注意：此接口 Token 消耗较高，建议使用 /query 接口
    """
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
    
    relevant_filenames = await select_relevant_docs_llm(q, docs_info, MODEL_NAME)
    
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
        search_res = await tree_search_llm(q, index_data['structure'], MODEL_NAME)
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


async def select_relevant_docs_llm(query, docs_info, model):
    """让 LLM 根据文档名称和描述选择与查询相关的文档（旧版方法）"""
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


async def tree_search_llm(query, tree, model):
    """使用 LLM 在树结构中搜索相关节点（旧版方法）"""
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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8502)
