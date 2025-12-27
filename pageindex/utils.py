"""
PageIndex 工具函数模块

本模块包含 PageIndex 框架使用的各种工具函数，包括：
- Token 计数
- OpenAI API 调用
- JSON 处理
- PDF 文本提取
- 树结构操作
- 配置加载
"""

import tiktoken
import openai
import logging
import os
from datetime import datetime
import time
import json
import PyPDF2
import copy
import asyncio
import pymupdf
from io import BytesIO
from dotenv import load_dotenv
load_dotenv()
import logging
import yaml
from pathlib import Path
from types import SimpleNamespace as config

CHATGPT_API_KEY = os.getenv("CHATGPT_API_KEY")
CHATGPT_API_BASE = os.getenv("CHATGPT_API_BASE", "https://api.openai.com/v1")


def count_tokens(text, model=None):
    """
    计算文本的 token 数量
    
    参数:
        text: 要计算的文本
        model: 使用的模型名称，用于选择正确的编码器
    
    返回:
        token 数量
    """
    if not text:
        return 0
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        # 对于不支持的模型（如 gemini），使用 cl100k_base 编码（GPT-4 使用的编码）
        enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(text)
    return len(tokens)


def ChatGPT_API_with_finish_reason(model, prompt, api_key=None, api_base=None, chat_history=None):
    """
    调用 ChatGPT API 并返回完成原因
    
    参数:
        model: 模型名称
        prompt: 提示词
        api_key: API 密钥（可选）
        api_base: API 基础地址（可选）
        chat_history: 聊天历史（可选）
    
    返回:
        (响应内容, 完成原因) 元组
    """
    if api_key is None: api_key = os.getenv("CHATGPT_API_KEY")
    if api_base is None: api_base = os.getenv("CHATGPT_API_BASE", "https://api.openai.com/v1")
    max_retries = 10
    client = openai.OpenAI(api_key=api_key, base_url=api_base)
    for i in range(max_retries):
        try:
            if chat_history:
                messages = chat_history
                messages.append({"role": "user", "content": prompt})
            else:
                messages = [{"role": "user", "content": prompt}]
            
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
            )
            if response.choices[0].finish_reason == "length":
                return response.choices[0].message.content, "max_output_reached"
            else:
                return response.choices[0].message.content, "finished"

        except Exception as e:
            print('************* 正在重试 *************')
            logging.error(f"错误: {e}")
            if i < max_retries - 1:
                time.sleep(1)  # 重试前等待 1 秒
            else:
                logging.error('已达到最大重试次数，提示词: ' + prompt)
                return "Error"


def ChatGPT_API(model, prompt, api_key=None, api_base=None, chat_history=None):
    """
    调用 ChatGPT API
    
    参数:
        model: 模型名称
        prompt: 提示词
        api_key: API 密钥（可选）
        api_base: API 基础地址（可选）
        chat_history: 聊天历史（可选）
    
    返回:
        响应内容
    """
    if api_key is None: api_key = os.getenv("CHATGPT_API_KEY")
    if api_base is None: api_base = os.getenv("CHATGPT_API_BASE", "https://api.openai.com/v1")
    max_retries = 10
    client = openai.OpenAI(api_key=api_key, base_url=api_base)
    for i in range(max_retries):
        try:
            if chat_history:
                messages = chat_history
                messages.append({"role": "user", "content": prompt})
            else:
                messages = [{"role": "user", "content": prompt}]
            
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
            )
   
            return response.choices[0].message.content
        except Exception as e:
            print('************* 正在重试 *************')
            logging.error(f"错误: {e}")
            if i < max_retries - 1:
                time.sleep(1)  # 重试前等待 1 秒
            else:
                logging.error('已达到最大重试次数，提示词: ' + prompt)
                return "Error"
            

