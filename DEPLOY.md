# GitHub Pages 部署指南

## 自动部署脚本

我们提供了一个自动部署脚本 `deploy.sh`，可以帮您快速完成部署。

### 使用方法

1. 确保您有 GitHub 账号
2. 在终端中运行以下命令：

```bash
cd /workspace/巴菲特分享版/
bash deploy.sh
```

3. 按照提示登录 GitHub（首次使用需要）
4. 脚本会自动创建仓库、推送代码并启用 GitHub Pages

## 手动部署步骤

如果您更喜欢手动操作，请按以下步骤进行：

### 1. 登录 GitHub CLI

```bash
gh auth login
```

按照提示选择：
- What account do you want to log into? **GitHub.com**
- What is your preferred protocol for Git operations on this host? **HTTPS**
- Authenticate Git with your GitHub credentials? **Yes**
- How would you like to authenticate GitHub CLI? **Login with a web browser**

复制显示的验证码，按 Enter 打开浏览器，粘贴验证码完成授权。

### 2. 创建 GitHub 仓库

```bash
gh repo create buffett-letters --public --source=. --remote=origin --push
```

或者使用其他仓库名称：

```bash
gh repo create 您的仓库名 --public --source=. --remote=origin --push
```

### 3. 启用 GitHub Pages

```bash
gh api repos/{用户名}/buffett-letters/pages \
  --method POST \
  --input - <<< '{"source":{"branch":"main","path":"/"}}'
```

将 `{用户名}` 替换为您的 GitHub 用户名。

### 4. 获取 GitHub Pages URL

```bash
gh api repos/{用户名}/buffett-letters/pages | grep html_url
```

或者直接在浏览器中访问：

```
https://{用户名}.github.io/buffett-letters/
```

## 通过 GitHub 网站手动启用 Pages

如果您不想使用 CLI 命令启用 Pages：

1. 打开浏览器，访问 `https://github.com/{用户名}/buffett-letters`
2. 点击 **Settings** 标签
3. 左侧菜单选择 **Pages**
4. 在 "Build and deployment" 部分：
   - Source: 选择 **Deploy from a branch**
   - Branch: 选择 **main**，文件夹选择 **/(root)**
5. 点击 **Save**
6. 等待几分钟，页面会显示您的网站 URL

## 网站地址

部署完成后，您的网站将通过以下地址访问：

```
https://{您的GitHub用户名}.github.io/buffett-letters/
```

## 更新网站

当您修改文件后，重新部署：

```bash
git add .
git commit -m "更新内容"
git push origin main
```

GitHub Pages 会自动重新构建和部署（通常需要 1-2 分钟）。
