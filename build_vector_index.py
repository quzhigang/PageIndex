"""
批量构建向量索引脚本

遍历 results 文件夹中的所有 JSON 结构文件，为每个文档构建向量索引。
"""

import os
import json
import time
from pageindex.vector_index import get_vector_index

RESULTS_DIR = "results"


def build_all_indexes(doc_delay: float = 1.0):
    """遍历 results 文件夹，为所有文档构建向量索引"""
    
    # 检查 results 目录是否存在
    if not os.path.exists(RESULTS_DIR):
        print(f"错误: {RESULTS_DIR} 目录不存在")
        return
    
    # 获取所有 JSON 结构文件
    structure_files = [f for f in os.listdir(RESULTS_DIR) if f.endswith("_structure.json")]
    
    if not structure_files:
        print(f"在 {RESULTS_DIR} 目录中没有找到任何结构文件")
        return
    
    print(f"找到 {len(structure_files)} 个结构文件，开始构建向量索引...\n")
    
    # 获取向量索引实例
    vector_index = get_vector_index()
    
    success_count = 0
    error_count = 0
    errors = []
    
    for i, filename in enumerate(structure_files, 1):
        filepath = os.path.join(RESULTS_DIR, filename)
        print(f"[{i}/{len(structure_files)}] 正在处理: {filename}")
        
        try:
            # 读取结构文件
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 提取文档信息
            doc_name = data.get("doc_name", filename.replace("_structure.json", ""))
            doc_description = data.get("doc_description", "")
            structure = data.get("structure", [])
            
            if not structure:
                print(f"  ⚠️ 跳过: 结构为空")
                continue
            
            # 构建向量索引
            node_count = vector_index.add_document(doc_name, structure, doc_description)
            print(f"  ✅ 成功: 添加了 {node_count} 个节点")
            success_count += 1
            
            # 文档之间添加延迟，避免连接池问题
            if i < len(structure_files):
                time.sleep(doc_delay)
            
        except Exception as e:
            print(f"  ❌ 失败: {str(e)}")
            errors.append(f"{filename}: {str(e)}")
            error_count += 1
    
    # 打印统计信息
    print("\n" + "=" * 50)
    print("构建完成!")
    print(f"成功: {success_count} 个文档")
    print(f"失败: {error_count} 个文档")
    
    if errors:
        print("\n失败详情:")
        for error in errors:
            print(f"  - {error}")
    
    # 显示索引统计
    stats = vector_index.get_stats()
    print(f"\n向量索引统计:")
    print(f"  总节点数: {stats['total_nodes']}")
    print(f"  总文档数: {stats['total_documents']}")


if __name__ == "__main__":
    build_all_indexes()