async def ChatGPT_API_async(model, prompt, api_key=None, api_base=None):
    """
    异步调用 ChatGPT API
    
    参数:
        model: 模型名称
        prompt: 提示词
        api_key: API 密钥（可选）
        api_base: API 基础地址（可选）
    
    返回:
        响应内容
    """
    if api_key is None: api_key = os.getenv("CHATGPT_API_KEY")
    if api_base is None: api_base = os.getenv("CHATGPT_API_BASE", "https://api.openai.com/v1")
    max_retries = 10
    messages = [{"role": "user", "content": prompt}]
    for i in range(max_retries):
        try:
            async with openai.AsyncOpenAI(api_key=api_key, base_url=api_base) as client:
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0,
                )
                return response.choices[0].message.content
        except Exception as e:
            print('************* 正在重试 *************')
            logging.error(f"错误: {e}")
            if i < max_retries - 1:
                await asyncio.sleep(1)  # 重试前等待 1 秒
            else:
                logging.error('已达到最大重试次数，提示词: ' + prompt)
                return "Error"  
            
            
def get_json_content(response):
    """
    从响应中提取 JSON 内容（去除 markdown 代码块标记）
    
    参数:
        response: 包含 JSON 的响应字符串
    
    返回:
        清理后的 JSON 字符串
    """
    start_idx = response.find("```json")
    if start_idx != -1:
        start_idx += 7
        response = response[start_idx:]
        
    end_idx = response.rfind("```")
    if end_idx != -1:
        response = response[:end_idx]
    
    json_content = response.strip()
    return json_content
         

def extract_json(content):
    """
    从内容中提取并解析 JSON
    
    参数:
        content: 包含 JSON 的字符串
    
    返回:
        解析后的 JSON 对象，解析失败返回空字典
    """
    try:
        # 首先尝试提取 ```json 和 ``` 之间的 JSON
        start_idx = content.find("```json")
        if start_idx != -1:
            start_idx += 7  # 调整索引到分隔符之后
            end_idx = content.rfind("```")
            json_content = content[start_idx:end_idx].strip()
        else:
            # 如果没有分隔符，假设整个内容可能是 JSON
            json_content = content.strip()

        # 清理可能导致解析错误的常见问题
        json_content = json_content.replace('None', 'null')  # 将 Python None 替换为 JSON null
        json_content = json_content.replace('\n', ' ').replace('\r', ' ')  # 移除换行符
        json_content = ' '.join(json_content.split())  # 规范化空白字符

        # 尝试解析并返回 JSON 对象
        return json.loads(json_content)
    except json.JSONDecodeError as e:
        logging.error(f"JSON 提取失败: {e}")
        # 如果初始解析失败，尝试进一步清理内容
        try:
            # 移除闭合括号前的尾随逗号
            json_content = json_content.replace(',]', ']').replace(',}', '}')
            return json.loads(json_content)
        except:
            logging.error("清理后仍无法解析 JSON")
            return {}
    except Exception as e:
        logging.error(f"提取 JSON 时发生意外错误: {e}")
        return {}


def write_node_id(data, node_id=0):
    """
    为树结构中的每个节点写入唯一的 node_id
    
    参数:
        data: 树结构数据
        node_id: 起始 ID
    
    返回:
        下一个可用的 node_id
    """
    if isinstance(data, dict):
        data['node_id'] = str(node_id).zfill(4)
        node_id += 1
        for key in list(data.keys()):
            if 'nodes' in key:
                node_id = write_node_id(data[key], node_id)
    elif isinstance(data, list):
        for index in range(len(data)):
            node_id = write_node_id(data[index], node_id)
    return node_id


def get_nodes(structure):
    """
    获取结构中的所有节点（不包含子节点信息）
    
    参数:
        structure: 树结构
    
    返回:
        节点列表
    """
    if isinstance(structure, dict):
        structure_node = copy.deepcopy(structure)
        structure_node.pop('nodes', None)
        nodes = [structure_node]
        for key in list(structure.keys()):
            if 'nodes' in key:
                nodes.extend(get_nodes(structure[key]))
        return nodes
    elif isinstance(structure, list):
        nodes = []
        for item in structure:
            nodes.extend(get_nodes(item))
        return nodes
    

