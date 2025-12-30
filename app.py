import streamlit as st
import os
import json
import asyncio
from datetime import datetime
from pageindex import page_index_main, config
from pageindex.page_index_md import md_to_tree
from pageindex.utils import ConfigLoader, ChatGPT_API, ChatGPT_API_async, get_text_of_pages, remove_fields
from pageindex.vector_index import get_vector_index, search_documents, build_index_for_document
import pandas as pd

st.set_page_config(page_title="PageIndex 网页界面", page_icon="🌲", layout="wide")

# 减少页面顶部空白，并设置上传文件列表为滚动显示
st.markdown("""
<style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 0rem;
    }
    header {
        visibility: hidden;
    }
    .stMainBlockContainer {
        padding-top: 1rem;
    }
    /* 上传文件列表滚动显示 */
    [data-testid="stFileUploaderDropzoneInput"] + div {
        max-height: 200px;
        overflow-y: auto;
    }
    /* 上传文件预览区域滚动 */
    .stFileUploader > div > div:last-child {
        max-height: 150px;
        overflow-y: auto;
    }
</style>
""", unsafe_allow_html=True)

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


def load_document_structure(doc_name: str, results_dir: str):
    """加载文档的结构 JSON 文件"""
    possible_names = [
        f"{doc_name}_structure.json",
        f"{doc_name.replace('.pdf', '')}_structure.json",
        f"{doc_name.replace('.md', '')}_structure.json",
    ]
    
    for name in possible_names:
        path = os.path.join(results_dir, name)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return None


# 侧边栏配置
st.sidebar.header("模型配置")
api_key = st.sidebar.text_input("API 密钥", value=os.getenv("CHATGPT_API_KEY", ""), type="password")
api_base = st.sidebar.text_input("API 基础地址", value=os.getenv("CHATGPT_API_BASE", "https://api.openai.com/v1"))

config_loader = ConfigLoader()
default_config = config_loader.load()
model_name = st.sidebar.text_input("模型名称", value=os.getenv("CHATGPT_MODEL", "gpt-4o"))

st.sidebar.header("PageIndex 配置")
toc_check_pages = st.sidebar.number_input("目录检查页数", value=default_config.toc_check_page_num)
max_pages_per_node = st.sidebar.number_input("每节点最大页数", value=default_config.max_page_num_each_node)
max_tokens_per_node = st.sidebar.number_input("每节点最大令牌数", value=default_config.max_token_num_each_node)

st.sidebar.header("向量检索配置")
vector_top_k = st.sidebar.slider("检索结果数量 (Top-K)", min_value=1, max_value=50, value=10)

# 默认设置
if_add_doc_description = "no"
if_add_node_text = "no"

# 原理介绍内容
PRINCIPLE_CONTENT = """
## PageIndex 检索原理对比

### 一、三种检索方式对比
| 特性 | 传统向量检索 | PageIndex 原版（Vectorless） | 本次优化（混合检索） |
|------|-------------|---------------------------|-------------------|
| 索引方式 | 文档切片 → 向量化 | 文档 → 目录树结构 | 目录树 + 节点向量 |
| 检索方式 | 向量相似度匹配 | LLM 推理定位 | 向量召回 + 结构定位 |
| Token 消耗 | 0（检索阶段） | 高（每次查询需多次 LLM 调用） | 0（检索阶段） |
| 检索速度 | 毫秒级 | 秒级（依赖 LLM 响应） | 毫秒级 |
| 上下文保留 | 差（切片破坏上下文） | 优（保留文档层级结构） | 优（保留结构信息） |
| 语义理解 | 浅层（向量相似度） | 深层（LLM 推理） | 中等（向量 + 摘要） |

### 二、PageIndex 原版检索原理（Vectorless RAG）
**核心理念**：不对文档进行向量化，而是利用 LLM 的推理能力在文档目录结构中定位信息。

**检索流程**：
```
用户查询 
    ↓
1. LLM 筛选相关文档（根据文档名称和描述）
    ↓
2. LLM 在目录树中推理定位（传递完整树结构给 LLM）
    ↓
3. 根据定位的节点提取原文（start_index → end_index）
    ↓
4. LLM 生成最终答案
```

**优点**：
- 保留文档的层级结构和上下文关系
- LLM 可以进行深层语义推理
- 不需要向量数据库

**缺点**：
- 每次查询消耗大量 Token（需要传递完整树结构）  
- 检索速度慢（依赖 LLM 响应时间）
- 文档数量增多时，Token 消耗线性增长

### 三、传统向量检索原理
**核心理念**：将文档切分为固定大小的块，向量化后通过相似度匹配检索。

**检索流程**：
```
用户查询 
    ↓
1. 查询文本向量化
    ↓
2. 向量相似度检索 Top-K 文档块
    ↓
3. 拼接检索到的文档块
    ↓
4. LLM 生成最终答案
```

**优点**：
- 检索速度快（毫秒级）
- 检索阶段不消耗 Token

**缺点**：
- 切片破坏文档上下文
- 无法理解文档层级结构
- 可能检索到不相关的片段

### 四、本系统优化方案（混合检索）
**核心理念**：结合向量检索的速度优势和目录树结构的上下文优势。

**检索流程**：
```
用户查询 
    ↓
1. 查询文本向量化
    ↓
2. 向量检索 Top-K 相关节点（基于节点标题+摘要的向量）
    ↓
3. 根据节点的 start_index/end_index 提取原文
    ↓
4. LLM 生成最终答案
```

**优点**：
- 检索速度快（毫秒级）
- 检索阶段不消耗 Token
- 保留了文档的层级结构信息
- 每个节点有完整的上下文（不是随机切片）

**关键差异**：
- 向量化的是节点摘要而非原文切片
- 检索单位是目录节点而非固定大小的块
- 保留了节点的层级路径和页码范围信息
"""

