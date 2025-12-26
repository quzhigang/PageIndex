import streamlit as st
import os
import json
import asyncio
from pageindex import page_index_main, config
from pageindex.page_index_md import md_to_tree
from pageindex.utils import ConfigLoader, ChatGPT_API, ChatGPT_API_async, get_text_of_pages, remove_fields

st.set_page_config(page_title="PageIndex Web UI", page_icon="🌲", layout="wide")

# Helper Functions
def update_api_config(api_key, api_base):
    os.environ["CHATGPT_API_KEY"] = api_key
    os.environ["CHATGPT_API_BASE"] = api_base
    import pageindex.utils
    pageindex.utils.CHATGPT_API_KEY = api_key
    pageindex.utils.CHATGPT_API_BASE = api_base

async def select_relevant_docs(query, docs_info, model):
    """Ask LLM to select which documents are relevant to the query based on their names and descriptions."""
    prompt = f"""You are an intelligent document routing agent. You have a list of documents with their names and descriptions.
The user has a question. Your task is to select the node IDs (document filenames) that are likely to contain the answer.

Question: {query}

Documents:
{json.dumps(docs_info, indent=2, ensure_ascii=False)}

Please reply ONLY in the following JSON format:
{{
    "relevant_docs": ["filename1.json", "filename2.json"]
}}
If none are relevant, return an empty list."""
    response = await ChatGPT_API_async(model=model, prompt=prompt)
    try:
        content = response.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return json.loads(content).get("relevant_docs", [])
    except Exception as e:
        st.error(f"文档筛选解析失败: {e}")
        return []