def structure_to_list(structure):
    """
    将树结构转换为扁平列表
    
    参数:
        structure: 树结构
    
    返回:
        节点列表
    """
    if isinstance(structure, dict):
        nodes = []
        nodes.append(structure)
        if 'nodes' in structure:
            nodes.extend(structure_to_list(structure['nodes']))
        return nodes
    elif isinstance(structure, list):
        nodes = []
        for item in structure:
            nodes.extend(structure_to_list(item))
        return nodes

    
def get_leaf_nodes(structure):
    """
    获取树结构中的所有叶子节点
    
    参数:
        structure: 树结构
    
    返回:
        叶子节点列表
    """
    if isinstance(structure, dict):
        if not structure['nodes']:
            structure_node = copy.deepcopy(structure)
            structure_node.pop('nodes', None)
            return [structure_node]
        else:
            leaf_nodes = []
            for key in list(structure.keys()):
                if 'nodes' in key:
                    leaf_nodes.extend(get_leaf_nodes(structure[key]))
            return leaf_nodes
    elif isinstance(structure, list):
        leaf_nodes = []
        for item in structure:
            leaf_nodes.extend(get_leaf_nodes(item))
        return leaf_nodes


def is_leaf_node(data, node_id):
    """
    检查指定 node_id 的节点是否为叶子节点
    
    参数:
        data: 树结构数据
        node_id: 要检查的节点 ID
    
    返回:
        如果是叶子节点返回 True，否则返回 False
    """
    # 辅助函数：通过 node_id 查找节点
    def find_node(data, node_id):
        if isinstance(data, dict):
            if data.get('node_id') == node_id:
                return data
            for key in data.keys():
                if 'nodes' in key:
                    result = find_node(data[key], node_id)
                    if result:
                        return result
        elif isinstance(data, list):
            for item in data:
                result = find_node(item, node_id)
                if result:
                    return result
        return None

    # 查找具有给定 node_id 的节点
    node = find_node(data, node_id)

    # 检查节点是否为叶子节点
    if node and not node.get('nodes'):
        return True
    return False


def get_last_node(structure):
    """获取结构中的最后一个节点"""
    return structure[-1]


def extract_text_from_pdf(pdf_path):
    """
    从 PDF 文件中提取所有文本
    
    参数:
        pdf_path: PDF 文件路径
    
    返回:
        提取的文本字符串
    """
    pdf_reader = PyPDF2.PdfReader(pdf_path)
    # 返回文本而非列表
    text=""
    for page_num in range(len(pdf_reader.pages)):
        page = pdf_reader.pages[page_num]
        text+=page.extract_text()
    return text


def get_pdf_title(pdf_path):
    """
    获取 PDF 文件的标题
    
    参数:
        pdf_path: PDF 文件路径
    
    返回:
        PDF 标题，如果没有则返回 'Untitled'
    """
    pdf_reader = PyPDF2.PdfReader(pdf_path)
    meta = pdf_reader.metadata
    title = meta.title if meta and meta.title else 'Untitled'
    return title


def get_text_of_pages(pdf_path, start_page, end_page, tag=True):
    """
    获取 PDF 指定页面范围的文本
    
    参数:
        pdf_path: PDF 文件路径
        start_page: 起始页码（从 1 开始）
        end_page: 结束页码
        tag: 是否添加页码标签
    
    返回:
        提取的文本
    """
    pdf_reader = PyPDF2.PdfReader(pdf_path)
    text = ""
    for page_num in range(start_page-1, end_page):
        page = pdf_reader.pages[page_num]
        page_text = page.extract_text()
        if tag:
            text += f"<start_index_{page_num+1}>\n{page_text}\n<end_index_{page_num+1}>\n"
        else:
            text += page_text
    return text


def get_first_start_page_from_text(text):
    """从文本中获取第一个起始页码标签"""
    start_page = -1
    start_page_match = re.search(r'<start_index_(\d+)>', text)
    if start_page_match:
        start_page = int(start_page_match.group(1))
    return start_page


def get_last_start_page_from_text(text):
    """从文本中获取最后一个起始页码标签"""
    start_page = -1
    # 查找所有 start_index 标签的匹配
    start_page_matches = re.finditer(r'<start_index_(\d+)>', text)
    # 将迭代器转换为列表并获取最后一个匹配（如果存在）
    matches_list = list(start_page_matches)
    if matches_list:
        start_page = int(matches_list[-1].group(1))
    return start_page


