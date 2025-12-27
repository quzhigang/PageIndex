
## 按元数据搜索文档
<callout>带元数据支持的 PageIndex 目前处于封闭测试阶段。填写此表单以申请提前访问此功能。</callout>

对于可以通过元数据轻松区分的文档，我们建议使用元数据来搜索文档。
此方法适用于以下文档类型：
- 按公司和时间段分类的财务报告
- 按案件类型分类的法律文档
- 按患者或病情分类的医疗记录
- 以及其他许多类型

在这种情况下，您可以利用文档的元数据进行搜索。一种流行的方法是使用"查询转 SQL"进行文档检索。


### 示例流程

#### PageIndex 树生成
将所有文档上传到 PageIndex 以获取其 `doc_id`。

#### 设置 SQL 表

将文档及其元数据和 PageIndex `doc_id` 存储在数据库表中。

#### 查询转 SQL

使用 LLM 将用户的检索请求转换为 SQL 查询以获取相关文档。

#### 使用 PageIndex 检索

使用检索到的文档的 PageIndex `doc_id`，通过 PageIndex 检索 API 进行进一步检索。

## 💬 帮助与社区
如果您需要针对您的用例进行文档搜索的任何建议，请联系我们。

- 🤝 [加入我们的 Discord](https://discord.gg/VuXuf29EUj)  
- 📨 [给我们留言](https://ii2abc2jejf.typeform.com/to/meB40zV0)
