"""
测试导入是否正常
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("测试导入 pydantic_settings...")
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    print("✓ pydantic_settings 导入成功")
except Exception as e:
    print(f"✗ pydantic_settings 导入失败: {e}")

print("\n测试导入 core.config...")
try:
    from core.config import settings
    print("✓ core.config 导入成功")
except Exception as e:
    print(f"✗ core.config 导入失败: {e}")

print("\n测试导入 workflow.graph...")
try:
    from workflow.graph import execute_workflow, app as langgraph_app
    print("✓ workflow.graph 导入成功")
except Exception as e:
    print(f"✗ workflow.graph 导入失败: {e}")
    import traceback
    traceback.print_exc()

print("\n所有测试完成！")