def sanitize_filename(filename, replacement='-'):
    """
    清理文件名中的非法字符
    
    参数:
        filename: 原始文件名
        replacement: 替换字符
    
    返回:
        清理后的文件名
    """
    # 在 Linux 中，只有 '/' 和 '\0'（空字符）在文件名中是非法的
    # 空字符无法在字符串中表示，所以我们只处理 '/'
    return filename.replace('/', replacement)


def get_pdf_name(pdf_path):
    """
    获取 PDF 文件名
    
    参数:
        pdf_path: PDF 文件路径或 BytesIO 对象
    
    返回:
        PDF 文件名
    """
    # 提取 PDF 名称
    if isinstance(pdf_path, str):
        pdf_name = os.path.basename(pdf_path)
    elif isinstance(pdf_path, BytesIO):
        pdf_reader = PyPDF2.PdfReader(pdf_path)
        meta = pdf_reader.metadata
        pdf_name = meta.title if meta and meta.title else 'Untitled'
        pdf_name = sanitize_filename(pdf_name)
    return pdf_name


class JsonLogger:
    """
    JSON 格式的日志记录器
    
    将日志消息以 JSON 格式保存到文件
    """
    def __init__(self, file_path):
        # 提取 PDF 名称作为日志名称
        pdf_name = get_pdf_name(file_path)
            
        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filename = f"{pdf_name}_{current_time}.json"
        os.makedirs("./logs", exist_ok=True)
        # 初始化空列表以存储所有消息
        self.log_data = []

    def log(self, level, message, **kwargs):
        if isinstance(message, dict):
            self.log_data.append(message)
        else:
            self.log_data.append({'message': message})
        # 将新消息添加到日志数据
        
        # 将整个日志数据写入文件
        with open(self._filepath(), "w") as f:
            json.dump(self.log_data, f, indent=2)

    def info(self, message, **kwargs):
        self.log("INFO", message, **kwargs)

    def error(self, message, **kwargs):
        self.log("ERROR", message, **kwargs)

    def debug(self, message, **kwargs):
        self.log("DEBUG", message, **kwargs)

    def exception(self, message, **kwargs):
        kwargs["exception"] = True
        self.log("ERROR", message, **kwargs)

    def _filepath(self):
        return os.path.join("logs", self.filename)
    


def list_to_tree(data):
    """
    将扁平列表转换为树结构
    
    参数:
        data: 包含 structure 字段的节点列表
    
    返回:
        树结构
    """
    def get_parent_structure(structure):
        """辅助函数：获取父级结构编码"""
        if not structure:
            return None
        parts = str(structure).split('.')
        return '.'.join(parts[:-1]) if len(parts) > 1 else None
    
    # 第一遍：创建节点并跟踪父子关系
    nodes = {}
    root_nodes = []
    
    for item in data:
        structure = item.get('structure')
        node = {
            'title': item.get('title'),
            'start_index': item.get('start_index'),
            'end_index': item.get('end_index'),
            'nodes': []
        }
        
        nodes[structure] = node
        
        # 查找父节点
        parent_structure = get_parent_structure(structure)
        
        if parent_structure:
            # 如果父节点存在，添加为子节点
            if parent_structure in nodes:
                nodes[parent_structure]['nodes'].append(node)
            else:
                root_nodes.append(node)
        else:
            # 没有父节点，这是根节点
            root_nodes.append(node)
    
    # 辅助函数：清理空的子节点数组
    def clean_node(node):
        if not node['nodes']:
            del node['nodes']
        else:
            for child in node['nodes']:
                clean_node(child)
        return node
    
    # 清理并返回树
    return [clean_node(node) for node in root_nodes]


def add_preface_if_needed(data):
    """
    如果需要，添加前言节点
    
    如果第一个节点的 physical_index 大于 1，则在开头添加前言节点
    """
    if not isinstance(data, list) or not data:
        return data

    if data[0]['physical_index'] is not None and data[0]['physical_index'] > 1:
        preface_node = {
            "structure": "0",
            "title": "Preface",
            "physical_index": 1,
        }
        data.insert(0, preface_node)
    return data