# 标题和原理介绍按钮
col_title, col_info = st.columns([6, 1])
with col_title:
    st.title("🌲 PageIndex + Vector 智能RAG检索系统")
with col_info:
    st.write("")  # 占位，使按钮垂直居中
    if st.button("ℹ️ 原理介绍", help="点击查看检索原理"):
        st.session_state.show_principle = True

# 原理介绍弹窗
if st.session_state.get("show_principle", False):
    @st.dialog("📖 PageIndex 检索原理介绍", width="large")
    def show_principle_dialog():
        st.markdown(PRINCIPLE_CONTENT)
        if st.button("关闭", type="primary"):
            st.session_state.show_principle = False
            st.rerun()
    show_principle_dialog()

tab1, tab2, tab3 = st.tabs(["📄 文档处理", "💬 智能对话", "📊 向量索引"])

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
                # 显示总体进度信息
                overall_status = st.empty()
                # 单文档进度条
                progress_bar = st.progress(0.0)
                status_text = st.empty()
                all_results_container = st.container()
                
                for i, uploaded_file in enumerate(uploaded_files):
                    file_extension = os.path.splitext(uploaded_file.name)[1].lower()
                    overall_status.info(f"📁 总进度: {i+1}/{total_files} 个文件")
                    status_text.text(f"正在处理: {uploaded_file.name}")
                    # 重置进度条为0
                    progress_bar.progress(0.0)
                    
                    try:
                        # 阶段1: 保存文件 (10%)
                        progress_bar.progress(0.1)
                        file_path = os.path.join(upload_dir, uploaded_file.name)
                        with open(file_path, "wb") as f:
                            f.write(uploaded_file.getvalue())
                        
                        # 阶段2: 开始处理 (20%)
                        progress_bar.progress(0.2)
                        result = None
                        if file_extension == ".pdf":
                            # 阶段3: PDF解析中 (40%)
                            progress_bar.progress(0.4)
                            opt = config(
                                model=model_name,
                                toc_check_page_num=toc_check_pages,
                                max_page_num_each_node=max_pages_per_node,
                                max_token_num_each_node=max_tokens_per_node,
                                if_add_node_id="yes",
                                if_add_node_summary="yes",
                                if_add_doc_description=if_add_doc_description,
                                if_add_node_text=if_add_node_text,
                                if_build_vector_index="yes"  # 自动构建向量索引
                            )
                            result = page_index_main(file_path, opt)
                        elif file_extension in [".md", ".markdown"]:
                            # 阶段3: Markdown解析中 (40%)
                            progress_bar.progress(0.4)
                            result = asyncio.run(md_to_tree(
                                md_path=file_path,
                                if_thinning=False,
                                if_add_node_summary=True,
                                model=model_name,
                                if_add_doc_description=(if_add_doc_description == "yes"),
                                if_add_node_text=True,  # Markdown 文件强制保留完整文本以支持检索
                                if_add_node_id=True,
                                if_build_vector_index=True  # 自动构建向量索引
                            ))
                        
                        # 阶段4: 生成摘要中 (70%)
                        progress_bar.progress(0.7)

                        if result:
                            # 阶段5: 保存结果 (90%)
                            progress_bar.progress(0.9)
                            file_base_name = os.path.splitext(uploaded_file.name)[0]
                            result_file_path = os.path.join(results_dir, f"{file_base_name}_structure.json")
                            with open(result_file_path, "w", encoding="utf-8") as f:
                                json.dump(result, f, indent=2, ensure_ascii=False)
                            
                            # 阶段6: 完成 (100%)
                            progress_bar.progress(1.0)
                            with all_results_container:
                                with st.expander(f"✅ {uploaded_file.name} 处理成功", expanded=False):
                                    st.info(f"JSON 已自动保存至: {result_file_path}")
                                    st.json(result)
                    except Exception as e:
                        progress_bar.progress(1.0)
                        with all_results_container:
                            st.error(f"❌ {uploaded_file.name} 处理出错: {str(e)}")
                
                overall_status.success(f"🎉 所有任务处理完成！共处理 {total_files} 个文件")
                status_text.empty()
                progress_bar.empty()
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
                vector_index = get_vector_index()
                
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
                        
                        # 删除向量索引
                        try:
                            vector_index.delete_document(file_base_name)
                        except Exception as e:
                            st.warning(f"删除 {file_base_name} 的向量索引失败: {e}")
                        
                        deleted_files.append(filename)
                
                if deleted_files:
                    st.success(f"已删除 {len(deleted_files)} 个文件")
                    st.session_state.selected_files = {}
                    st.rerun()
                else:
                    st.warning("请先选择要删除的文件")
        
        # 使用 data_editor 实现紧凑的可选择表格，设置固定高度实现滚动
        df = pd.DataFrame(files_info)
        df.insert(0, '选择', False)
        
        # 将序号转为字符串以便居中显示
        df['序号'] = df['序号'].astype(str)
        
        # 计算表格高度：每行约35px，表头约35px，最大显示10行
        table_height = min(len(files_info) * 35 + 35, 400)
        
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
            height=table_height,
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

