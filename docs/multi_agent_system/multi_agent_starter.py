"""
多智能体协作系统 - 系统快速启动脚本
"""

import asyncio
import sys
from pathlib import Path
from typing import List, Optional

# 添加项目路径到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from docs.multi_agent_system.multi_agent_integration import (
    MultiAgentSystem, example_basic_usage, 
    example_direct_agent_call, example_parallel_workflow
)


async def run_system_demo():
    """运行系统演示"""
    print("🤖 多智能体协作系统演示")
    print("=" * 50)
    
    # 获取项目根目录
    project_root = Path.cwd()
    
    # 创建并初始化系统
    system = MultiAgentSystem(project_root)
    
    try:
        print("\n📡 初始化系统...")
        await system.initialize()
        
        print("\n✅ 系统启动成功！")
        print("\n📊 当前智能体状态:")
        system.print_system_status()
        
        # 执行示例工作流
        print("\n🔄 执行代码变更工作流示例...")
        result = await system.execute_workflow(
            workflow_type="code_change_workflow",
            changed_files=["src/main.py", "tests/test_main.py"]
        )
        
        print("\n📈 工作流执行结果:")
        print(f"状态: {result.get('state', 'unknown')}")
        
        if 'result' in result:
            workflow_result = result['result']
            print(f"完成的步骤: {len(workflow_result.get('results', {}))}")
            print(f"错误数量: {len(workflow_result.get('errors', []))}")
        
        print("\n📊 最终系统状态:")
        system.print_system_status()
        
    except Exception as e:
        print(f"\n❌ 系统运行出错: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        print("\n🛑 关闭系统...")
        await system.shutdown()
        print("✅ 系统已安全关闭")


async def run_direct_agent_demo():
    """运行直接调用智能体演示"""
    print("🤖 直接调用智能体演示")
    print("=" * 50)
    
    project_root = Path.cwd()
    system = MultiAgentSystem(project_root)
    
    try:
        await system.initialize()
        await example_direct_agent_call()
        
    finally:
        await system.shutdown()


async def run_parallel_demo():
    """运行并行工作流演示"""
    print("🤖 并行工作流演示")
    print("=" * 50)
    
    project_root = Path.cwd()
    system = MultiAgentSystem(project_root)
    
    try:
        await system.initialize()
        await example_parallel_workflow()
        
    finally:
        await system.shutdown()


def print_usage():
    """打印使用说明"""
    print("""
多智能体协作系统 - 快速启动脚本

使用方法:
  python multi_agent_starter.py [命令]

可用命令:
  demo              运行系统演示 (默认)
  direct            直接调用智能体演示
  parallel          并行工作流演示
  status            查看系统状态
  help              显示此帮助信息

示例:
  python multi_agent_starter.py demo
  python multi_agent_starter.py direct
  python multi_agent_starter.py parallel
""")


async def check_system_status():
    """检查系统状态"""
    print("🔍 系统状态检查")
    print("=" * 50)
    
    project_root = Path.cwd()
    
    # 检查项目结构
    print(f"项目根目录: {project_root}")
    print(f"存在 docs/multi_agent_system/: {(project_root / 'docs/multi_agent_system').exists()}")
    
    # 检查 Entrix 配置
    harness_path = project_root / "harness.yaml"
    print(f"存在 harness.yaml: {harness_path.exists()}")
    
    if harness_path.exists():
        print("Harness 配置已就绪")


def main():
    """主函数"""
    # 解析命令行参数
    command = sys.argv[1] if len(sys.argv) > 1 else "demo"
    
    try:
        if command == "demo":
            asyncio.run(run_system_demo())
        elif command == "direct":
            asyncio.run(run_direct_agent_demo())
        elif command == "parallel":
            asyncio.run(run_parallel_demo())
        elif command == "status":
            asyncio.run(check_system_status())
        elif command == "help":
            print_usage()
        else:
            print(f"❌ 未知命令: {command}")
            print_usage()
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断，系统正在关闭...")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