async def tree_search(query, tree, model):
    # Prepare a version of the tree without full text for retrieval
    tree_for_search = remove_fields(tree, fields=['text'])
    
    search_prompt = f"""You are an expert document retriever. You are given a user question and a hierarchical tree structure of a document.
Each node in the tree has a `node_id`, `title`, and a `summary`.

Your goal is to identify the most relevant nodes that would contain the information needed to answer the question. 
- Prioritize leaf nodes (nodes at the bottom of the hierarchy) as they contain the actual page content.
- You can select multiple nodes if the information is spread across different sections.
- Provide your reasoning in the `thinking` field.

Question: {query}

Document tree structure:
{json.dumps(tree_for_search, indent=2, ensure_ascii=False)}

Please reply ONLY in the following JSON format:
{{
    "thinking": "<Step-by-step reasoning on why these nodes were selected>",
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
        return {"thinking": f"解析失败: {e}", "node_list": []}

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

# Sidebar for configuration
st.sidebar.header("模型选项")
api_key = st.sidebar.text_input("API Key", value=os.getenv("CHATGPT_API_KEY", ""), type="password")
api_base = st.sidebar.text_input("API Base URL", value=os.getenv("CHATGPT_API_BASE", "https://api.openai.com/v1"))

config_loader = ConfigLoader()
default_config = config_loader.load()
model_name = st.sidebar.text_input("模型名称", value=default_config.model)

st.sidebar.header("PageIndex 选项")
toc_check_pages = st.sidebar.number_input("TOC 检查页数", value=default_config.toc_check_page_num)
max_pages_per_node = st.sidebar.number_input("每个节点最大页数", value=default_config.max_page_num_each_node)
max_tokens_per_node = st.sidebar.number_input("每个节点最大 Token 数", value=default_config.max_token_num_each_node)

# Defaults as per user request
if_add_doc_description = "no"
if_add_node_text = "no"

st.title("🌲 PageIndex Intelligent Document Agent")

tab1, tab2 = st.tabs(["📄 文档处理", "💬 智能对话"])

upload_dir = "uploads"
results_dir = "results"
os.makedirs(upload_dir, exist_ok=True)
os.makedirs(results_dir, exist_ok=True)

# Tab 1: Document Processing
with tab1:
    st.header("处理新文档")
    uploaded_files = st.file_uploader("选择文件（支持多选）", type=["pdf", "md", "markdown"], accept_multiple_files=True)

    if uploaded_files:
        if st.button("🚀 开始批量处理"):
            if not api_key:
                st.error("请输入 API Key！")
            else:
                update_api_config(api_key, api_base)
                total_files = len(uploaded_files)
                progress_bar = st.progress(0.0)
                status_text = st.empty()
                all_results_container = st.container()
                
                for i, uploaded_file in enumerate(uploaded_files):
                    file_extension = os.path.splitext(uploaded_file.name)[1].lower()
                    status_text.text(f"正在处理 ({i+1}/{total_files}): {uploaded_file.name}...")
                    
                    try:
                        file_path = os.path.join(upload_dir, uploaded_file.name)
                        with open(file_path, "wb") as f:
                            f.write(uploaded_file.getvalue())
                        
                        result = None
                        if file_extension == ".pdf":
                            opt = config(
                                model=model_name,
                                toc_check_page_num=toc_check_pages,
                                max_page_num_each_node=max_pages_per_node,
                                max_token_num_each_node=max_tokens_per_node,
                                if_add_node_id="yes",
                                if_add_node_summary="yes",
                                if_add_doc_description=if_add_doc_description,
                                if_add_node_text=if_add_node_text
                            )
                            result = page_index_main(file_path, opt)
                        elif file_extension in [".md", ".markdown"]:
                            result = asyncio.run(md_to_tree(
                                md_path=file_path,
                                if_thinning=False,
                                if_add_node_summary=True,
                                model=model_name,
                                if_add_doc_description=(if_add_doc_description == "yes"),
                                if_add_node_text=(if_add_node_text == "yes"),
                                if_add_node_id=True
                            ))

                        if result:
                            file_base_name = os.path.splitext(uploaded_file.name)[0]
                            result_file_path = os.path.join(results_dir, f"{file_base_name}_structure.json")
                            with open(result_file_path, "w", encoding="utf-8") as f:
                                json.dump(result, f, indent=2, ensure_ascii=False)
                            
                            with all_results_container:
                                with st.expander(f"✅ {uploaded_file.name} 处理成功", expanded=False):
                                    st.info(f"JSON 已自动保存至: {result_file_path}")
                                    st.json(result)
                    except Exception as e:
                        with all_results_container:
                            st.error(f"❌ {uploaded_file.name} 处理出错: {str(e)}")
                    progress_bar.progress((i + 1) / total_files)
                status_text.text("🎉 所有任务处理完成！")
                st.balloons()

# Tab 2: Intelligent Chat (RAG)
with tab2:
    st.header("跨文档智能对话")
    
    # Load all available indices
    available_indices = [f for f in os.listdir(results_dir) if f.endswith("_structure.json")]
    
    if not available_indices:
        st.warning("尚未处理任何文档。请先在“文档处理”选项卡中处理文件。")
    else:
        st.info(f"当前库中共包含 {len(available_indices)} 个已索引文档。")

        # Initialize chat history
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # Display chat messages
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                if "thinking" in message and message["thinking"]:
                    with st.expander("推理检索过程"):
                        st.markdown(message["thinking"])
                if "nodes" in message and message["nodes"]:
                    with st.expander("参考来源"):
                        for node_info in message["nodes"]:
                            st.write(node_info)

        # Chat input
        if query := st.chat_input("向整个文档库提问..."):
            if not api_key:
                st.error("请先在侧边栏配置 API Key")
            else:
                update_api_config(api_key, api_base)
                st.session_state.messages.append({"role": "user", "content": query})
                with st.chat_message("user"):
                    st.markdown(query)

                with st.chat_message("assistant"):
                    with st.status("正在进行多文档智能检索...", expanded=True) as status:
                        # 1. Select relevant documents
                        st.write("1. 筛选相关文档...")
                        docs_info = []
                        for idx_file in available_indices:
                            with open(os.path.join(results_dir, idx_file), "r", encoding="utf-8") as f:
                                data = json.load(f)
                                docs_info.append({
                                    "filename": idx_file,
                                    "doc_name": data.get("doc_name", idx_file),
                                    "description": data.get("description", "无描述")
                                })
                        
                        relevant_filenames = asyncio.run(select_relevant_docs(query, docs_info, model_name))
                        st.write(f"已筛选出 {len(relevant_filenames)} 个相关文档: {relevant_filenames}")
                        
                        if not relevant_filenames:
                            if len(available_indices) <= 3:
                                relevant_filenames = available_indices
                            else:
                                st.warning("模型认为没有文档与此问题直接相关。")
                                relevant_filenames = []
                        
                        # 2. Search within each relevant document
                        all_relevant_text = ""
                        all_reference_nodes = []
                        total_thinking = ""
                        
                        for idx_file in relevant_filenames:
                            idx_path = os.path.join(results_dir, idx_file)
                            if not os.path.exists(idx_path): continue
                            
                            with open(idx_path, "r", encoding="utf-8") as f:
                                index_data = json.load(f)
                            
                            doc_display_name = index_data.get('doc_name', idx_file)
                            st.write(f"正在检索文档: {doc_display_name}...")
                            
                            # Tree Search for this doc
                            search_res = asyncio.run(tree_search(query, index_data['structure'], model_name))
                            if search_res.get('thinking'):
                                total_thinking += f"**[{doc_display_name}]**: {search_res['thinking']}

"
                            
                            node_map = get_node_mapping(index_data['structure'])
                            
                            pdf_name = index_data.get('doc_name', idx_file.replace("_structure.json", ""))
                            pdf_path = os.path.join(upload_dir, pdf_name)
                            if not os.path.exists(pdf_path):
                                for ext in [".pdf", ".md", ".markdown"]:
                                    if os.path.exists(pdf_path + ext):
                                        pdf_path = pdf_path + ext
                                        break

                            for node_id in search_res.get('node_list', []):
                                if node_id in node_map:
                                    node = node_map[node_id]
                                    title = node.get('title', 'Unknown')
                                    start_p = node.get('start_index', '?')
                                    all_reference_nodes.append(f"[{doc_display_name}] {title} (P{start_p})")
                                    
                                    if node.get('text'):
                                        all_relevant_text += f"--- Document: {doc_display_name}, Section: {title} ---
{node['text']}

"
                                    elif os.path.exists(pdf_path) and pdf_path.lower().endswith(".pdf"):
                                        try:
                                            page_text = get_text_of_pages(pdf_path, node['start_index'], node['end_index'], tag=False)
                                            all_relevant_text += f"--- Document: {doc_display_name}, Section: {title} ---
{page_text}

"
                                        except Exception as e:
                                            pass
                        
                        st.write("3. 整合知识生成回答...")
                        status.update(label="多文档检索完成", state="complete", expanded=False)

                    # 3. Final Answer Generation
                    if not all_relevant_text:
                        full_answer = "抱歉，检索过程未能从相关文档中提取到足够的原文内容。请确保文档已正确处理且文件未被移动。"
                    else:
                        answer_prompt = f"""You are a professional research assistant. You have document snippets from multiple sources.
Answer the user's question based on the provided context. 
If the sources have conflicting information, mention it. 
Always cite the document names in your answer.

Question: {query}

Context:
{all_relevant_text[:15000]}

Assistant:"""
                        full_answer = ChatGPT_API(model=model_name, prompt=answer_prompt)
                    
                    st.markdown(full_answer)
                    if all_reference_nodes:
                        with st.expander("参考来源"):
                            for node_info in all_reference_nodes:
                                st.write(node_info)
                    
                    # Save history
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": full_answer,
                        "thinking": total_thinking,
                        "nodes": all_reference_nodes
                    })

st.markdown("---")
st.caption("Powered by PageIndex Framework - Vectorless Reasoning RAG")
