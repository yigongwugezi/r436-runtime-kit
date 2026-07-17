
# 讯飞智文PPT生成服务MCP Server

## 概述

讯飞智文PPT生成服务MCP Server是基于讯飞星火大模型搭建的智能文档AI助理，全面兼容[MCP协议](https://modelcontextprotocol.io/)，支持通过MCP协议快速接入各类智能体助手（如`Claude`、`Cursor`以及`千帆AppBuilder`等）。

本服务提供6个符合MCP协议标准的API接口，涵盖PPT模板获取、PPT生成任务创建、任务进度查询、大纲生成等核心功能，帮助用户高效生成PPT文档，提升工作与学习效率。

依赖`MCP Python SDK`开发，支持通过环境变量配置服务认证信息，确保安全可靠的API调用。


## 工具

### 1. 获取PPT模板列表 `get_theme_list`
- **描述**：获取可用的PPT模板列表，支持通过风格、颜色、行业等条件筛选模板，需先设置环境变量 `AIPPT_APP_ID` 和 `AIPPT_API_SECRET`。
- **参数**：
  - `pay_type`：模板付费类型（可选值：`free`-免费模板，`not_free`-付费模板，默认值：`not_free`）
  - `style`：模板风格（如：简约、商务、科技等，可选）
  - `color`：模板颜色（如：红色、蓝色等，可选）
  - `industry`：模板行业（如：教育培训、金融等，可选）
  - `page_num`：页码（从1开始，默认值：2）
  - `page_size`：每页数量（最大100，默认值：10）
- **输出**：包含模板列表的字典，每个模板包含 `template_id`、`name`、`style` 等信息。


### 2. 创建PPT生成任务 `create_ppt_task`
- **描述**：根据文本内容和模板ID创建PPT生成任务，需先通过 `get_theme_list` 获取有效的 `template_id`，返回任务ID（`sid`）用于查询进度。
- **参数**：
  - `text`：PPT生成的内容描述（必填）
  - `template_id`：PPT模板ID（必填，通过 `get_theme_list` 获取）
  - `author`：PPT作者名称（默认值：`XXXX`）
  - `is_card_note`：是否生成演讲备注（`True`/`False`，默认值：`True`）
  - `search`：是否联网搜索补充内容（`True`/`False`，默认值：`False`）
  - `is_figure`：是否自动配图（`True`/`False`，默认值：`True`）
  - `ai_image`：AI配图类型（仅在 `is_figure=True` 时生效，可选值：`normal`-普通配图，`advanced`-高级配图，默认值：`normal`）
- **输出**：成功时返回 `{"sid": "任务ID"}`，失败时抛出异常。


### 3. 查询PPT生成任务进度 `get_task_progress`
- **描述**：查询通过 `create_ppt_task` 或 `create_ppt_by_outline` 创建的任务进度，任务完成后返回PPT下载地址。
- **参数**：
  - `sid`：任务ID（必填，从任务创建工具返回中获取）
- **输出**：包含任务状态（`status`）和PPT下载地址（`download_url`）的字典。


### 4. 创建PPT大纲 `create_outline`
- **描述**：根据文本内容生成PPT大纲，支持联网搜索补充内容，生成的大纲可用于 `create_ppt_by_outline`。
- **参数**：
  - `text`：需要生成大纲的内容描述（必填）
  - `language`：大纲生成语言（目前仅支持 `cn`-中文，默认值：`cn`）
  - `search`：是否联网搜索（`True`/`False`，默认值：`False`）
- **输出**：包含大纲内容的字典，格式为 `{"data": {"outline": 大纲内容}}`。


### 5. 从文档创建PPT大纲 `create_outline_by_doc`
- **描述**：根据文档内容生成PPT大纲，支持通过URL或本地路径上传文档（格式：pdf、doc、docx、txt、md，大小≤10M，字数≤8000字）。
- **参数**：
  - `file_name`：文档文件名（必填，需包含后缀名）
  - `file_url`：文档URL地址（与 `file_path` 二选一必填）
  - `file_path`：文档本地路径（与 `file_url` 二选一必填）
  - `text`：补充文本内容（指导大纲生成，必填）
  - `language`：大纲生成语言（目前仅支持 `cn`-中文，默认值：`cn`）
  - `search`：是否联网搜索（`True`/`False`，默认值：`False`）
- **输出**：包含大纲内容的字典，格式同 `create_outline`。


### 6. 根据大纲创建PPT `create_ppt_by_outline`
- **描述**：根据已生成的大纲和模板ID创建PPT，需通过 `create_outline` 或 `create_outline_by_doc` 获取大纲，通过 `get_theme_list` 获取模板ID。
- **参数**：
  - `text`：PPT生成内容描述（必填）
  - `outline`：大纲内容（必填，需提取 `create_outline` 返回的 `['data']['outline']` 字段）
  - `template_id`：PPT模板ID（必填，通过 `get_theme_list` 获取）
  - `author`：PPT作者名称（默认值：`XXXX`）
  - `is_card_note`：是否生成演讲备注（`True`/`False`，默认值：`True`）
  - `search`：是否联网搜索补充内容（`True`/`False`，默认值：`False`）
  - `is_figure`：是否自动配图（`True`/`False`，默认值：`True`）
  - `ai_image`：AI配图类型（仅在 `is_figure=True` 时生效，默认值：`normal`）
- **输出**：成功时返回 `{"sid": "任务ID"}`，失败时抛出异常。


## 开始

### 获取认证信息
在[讯飞开放平台](https://www.xfyun.cn/)申请应用，获取 `AIPPT_APP_ID` 和 `AIPPT_API_SECRET`，并设置为环境变量：
```bash
export AIPPT_APP_ID="你的应用ID"
export AIPPT_API_SECRET="你的API密钥"
```


### Python接入

#### 推荐方式：使用uvx一键启动（极简接入）
`uvx` 是一款轻量级工具，支持快速运行MCP服务，无需额外安装依赖。若已安装`uvx`，可直接通过以下步骤启动服务：

##### 安装uvx（首次使用需安装）
```bash
# 按官方文档安装uv（支持macOS/Linux/Windows）
curl -fsSL https://install.astral.sh/uv | bash
```

##### 启动服务
```bash
uvx zwppt-mcp
```
该命令会自动拉取并运行讯飞智文PPT生成服务MCP Server，无需手动管理依赖或代码。



### MCP客户端配置
在MCP客户端（如Claude.app）中添加服务配置

#### 使用uvx启动的配置（推荐）
```json
{
  "mcpServers": {
    "zwppt-mcp": {
      "command": "uvx",
      "args": ["zwppt-mcp"],
      "env": {
        "AIPPT_APP_ID": "<你的应用ID>",
        "AIPPT_API_SECRET": "<你的API密钥>"
      }
    }
  }
}
```


## 说明
1. **参数规格**：
   - `template_id` 需通过 `get_theme_list` 工具获取，确保为有效模板ID。
   - `sid` 任务ID需从任务创建工具（`create_ppt_task`/`create_ppt_by_outline`）的返回中获取。
   - 文档上传时，`file_url` 与 `file_path` 需二选一，且文件名需包含正确后缀（如 `.pdf`/`.docx`）。

2. **任务流程**：
   - 生成PPT需先获取模板ID（`get_theme_list`），再创建任务（`create_ppt_task`/`create_ppt_by_outline`），通过 `get_task_progress` 轮询进度，任务完成后获取下载地址。



## 反馈
使用中遇到问题，欢迎通过`issue`或[讯飞开放平台客服](https://www.xfyun.cn/support)反馈。我们鼓励提交`PR`贡献代码，感谢您的支持！