# 选项卡 2: 智能对话 (RAG) - 使用向量检索
with tab2:
    st.header("跨文档智能对话")
    
    # 检查向量索引状态
    try:
        vector_index = get_vector_index()
        stats = vector_index.get_stats()
        
        if stats["total_nodes"] == 0:
            st.warning("向量索引为空。请先在「文档处理」选项卡中处理文件，或在「向量索引」选项卡中重建索引。")
        else:
            st.success(f"✅ 向量索引就绪：{stats['total_documents']} 个文档，{stats['total_nodes']} 个节点")
    except Exception as e:
        st.error(f"向量索引初始化失败: {e}")
        st.info("请检查 Embedding 模型配置是否正确。")

    # 初始化聊天历史
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 创建聊天消息容器
    chat_container = st.container()
    
    # 聊天输入放在容器外面（底部）
    query = st.chat_input("向整个文档库提问...")
    
    # 在容器内显示聊天消息
    with chat_container:
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

    # 处理用户输入
    if query:
        if not api_key:
            st.error("请先在侧边栏配置 API 密钥")
        else:
            update_api_config(api_key, api_base)
            st.session_state.messages.append({"role": "user", "content": query})
            with st.chat_message("user"):
                st.markdown(query)

            with st.chat_message("assistant"):
                with st.status("正在进行向量检索...", expanded=True) as status:
                    thinking_parts = []
                    all_reference_nodes = []
                    all_relevant_text = ""
                    
                    # 1. 向量检索（毫秒级）
                    st.write("1. 向量相似度检索...")
                    try:
                        search_results = search_documents(query, top_k=vector_top_k)
                        thinking_parts.append(f"向量检索返回 {len(search_results)} 个相关节点")
                    except Exception as e:
                        st.error(f"向量检索失败: {e}")
                        search_results = []
                    
                    if search_results:
                        # 按文档分组
                        doc_results = {}
                        for result in search_results:
                            doc_name = result["doc_name"]
                            if doc_name not in doc_results:
                                doc_results[doc_name] = []
                            doc_results[doc_name].append(result)
                        
                        st.write(f"找到 {len(search_results)} 个相关节点，来自 {len(doc_results)} 个文档")
                        
                        # 2. 内容提取
                        st.write("2. 提取相关内容...")
                        for doc_name, results in doc_results.items():
                            doc_data = load_document_structure(doc_name, results_dir)
                            if not doc_data:
                                thinking_parts.append(f"[{doc_name}] 未找到结构文件")
                                continue
                            
                            node_map = get_node_mapping(doc_data.get("structure", []))
                            
                            for result in results:
                                node_id = result["node_id"]
                                title = result["title"]
                                score = result.get("score", 0)
                                
                                all_reference_nodes.append(f"[{doc_name}] {title} (相似度: {score:.3f})")
                                
                                node = node_map.get(node_id)
                                if node and node.get("text"):
                                    all_relevant_text += f"\n--- 文档: {doc_name}, 章节: {title} ---\n{node['text']}\n"
                                elif result.get("summary"):
                                    all_relevant_text += f"\n--- 文档: {doc_name}, 章节: {title} (摘要) ---\n{result['summary']}\n"
                        
                        st.write("3. 生成回答...")
                        status.update(label="向量检索完成", state="complete", expanded=False)
                    else:
                        status.update(label="未找到相关内容", state="error", expanded=False)

                # 3. 生成答案
                if not all_relevant_text.strip():
                    full_answer = "抱歉，未能从文档库中找到与您问题相关的内容。请尝试换一种方式提问，或确保相关文档已被处理。"
                else:
                    answer_prompt = f"""你是一个专业的研究助手。你有来自多个来源的文档片段。
根据提供的上下文回答用户的问题。
如果来源有冲突的信息，请提及。
在回答中始终引用文档名称。

问题: {query}

上下文:
{all_relevant_text[:15000]}

助手:"""
                    try:
                        full_answer = ChatGPT_API(model=model_name, prompt=answer_prompt)
                    except Exception as e:
                        full_answer = f"答案生成失败: {str(e)}"
                
                st.markdown(full_answer)
                if all_reference_nodes:
                    with st.expander("参考来源"):
                        for node_info in all_reference_nodes:
                            st.write(node_info)
                
                # 保存历史记录
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": full_answer,
                    "thinking": "\n".join(thinking_parts),
                    "nodes": all_reference_nodes
                })

