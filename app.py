import streamlit as st
import os
import json
import asyncio
from datetime import datetime
from pageindex import page_index_main, config
from pageindex.page_index_md import md_to_tree
from pageindex.utils import ConfigLoader, ChatGPT_API, ChatGPT_API_async, get_text_of_pages, remove_fields
import pandas as pd

st.set_page_config(page_title="PageIndex 网页界面", page_icon="🌲", layout="wide")

# Helper Functions
def update_api_config(api_key, api_base):
    os.environ["CHATGPT_API_KEY"] = api_key
    os.environ["CHATGPT_API_BASE"] = api_base
    import pageindex.utils
    pageindex.utils.CHATGPT_API_KEY = api_key
    pageindex.utils.CHATGPT_API_BASE = api_base

def get_file_size_str(size_bytes):
    """将字节大小转换为可读格式"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"

def get_file_type(filename):
    """获取文件类型描述"""
    ext = os.path.splitext(filename)[1].lower()
    type_map = {
        '.pdf': 'PDF 文档',
        '.md': 'Markdown 文档',
        '.markdown': 'Markdown 文档'
    }
    return type_map.get(ext, '未知类型')

def get_uploaded_files_info(upload_dir):
    """获取已上传文件的详细信息"""
    files_info = []
    if os.path.exists(upload_dir):
        for idx, filename in enumerate(os.listdir(upload_dir), 1):
            filepath = os.path.join(upload_dir, filename)
            if os.path.isfile(filepath):
                stat = os.stat(filepath)
                files_info.append({
                    '序号': idx,
                    '文件名': filename,
                    '上传时间': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    '文件大小': get_file_size_str(stat.st_size),
                    '文件类型': get_file_type(filename)
                })
    return files_info

def check_duplicate_files(uploaded_files, upload_dir):
    """检测重复文件"""
    duplicates = []
    if os.path.exists(upload_dir):
        existing_files = set(os.listdir(upload_dir))
        for uploaded_file in uploaded_files:
            if uploaded_file.name in existing_files:
                duplicates.append(uploaded_file.name)
    return duplicates

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
    except Exception as e:
        st.error(f"文档筛选解析失败: {e}")
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

# 侧边栏配置
st.sidebar.header("模型配置")
api_key = st.sidebar.text_input("API 密钥", value=os.getenv("CHATGPT_API_KEY", ""), type="password")
api_base = st.sidebar.text_input("API 基础地址", value=os.getenv("CHATGPT_API_BASE", "https://api.openai.com/v1"))

config_loader = ConfigLoader()
default_config = config_loader.load()
model_name = st.sidebar.text_input("模型名称", value=default_config.model)

st.sidebar.header("PageIndex 配置")
toc_check_pages = st.sidebar.number_input("目录检查页数", value=default_config.toc_check_page_num)
max_pages_per_node = st.sidebar.number_input("每节点最大页数", value=default_config.max_page_num_each_node)
max_tokens_per_node = st.sidebar.number_input("每节点最大令牌数", value=default_config.max_token_num_each_node)

# 默认设置
if_add_doc_description = "no"
if_add_node_text = "no"

st.title("🌲 PageIndex 智能文档代理")

tab1, tab2 = st.tabs(["📄 文档处理", "💬 智能对话"])

upload_dir = "uploads"
results_dir = "results"
os.makedirs(upload_dir, exist_ok=True)
os.makedirs(results_dir, exist_ok=True)

# 选项卡 1: 文档处理
with tab1:
    st.header("处理新文档")
    uploaded_files = st.file_uploader(
        "上传文件", 
        type=["pdf", "md", "markdown"], 
        accept_multiple_files=True,
        key="file_uploader"
    )

    # 重复文件检测
    if uploaded_files:
        duplicates = check_duplicate_files(uploaded_files, upload_dir)
        if duplicates:
            st.warning(f"⚠️ 检测到重复文件！以下文件已存在于上传目录中：\n\n**{', '.join(duplicates)}**\n\n继续处理将覆盖原有文件。")

        if st.button("🚀 开始批量处理"):
            if not api_key:
                st.error("请输入 API 密钥！")
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
                                if_add_node_text=True,  # Markdown 文件强制保留完整文本以支持检索
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

    # 文件详细清单
    st.markdown("---")
    files_info = get_uploaded_files_info(upload_dir)
    
    # 标题和删除按钮在同一行
    col_title, col_btn = st.columns([4, 1])
    with col_title:
        st.subheader("📋 已处理文件清单")
    
    if files_info:
        file_names = [f['文件名'] for f in files_info]
        
        # 初始化选中状态
        if "selected_files" not in st.session_state:
            st.session_state.selected_files = {name: False for name in file_names}
        
        # 同步新文件到选中状态
        for name in file_names:
            if name not in st.session_state.selected_files:
                st.session_state.selected_files[name] = False
        
        with col_btn:
            if st.button("🗑️ 删除选中", type="secondary"):
                deleted_files = []
                for filename, selected in st.session_state.selected_files.items():
                    if selected:
                        # 删除原始文件
                        file_path = os.path.join(upload_dir, filename)
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        
                        # 删除对应的索引 JSON 文件
                        file_base_name = os.path.splitext(filename)[0]
                        json_path = os.path.join(results_dir, f"{file_base_name}_structure.json")
                        if os.path.exists(json_path):
                            os.remove(json_path)
                        
                        deleted_files.append(filename)
                
                if deleted_files:
                    st.success(f"已删除 {len(deleted_files)} 个文件")
                    st.session_state.selected_files = {}
                    st.rerun()
                else:
                    st.warning("请先选择要删除的文件")
        
        # 使用 data_editor 实现紧凑的可选择表格
        df = pd.DataFrame(files_info)
        df.insert(0, '选择', False)
        
        # 将序号转为字符串以便居中显示
        df['序号'] = df['序号'].astype(str)
        
        edited_df = st.data_editor(
            df,
            column_config={
                "选择": st.column_config.CheckboxColumn(
                    "选择",
                    help="选择要删除的文件",
                    default=False,
                ),
                "序号": st.column_config.TextColumn("序号", width="small"),
                "文件名": st.column_config.TextColumn("文件名", width="medium"),
                "上传时间": st.column_config.TextColumn("上传时间", width="medium"),
                "文件大小": st.column_config.TextColumn("大小", width="small"),
                "文件类型": st.column_config.TextColumn("类型", width="small"),
            },
            disabled=["序号", "文件名", "上传时间", "文件大小", "文件类型"],
            hide_index=True,
            use_container_width=True,
            key="file_table"
        )
        
        # 更新选中状态
        for idx, row in edited_df.iterrows():
            st.session_state.selected_files[row['文件名']] = row['选择']
        
        st.caption(f"共 {len(files_info)} 个文件")
    else:
        with col_btn:
            st.empty()
        st.info("暂无已上传的文件。请上传文件进行处理。")

# 选项卡 2: 智能对话 (RAG)
with tab2:
    st.header("跨文档智能对话")
    
    # 加载所有可用索引
    available_indices = [f for f in os.listdir(results_dir) if f.endswith("_structure.json")]
    
    if not available_indices:
        st.warning("尚未处理任何文档。请先在「文档处理」选项卡中处理文件。")
    else:

        # 初始化聊天历史
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # 显示聊天消息
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

        # 聊天输入
        if query := st.chat_input("向整个文档库提问..."):
            if not api_key:
                st.error("请先在侧边栏配置 API 密钥")
            else:
                update_api_config(api_key, api_base)
                st.session_state.messages.append({"role": "user", "content": query})
                with st.chat_message("user"):
                    st.markdown(query)

                with st.chat_message("assistant"):
                    with st.status("正在进行多文档智能检索...", expanded=True) as status:
                        # 1. 筛选相关文档
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
                        
                        # 2. 在每个相关文档中搜索
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
                            
                            # 对此文档进行树搜索
                            search_res = asyncio.run(tree_search(query, index_data['structure'], model_name))
                            if search_res.get('thinking'):
                                total_thinking += f"**[{doc_display_name}]**: {search_res['thinking']}"
                            
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
                                    title = node.get('title', '未知')
                                    start_p = node.get('start_index', '?')
                                    all_reference_nodes.append(f"[{doc_display_name}] {title} (第{start_p}页)")
                                    
                                    if node.get('text'):
                                        all_relevant_text += f"--- 文档: {doc_display_name}, 章节: {title} ---{node['text']}"
                                    elif os.path.exists(pdf_path) and pdf_path.lower().endswith(".pdf"):
                                        try:
                                            page_text = get_text_of_pages(pdf_path, node['start_index'], node['end_index'], tag=False)
                                            all_relevant_text += f"--- 文档: {doc_display_name}, 章节: {title} ---{page_text}"
                                        except Exception as e:
                                            pass
                        
                        st.write("3. 整合知识生成回答...")
                        status.update(label="多文档检索完成", state="complete", expanded=False)

                    # 3. 最终答案生成
                    if not all_relevant_text:
                        full_answer = "抱歉，检索过程未能从相关文档中提取到足够的原文内容。请确保文档已正确处理且文件未被移动。"
                    else:
                        answer_prompt = f"""你是一个专业的研究助手。你有来自多个来源的文档片段。
根据提供的上下文回答用户的问题。
如果来源有冲突的信息，请提及。
在回答中始终引用文档名称。

问题: {query}

上下文:
{all_relevant_text[:15000]}

助手:"""
                        full_answer = ChatGPT_API(model=model_name, prompt=answer_prompt)
                    
                    st.markdown(full_answer)
                    if all_reference_nodes:
                        with st.expander("参考来源"):
                            for node_info in all_reference_nodes:
                                st.write(node_info)
                    
                    # 保存历史记录
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": full_answer,
                        "thinking": total_thinking,
                        "nodes": all_reference_nodes
                    })

st.markdown("---")
st.caption("由 PageIndex 框架驱动 - 无向量推理 RAG")
