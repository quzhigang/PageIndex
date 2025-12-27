
## 按描述搜索文档

对于没有元数据的文档，您可以使用 LLM 生成的描述来帮助文档选择。这是一种轻量级方法，最适合少量文档。


### 示例流程


#### PageIndex 树生成
将所有文档上传到 PageIndex 以获取其 `doc_id` 和树结构。

#### 描述生成

根据文档的 PageIndex 树结构和节点摘要为每个文档生成描述。
```python
prompt = f"""
你将获得一个文档的目录结构。
你的任务是为该文档生成一句话描述，使其易于与其他文档区分。
    
文档树结构: {PageIndex_Tree}

直接返回描述，不要包含任何其他文本。
"""
```

#### 使用 LLM 搜索

使用 LLM 通过将用户查询与生成的描述进行比较来选择相关文档。

以下是基于描述进行文档选择的示例提示：

```python
prompt = f""" 
你将获得一个包含文档 ID、文件名和描述的文档列表。你的任务是选择可能包含与回答用户查询相关信息的文档。

查询: {query}

文档: [
    {
        "doc_id": "xxx",
        "doc_name": "xxx",
        "doc_description": "xxx"
    }
]

响应格式:
{{
    "thinking": "<你选择文档的推理过程>",
    "answer": <相关 doc_id 的 Python 列表>, 例如 ['doc_id1', 'doc_id2']。如果没有相关文档则返回 []。
}}

仅返回 JSON 结构，不要有额外输出。
"""
```

#### 使用 PageIndex 检索

使用检索到的文档的 PageIndex `doc_id`，通过 PageIndex 检索 API 进行进一步检索。



## 💬 帮助与社区
如果您需要针对您的用例进行文档搜索的任何建议，请联系我们。

- 🤝 [加入我们的 Discord](https://discord.gg/VuXuf29EUj)  
- 📨 [给我们留言](https://ii2abc2jejf.typeform.com/to/meB40zV0)