# 选项卡 3: 向量索引管理
with tab3:
    st.header("向量索引管理")
    
    # 显示索引统计
    try:
        vector_index = get_vector_index()
        stats = vector_index.get_stats()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("总节点数", stats["total_nodes"])
        with col2:
            st.metric("已索引文档数", stats["total_documents"])
        with col3:
            st.metric("索引状态", "正常" if stats["total_nodes"] > 0 else "空")
        
        if stats["documents"]:
            st.subheader("已索引文档列表")
            for doc in stats["documents"]:
                node_count = vector_index.get_document_node_count(doc)
                st.write(f"- **{doc}**: {node_count} 个节点")
    except Exception as e:
        st.error(f"获取索引统计失败: {e}")
    
    st.markdown("---")
    
    # 索引操作
    col_rebuild, col_clear = st.columns(2)
    
    with col_rebuild:
        if st.button("🔄 重建所有索引", type="primary"):
            with st.spinner("正在重建索引..."):
                try:
                    vector_index = get_vector_index()
                    
                    structure_files = [f for f in os.listdir(results_dir) if f.endswith("_structure.json")]
                    
                    if not structure_files:
                        st.warning("没有找到任何结构文件")
                    else:
                        progress = st.progress(0)
                        rebuilt_count = 0
                        
                        for i, filename in enumerate(structure_files):
                            try:
                                filepath = os.path.join(results_dir, filename)
                                with open(filepath, "r", encoding="utf-8") as f:
                                    data = json.load(f)
                                
                                doc_name = data.get("doc_name", filename.replace("_structure.json", ""))
                                doc_description = data.get("doc_description", "")
                                structure = data.get("structure", [])
                                
                                node_count = vector_index.add_document(doc_name, structure, doc_description)
                                rebuilt_count += 1
                                
                            except Exception as e:
                                st.warning(f"重建 {filename} 失败: {e}")
                            
                            progress.progress((i + 1) / len(structure_files))
                        
                        st.success(f"✅ 索引重建完成！共处理 {rebuilt_count} 个文档")
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"重建索引失败: {e}")
    
    with col_clear:
        if st.button("🗑️ 清空所有索引", type="secondary"):
            try:
                vector_index = get_vector_index()
                docs = vector_index.get_all_documents()
                
                for doc in docs:
                    vector_index.delete_document(doc)
                
                st.success(f"✅ 已清空 {len(docs)} 个文档的索引")
                st.rerun()
            except Exception as e:
                st.error(f"清空索引失败: {e}")
    
    # Embedding 模型配置信息
    st.markdown("---")
    st.subheader("Embedding 模型配置")
    
    embedding_model_name = os.getenv("EMBEDDING_MODEL_NAME", "bge-m3:latest")
    embedding_api_url = os.getenv("EMBEDDING_MODEL_API_URL", "http://10.20.2.135:11434")
    
    st.code(f"""
EMBEDDING_MODEL_NAME={embedding_model_name}
EMBEDDING_MODEL_API_URL={embedding_api_url}
EMBEDDING_MODEL_TYPE=ollama
    """, language="bash")
    
    # 测试 Embedding 连接
    if st.button("🔗 测试 Embedding 连接"):
        with st.spinner("正在测试连接..."):
            try:
                from pageindex.vector_index import OllamaEmbedding
                embedding_model = OllamaEmbedding()
                test_embedding = embedding_model.embed("测试文本")
                st.success(f"✅ 连接成功！Embedding 维度: {len(test_embedding)}")
            except Exception as e:
                st.error(f"❌ 连接失败: {e}")

st.markdown("---")
st.caption("由 PageIndex 框架驱动 - 混合向量检索 RAG")
