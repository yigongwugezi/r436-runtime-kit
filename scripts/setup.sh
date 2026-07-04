#!/bin/bash
# ── EduAgent 一键部署脚本 ──
set -e

echo "🎓 EduAgent 部署开始..."

# 1. 检查 .env
if [ ! -f .env ]; then
    echo "❌ 请先创建 .env 文件：cp .env.example .env 并填入讯飞 API Key"
    exit 1
fi

source .env

if [ -z "$SPARK_API_KEY" ]; then
    echo "❌ SPARK_API_KEY 未设置，请在 .env 中填入讯飞星火 API Key"
    exit 1
fi

# 2. Clone 外部项目（如不存在）
if [ ! -d external_agents/deeptutor/.git ]; then
    echo "📥 克隆 DeepTutor..."
    git clone --depth 1 https://github.com/HKUDS/DeepTutor.git external_agents/deeptutor
fi

if [ ! -d external_agents/openmaic/.git ]; then
    echo "📥 克隆 OpenMAIC..."
    git clone --depth 1 https://github.com/THU-MAIC/OpenMAIC.git external_agents/openmaic
fi

# 3. 创建运行时数据目录
mkdir -p runtime_data/user/settings

# 4. 启动
echo "🚀 启动所有服务..."
docker-compose up -d --build

echo ""
echo "✅ 部署完成！"
echo ""
echo "服务地址："
echo "  前端：      http://localhost:3000"
echo "  DeepTutor： http://localhost:8000"
echo "  Profiler：  http://localhost:8001"
echo "  Grading：   http://localhost:8002"
echo "  OpenMAIC：  http://localhost:8003"
echo ""
echo "上传知识库："
echo "  curl -X POST http://localhost:8000/api/rag/upload -F \"files=@knowledge_base/courses/ai_intro/chapters/*.md\""