def get_page_tokens(pdf_path, model="gpt-4o-2024-11-20", pdf_parser="PyPDF2"):
    """
    获取 PDF 每页的文本和 token 数量
    
    参数:
        pdf_path: PDF 文件路径或 BytesIO 对象
        model: 用于 token 计数的模型
        pdf_parser: PDF 解析器（PyPDF2 或 PyMuPDF）
    
    返回:
        (页面文本, token 数量) 元组的列表
    """
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        # 对于不支持的模型（如 gemini），使用 cl100k_base 编码
        enc = tiktoken.get_encoding("cl100k_base")
    if pdf_parser == "PyPDF2":
        pdf_reader = PyPDF2.PdfReader(pdf_path)
        page_list = []
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            page_text = page.extract_text()
            token_length = len(enc.encode(page_text))
            page_list.append((page_text, token_length))
        return page_list
    elif pdf_parser == "PyMuPDF":
        if isinstance(pdf_path, BytesIO):
            pdf_stream = pdf_path
            doc = pymupdf.open(stream=pdf_stream, filetype="pdf")
        elif isinstance(pdf_path, str) and os.path.isfile(pdf_path) and pdf_path.lower().endswith(".pdf"):
            doc = pymupdf.open(pdf_path)
        page_list = []
        for page in doc:
            page_text = page.get_text()
            token_length = len(enc.encode(page_text))
            page_list.append((page_text, token_length))
        return page_list
    else:
        raise ValueError(f"不支持的 PDF 解析器: {pdf_parser}")

        

def get_text_of_pdf_pages(pdf_pages, start_page, end_page):
    """获取指定页面范围的文本"""
    text = ""
    for page_num in range(start_page-1, end_page):
        text += pdf_pages[page_num][0]
    return text


def get_text_of_pdf_pages_with_labels(pdf_pages, start_page, end_page):
    """获取指定页面范围的文本（带页码标签）"""
    text = ""
    for page_num in range(start_page-1, end_page):
        text += f"<physical_index_{page_num+1}>\n{pdf_pages[page_num][0]}\n<physical_index_{page_num+1}>\n"
    return text


def get_number_of_pages(pdf_path):
    """获取 PDF 的总页数"""
    pdf_reader = PyPDF2.PdfReader(pdf_path)
    num = len(pdf_reader.pages)
    return num


def post_processing(structure, end_physical_index):
    """
    后处理：将 physical_index 转换为 start_index 和 end_index
    
    参数:
        structure: 结构列表
        end_physical_index: 文档的最后一页索引
    
    返回:
        处理后的树结构
    """
    # 首先在扁平列表中将 page_number 转换为 start_index
    for i, item in enumerate(structure):
        item['start_index'] = item.get('physical_index')
        if i < len(structure) - 1:
            if structure[i + 1].get('appear_start') == 'yes':
                item['end_index'] = structure[i + 1]['physical_index']-1
            else:
                item['end_index'] = structure[i + 1]['physical_index']
        else:
            item['end_index'] = end_physical_index
    tree = list_to_tree(structure)
    if len(tree)!=0:
        return tree
    else:
        # 移除 appear_start
        for node in structure:
            node.pop('appear_start', None)
            node.pop('physical_index', None)
        return structure


def clean_structure_post(data):
    """清理结构中的临时字段"""
    if isinstance(data, dict):
        data.pop('page_number', None)
        data.pop('start_index', None)
        data.pop('end_index', None)
        if 'nodes' in data:
            clean_structure_post(data['nodes'])
    elif isinstance(data, list):
        for section in data:
            clean_structure_post(section)
    return data


def remove_fields(data, fields=['text']):
    """
    从数据结构中移除指定字段
    
    参数:
        data: 数据结构
        fields: 要移除的字段列表
    
    返回:
        移除字段后的数据
    """
    if isinstance(data, dict):
        return {k: remove_fields(v, fields)
            for k, v in data.items() if k not in fields}
    elif isinstance(data, list):
        return [remove_fields(item, fields) for item in data]
    return data


