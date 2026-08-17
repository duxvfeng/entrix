"""
多智能体协作系统架构设计
基于 Entrix 质量保障系统的智能体编排
"""

# 核心设计原则
PRINCIPLES = {
    "separation_of_concerns": "每个智能体专注于特定领域",
    "loose_coupling": "通过消息传递通信，避免直接依赖",
    "fault_tolerance": "单个智能体失败不影响整体系统",
    "scalability": "支持动态添加和移除智能体"
}

# 智能体角色定义
AGENT_ROLES = {
    "quality_gate_agent": {
        "name": "质量门禁智能体",
        "responsibility": "执行 Entrix 检查，评估代码质量",
        "capabilities": [
            "运行 entrix run --tier fast",
            "评估适应度函数",
            "生成质量报告"
        ],
        "input": "代码变更列表",
        "output": "质量评估结果"
    },
    
    "review_agent": {
        "name": "代码审查智能体",
        "responsibility": "深度代码审查和架构分析",
        "capabilities": [
            "运行 entrix review-trigger",
            "基于图的影响分析",
            "生成审查上下文"
        ],
        "input": "高风险变更",
        "output": "审查建议和风险评估"
    },
    
    "test_agent": {
        "name": "测试智能体",
        "responsibility": "测试半径分析和测试执行",
        "capabilities": [
            "运行 entrix graph test-radius",
            "执行相关测试",
            "生成测试覆盖报告"
        ],
        "input": "变更影响范围",
        "output": "测试结果和覆盖度"
    },
    
    "orchestrator_agent": {
        "name": "编排智能体",
        "responsibility": "协调各智能体工作流程",
        "capabilities": [
            "任务分解和分发",
            "结果聚合",
            "决策制定"
        ],
        "input": "用户请求",
        "output": "协调后的任务分配"
    },
    
    "documentation_agent": {
        "name": "文档智能体",
        "responsibility": "生成和维护技术文档",
        "capabilities": [
            "生成 fitness 规格",
            "更新 AGENTS.md",
            "创建架构文档"
        ],
        "input": "代码变更和质量报告",
        "output": "更新的文档"
    }
}

# 工作流程定义
WORKFLOWS = {
    "code_change_workflow": {
        "trigger": "代码变更提交",
        "steps": [
            "orchestrator_agent 接收变更",
            "quality_gate_agent 执行快速检查",
            "如通过，review_agent 进行深度审查",
            "test_agent 分析测试半径",
            "documentation_agent 更新文档"
        ],
        "decision_points": [
            "快速检查失败 -> 阻止变更",
            "高风险变更 -> 触发人工审查",
            "测试覆盖不足 -> 标记警告"
        ]
    },
    
    "quality_monitoring_workflow": {
        "trigger": "定期质量检查",
        "steps": [
            "orchestrator_agent 启动检查",
            "quality_gate_agent 执行完整检查",
            "review_agent 分析趋势",
            "生成质量报告"
        ]
    }
}

# 消息传递协议
MESSAGE_PROTOCOL = {
    "message_format": {
        "id": "unique_message_id",
        "from_agent": "sender_agent_name",
        "to_agent": "receiver_agent_name",
        "type": "request|response|notification",
        "timestamp": "ISO8601_timestamp",
        "payload": "message_content",
        "priority": "high|medium|low"
    },
    
    "message_types": {
        "quality_check_request": "质量检查请求",
        "review_request": "审查请求",
        "test_analysis_request": "测试分析请求",
        "documentation_update_request": "文档更新请求",
        "aggregation_request": "结果聚合请求"
    }
}

# 协作模式
COLLABORATION_PATTERNS = {
    "pipeline": "流水线模式 - 按顺序处理",
    "fan_out_fan_in": "并行处理模式 - 分发后聚合",
    "orchestration": "编排模式 - 中央协调",
    "choreography": "对等模式 - 事件驱动"
}

# 错误处理和恢复
ERROR_HANDLING = {
    "retry_strategy": "指数退避重试",
    "fallback_behavior": "降级处理",
    "circuit_breaker": "熔断保护",
    "dead_letter_queue": "失败消息队列"
}

# 监控和可观测性
OBSERVABILITY = {
    "metrics": [
        "agent_execution_time",
        "success_rate",
        "error_count",
        "message_queue_size"
    ],
    "logging": "结构化日志",
    "tracing": "分布式追踪",
    "alerting": "异常告警"
}