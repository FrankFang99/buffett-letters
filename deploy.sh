#!/bin/bash

# GitHub Pages 自动部署脚本

set -e

echo "=========================================="
echo "  巴菲特致股东信 - GitHub Pages 部署脚本"
echo "=========================================="
echo ""

# 检查 gh 是否已登录
echo "[1/5] 检查 GitHub 登录状态..."
if ! gh auth status &>/dev/null; then
    echo "您尚未登录 GitHub CLI，请先登录："
    echo ""
    gh auth login
else
    echo "✓ 已登录 GitHub"
fi

# 获取当前登录的用户名
echo ""
echo "[2/5] 获取 GitHub 用户名..."
USERNAME=$(gh api user -q '.login')
echo "✓ GitHub 用户名: $USERNAME"

# 创建仓库
echo ""
echo "[3/5] 创建 GitHub 仓库..."
REPO_NAME="buffett-letters"

if gh repo view "$USERNAME/$REPO_NAME" &>/dev/null; then
    echo "✓ 仓库 $REPO_NAME 已存在"
else
    echo "创建新仓库: $REPO_NAME"
    gh repo create "$REPO_NAME" --public --source=. --remote=origin --push
    echo "✓ 仓库创建成功"
fi

# 推送代码
echo ""
echo "[4/5] 推送代码到 GitHub..."
if git remote get-url origin &>/dev/null; then
    git push -u origin main
else
    git remote add origin "https://github.com/$USERNAME/$REPO_NAME.git"
    git push -u origin main
fi
echo "✓ 代码推送成功"

# 启用 GitHub Pages
echo ""
echo "[5/5] 启用 GitHub Pages..."

# 检查是否已启用 Pages
if gh api "repos/$USERNAME/$REPO_NAME/pages" &>/dev/null; then
    echo "✓ GitHub Pages 已启用"
else
    echo "正在启用 GitHub Pages..."
    gh api "repos/$USERNAME/$REPO_NAME/pages" \
        --method POST \
        --input - <<< '{"source":{"branch":"main","path":"/"}}' \
        --silent 2>/dev/null || echo "注意: 请手动在 GitHub 网站启用 Pages"
fi

# 获取 Pages URL
echo ""
echo "=========================================="
echo "  部署完成！"
echo "=========================================="
echo ""
echo "您的网站地址是:"
echo "  https://$USERNAME.github.io/$REPO_NAME/"
echo ""
echo "注意：首次部署可能需要 1-2 分钟才能生效。"
echo ""
echo "如果 Pages 未自动启用，请手动操作："
echo "  1. 访问 https://github.com/$USERNAME/$REPO_NAME"
echo "  2. 点击 Settings -> Pages"
echo "  3. Source 选择 'Deploy from a branch'"
echo "  4. Branch 选择 'main'，路径选择 '/(root)'"
echo "  5. 点击 Save"
echo ""