def print_toc(tree, indent=0):
    """打印目录结构"""
    for node in tree:
        print('  ' * indent + node['title'])
        if node.get('nodes'):
            print_toc(node['nodes'], indent + 1)


def print_json(data, max_len=40, indent=2):
    """
    打印 JSON 数据（长字符串会被截断）
    
    参数:
        data: 要打印的数据
        max_len: 字符串最大长度
        indent: 缩进空格数
    """
    def simplify_data(obj):
        if isinstance(obj, dict):
            return {k: simplify_data(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [simplify_data(item) for item in obj]
        elif isinstance(obj, str) and len(obj) > max_len:
            return obj[:max_len] + '...'
        else:
            return obj
    
    simplified = simplify_data(data)
    print(json.dumps(simplified, indent=indent, ensure_ascii=False))


def remove_structure_text(data):
    """从结构中移除 text 字段"""
    if isinstance(data, dict):
        data.pop('text', None)
        if 'nodes' in data:
            remove_structure_text(data['nodes'])
    elif isinstance(data, list):
        for item in data:
            remove_structure_text(item)
    return data


def check_token_limit(structure, limit=110000):
    """
    检查结构中是否有节点超过 token 限制
    
    参数:
        structure: 树结构
        limit: token 限制
    """
    list = structure_to_list(structure)
    for node in list:
        num_tokens = count_tokens(node['text'], model='gpt-4o')
        if num_tokens > limit:
            print(f"节点 ID: {node['node_id']} 有 {num_tokens} 个 token")
            print("起始索引:", node['start_index'])
            print("结束索引:", node['end_index'])
            print("标题:", node['title'])
            print("\n")


def convert_physical_index_to_int(data):
    """将 physical_index 从字符串转换为整数"""
    if isinstance(data, list):
        for i in range(len(data)):
            # 检查项目是否为字典且有 'physical_index' 键
            if isinstance(data[i], dict) and 'physical_index' in data[i]:
                if isinstance(data[i]['physical_index'], str):
                    if data[i]['physical_index'].startswith('<physical_index_'):
                        data[i]['physical_index'] = int(data[i]['physical_index'].split('_')[-1].rstrip('>').strip())
                    elif data[i]['physical_index'].startswith('physical_index_'):
                        data[i]['physical_index'] = int(data[i]['physical_index'].split('_')[-1].strip())
    elif isinstance(data, str):
        if data.startswith('<physical_index_'):
            data = int(data.split('_')[-1].rstrip('>').strip())
        elif data.startswith('physical_index_'):
            data = int(data.split('_')[-1].strip())
        # 检查 data 是否为整数
        if isinstance(data, int):
            return data
        else:
            return None
    return data


def convert_page_to_int(data):
    """将 page 字段从字符串转换为整数"""
    for item in data:
        if 'page' in item and isinstance(item['page'], str):
            try:
                item['page'] = int(item['page'])
            except ValueError:
                # 转换失败时保留原值
                pass
    return data


def add_node_text(node, pdf_pages):
    """
    为节点添加文本内容
    
    参数:
        node: 节点或节点列表
        pdf_pages: PDF 页面列表
    """
    if isinstance(node, dict):
        start_page = node.get('start_index')
        end_page = node.get('end_index')
        node['text'] = get_text_of_pdf_pages(pdf_pages, start_page, end_page)
        if 'nodes' in node:
            add_node_text(node['nodes'], pdf_pages)
    elif isinstance(node, list):
        for index in range(len(node)):
            add_node_text(node[index], pdf_pages)
    return


def add_node_text_with_labels(node, pdf_pages):
    """为节点添加带页码标签的文本内容"""
    if isinstance(node, dict):
        start_page = node.get('start_index')
        end_page = node.get('end_index')
        node['text'] = get_text_of_pdf_pages_with_labels(pdf_pages, start_page, end_page)
        if 'nodes' in node:
            add_node_text_with_labels(node['nodes'], pdf_pages)
    elif isinstance(node, list):
        for index in range(len(node)):
            add_node_text_with_labels(node[index], pdf_pages)
    return


async def generate_node_summary(node, model=None):
    """
    为节点生成摘要
    
    参数:
        node: 包含 text 字段的节点
        model: 使用的模型
    
    返回:
        生成的摘要
    """
    prompt = f"""You are given a part of a document, your task is to generate a description of the partial document about what are main points covered in the partial document.

    Partial Document Text: {node['text']}
    
    Directly return the description, do not include any other text.
    """
    response = await ChatGPT_API_async(model, prompt)
    return response


async def generate_summaries_for_structure(structure, model=None):
    """
    为结构中的所有节点生成摘要
    
    参数:
        structure: 树结构
        model: 使用的模型
    
    返回:
        添加了摘要的结构
    """
    nodes = structure_to_list(structure)
    tasks = [generate_node_summary(node, model=model) for node in nodes]
    summaries = await asyncio.gather(*tasks)
    
    for node, summary in zip(nodes, summaries):
        node['summary'] = summary
    return structure


def create_clean_structure_for_description(structure):
    """
    创建用于文档描述生成的干净结构
    排除不必要的字段如 'text'
    
    参数:
        structure: 原始结构
    
    返回:
        清理后的结构
    """
    if isinstance(structure, dict):
        clean_node = {}
        # 只包含描述所需的基本字段
        for key in ['title', 'node_id', 'summary', 'prefix_summary']:
            if key in structure:
                clean_node[key] = structure[key]
        
        # 递归处理子节点
        if 'nodes' in structure and structure['nodes']:
            clean_node['nodes'] = create_clean_structure_for_description(structure['nodes'])
        
        return clean_node
    elif isinstance(structure, list):
        return [create_clean_structure_for_description(item) for item in structure]
    else:
        return structure


def generate_doc_description(structure, model=None):
    """
    为文档生成描述
    
    参数:
        structure: 文档结构
        model: 使用的模型
    
    返回:
        文档描述
    """
    prompt = f"""Your are an expert in generating descriptions for a document.
    You are given a structure of a document. Your task is to generate a one-sentence description for the document, which makes it easy to distinguish the document from other documents.
        
    Document Structure: {structure}
    
    Directly return the description, do not include any other text.
    """
    response = ChatGPT_API(model, prompt)
    return response


def reorder_dict(data, key_order):
    """按指定顺序重新排列字典的键"""
    if not key_order:
        return data
    return {key: data[key] for key in key_order if key in data}


def format_structure(structure, order=None):
    """
    格式化结构，按指定顺序排列字段
    
    参数:
        structure: 树结构
        order: 字段顺序列表
    
    返回:
        格式化后的结构
    """
    if not order:
        return structure
    if isinstance(structure, dict):
        if 'nodes' in structure:
            structure['nodes'] = format_structure(structure['nodes'], order)
        if not structure.get('nodes'):
            structure.pop('nodes', None)
        structure = reorder_dict(structure, order)
    elif isinstance(structure, list):
        structure = [format_structure(item, order) for item in structure]
    return structure


class ConfigLoader:
    """
    配置加载器
    
    从 YAML 文件加载默认配置，并与用户配置合并
    """
    def __init__(self, default_path: str = None):
        if default_path is None:
            default_path = Path(__file__).parent / "config.yaml"
        self._default_dict = self._load_yaml(default_path)

    @staticmethod
    def _load_yaml(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _validate_keys(self, user_dict):
        unknown_keys = set(user_dict) - set(self._default_dict)
        if unknown_keys:
            raise ValueError(f"未知的配置键: {unknown_keys}")

    def load(self, user_opt=None) -> config:
        """
        加载配置，将用户选项与默认值合并
        
        参数:
            user_opt: 用户配置（字典、config 对象或 None）
        
        返回:
            合并后的配置对象
        """
        if user_opt is None:
            user_dict = {}
        elif isinstance(user_opt, config):
            user_dict = vars(user_opt)
        elif isinstance(user_opt, dict):
            user_dict = user_opt
        else:
            raise TypeError("user_opt 必须是 dict、config(SimpleNamespace) 或 None")

        self._validate_keys(user_dict)
        merged = {**self._default_dict, **user_dict}
        return config(**merged)
