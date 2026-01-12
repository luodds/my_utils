import os
import fnmatch

# ==============================================================================
#                               👇 用户配置区域 👇
# ==============================================================================

# 1. 当前要运行的任务名称
CURRENT_TASK = "paper_chapter3-1" 

# 2. 统一输出文件夹名称 (所有生成的 markdown 都会放在这里，自动创建)
OUTPUT_DIR = "output"

# 3. 全局配置与任务配置
GLOBAL_CONFIG = {
  "global_ignore": [
    "node_modules", ".git", "__pycache__", ".DS_Store", "generated",
    "__init__.py", ".next", "baselines", ".venv", "dist", "build", "*.pyc"
  ],

  "tasks": {
    "default": {
      "description": "默认任务",
      "project_root": "../",
      "output_file": "context_default.md",
      "paths": ["backend-server/src/api"],
      "extensions": [".py"]
    },

    "paper_chapter3": {
      "description": "第三章论文代码",
      "project_root": "../../pythonCode/Icpn",
      "output_file": "chapter3_code.md",
      "paths": ["Chapter3_Static_FewShot", "utils/new_pcap_processor.py"],
      "extensions": [".py"]
    },

    "paper_chapter3-1": {
      "description": "第三章论文代码-1",
      "project_root": "../../pythonCode/Icpn",
      "output_file": "chapter3_1.md",
      "paths": ["Chapter3_Static_FewShot", "utils/preprocess_etbert_style.py"],
      "extensions": [".py"]
    },

    "paper_chapter3-2": {
      "description": "第三章论文代码-2",
      "project_root": "../../pythonCode/Icpn",
      "output_file": "chapter3_2.md",
      "paths": ["utils/preprocess_etbert_style.py"],
      "extensions": [".py"]
    },

    "paper_chapter3-3": {
      "description": "第三章论文代码-3",
      "project_root": "../../pythonCode/Icpn",
      "output_file": "chapter3_3.md",
      "paths": ["C3","utils/new_pcap_processor.py"],
      "extensions": [".py"]
    },

    "paper_chapter4-1": {
      "description": "第四章论文代码-1",
      "project_root": "../../pythonCode/Icpn",
      "output_file": "chapter4_1.md",
      "paths": ["Chapter4_Incremental",
                "utils/preprocess_etbert_style.py"],
      "extensions": [".py"]
    },

    "my-website": {
      "description": "我的网页项目",
      "project_root": "../../pythonCode/my-website",
      "output_file": "my-website.md",
      "paths": ["backend", "frontend"],
      "extensions": [".ts", ".tsx", ".css", ".py"]
    },

    "my-full-stack": {
      "description": "我的网页项目",
      "project_root": "../../pythonCode/my-full-stack",
      "output_file": "my-full-stack.md",
      "paths": [],
      "extensions": []
    },

    "MC-1DCNN-GTCN": {
      "description": "MC-1DCNN-GTCN",
      "project_root": "../../pythonCode/MC_1DCNN_GTCN",
      "output_file": "MC-1DCNN-GTCN.md",
      "paths": ["."],
      "extensions": [".py"]
    },

    "my_utils": {
      "description": "当前工具集项目",
      "project_root": "../",
      "output_file": "my_utils_context.md",
      "paths": ["."],
      "extensions": [".py"]
    }
  }
}

# ==============================================================================
#                               👆 配置结束 👆
# ==============================================================================

# ================= 常量定义 =================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

EXT_TO_LANG = {
    '.py': 'python', '.js': 'javascript', '.ts': 'typescript', 
    '.vue': 'html', '.html': 'html', '.css': 'css', 
    '.java': 'java', '.c': 'c', '.cpp': 'cpp', '.go': 'go', 
    '.rs': 'rust', '.json': 'json', '.md': 'markdown', 
    '.sql': 'sql', '.sh': 'bash', '.yaml': 'yaml', '.tsx': 'typescript'
}

# ================= 核心类 =================

class ContextPacker:
    def __init__(self, task_name):
        self.config = GLOBAL_CONFIG
        self.task_name = task_name
        self.task_config = self.get_task_config(task_name)
        self.output_dir_name = OUTPUT_DIR 
        
        # 优先级: 任务配置 > 全局配置 > 默认值 "../"
        raw_root = self.task_config.get('project_root', '../')
        self.project_root = os.path.abspath(os.path.join(SCRIPT_DIR, raw_root))
        
        print(f"📂 任务 [{task_name}] 根目录定位为: {self.project_root}")

        self.ignore_patterns = self.config.get('global_ignore', []) + \
                               self.task_config.get('ignore', [])
        
        self.target_extensions = set(self.task_config.get('extensions', []))
        
        self.collected_files = [] 
        self.structure_files = [] 

    def get_task_config(self, task_name):
        tasks = self.config.get('tasks', {})
        if task_name not in tasks:
            print(f"❌ 错误: 任务 '{task_name}' 未在配置中定义。")
            print(f"📋 可用任务: {', '.join(tasks.keys())}")
            exit(1)
        return tasks[task_name]

    def is_ignored(self, rel_path):
        name = os.path.basename(rel_path)
        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
            if fnmatch.fnmatch(rel_path, pattern):
                return True
        return False

    def scan_files(self):
        paths = self.task_config.get('paths', [])
        if not paths:
            print(f"👉 检测到 paths 配置为空，将扫描整个项目根目录...")
            paths = ["."]

        content_file_set = set()
        structure_file_set = set()

        print(f"🔍 正在扫描文件...")

        for p in paths:
            full_path = os.path.join(self.project_root, p)
            if not os.path.exists(full_path):
                print(f"⚠️  警告: 路径不存在: {p}")
                continue

            if os.path.isfile(full_path):
                rel_path = os.path.relpath(full_path, self.project_root)
                if not self.is_ignored(rel_path):
                    structure_file_set.add(rel_path)
                    _, ext = os.path.splitext(rel_path)
                    if ext in self.target_extensions:
                        content_file_set.add(rel_path)
            
            elif os.path.isdir(full_path):
                for root, dirs, files in os.walk(full_path):
                    rel_root = os.path.relpath(root, self.project_root)
                    
                    # 【新增修复逻辑 1】: 显式将当前遍历到的文件夹加入结构树
                    # 这样即使文件夹下没有文件，或者没有目标代码文件，目录结构也会保留
                    if rel_root != "." and not self.is_ignored(rel_root):
                        structure_file_set.add(rel_root)

                    # 过滤忽略的文件夹，防止递归进去
                    dirs[:] = [d for d in dirs if not self.is_ignored(os.path.join(rel_root, d))]
                    
                    for file in files:
                        abs_file_path = os.path.join(root, file)
                        rel_file_path = os.path.relpath(abs_file_path, self.project_root)
                        
                        if self.is_ignored(rel_file_path):
                            continue
                        
                        # 只要文件不被忽略，就加入结构树（不管是不是 .py 代码）
                        structure_file_set.add(rel_file_path)
                        
                        # 检查后缀，如果符合才加入内容列表
                        _, ext = os.path.splitext(file)
                        if ext in self.target_extensions:
                            content_file_set.add(rel_file_path)

        self.collected_files = sorted(list(content_file_set))
        self.structure_files = sorted(list(structure_file_set))
        
        # 【新增修复逻辑 2】: 恢复打印找到的文件列表
        print(f"✅ 找到 {len(self.collected_files)} 个符合内容读取条件的文件：")
        print("-" * 40)
        for idx, f in enumerate(self.collected_files, 1):
            print(f"   {idx}. {f}")
        print("-" * 40)
        
        print(f"📊 统计：")
        print(f"   - 目录树包含节点总数: {len(self.structure_files)} (包含目录和所有非忽略文件)")
        print(f"   - 实际打包内容文件数: {len(self.collected_files)}")

    def generate_tree_structure(self):
        tree = {}
        for path in self.structure_files:
            parts = path.split(os.sep)
            current = tree
            for part in parts:
                current = current.setdefault(part, {})
        
        lines = []
        def _build_tree_string(node, prefix=""):
            keys = sorted(node.keys())
            count = len(keys)
            for i, key in enumerate(keys):
                is_last = (i == count - 1)
                connector = "└── " if is_last else "├── "
                lines.append(f"{prefix}{connector}{key}")
                children = node[key]
                if children:
                    extension = "    " if is_last else "│   "
                    _build_tree_string(children, prefix + extension)

        lines.append(".") 
        _build_tree_string(tree)
        return "\n".join(lines)

    def generate_markdown(self):
        raw_filename = self.task_config.get('output_file', 'context_bundle.md')
        filename = os.path.basename(raw_filename)
        
        output_dir_path = os.path.join(SCRIPT_DIR, self.output_dir_name)
        final_output_path = os.path.join(output_dir_path, filename)

        if not os.path.exists(output_dir_path):
            os.makedirs(output_dir_path)
            print(f"📁 已创建输出目录: {output_dir_path}")
        
        try:
            with open(final_output_path, 'w', encoding='utf-8') as f:
                f.write(f"# Project Context Bundle\n")
                f.write(f"> Task: {self.task_name} | Root: {self.task_config.get('project_root', 'Global')}\n\n")
                
                f.write("## 1. Project Structure\n")
                f.write("Files included (All non-ignored files and directories):\n\n")
                f.write("```text\n")
                f.write(self.generate_tree_structure())
                f.write("\n```\n\n")
                
                f.write("## 2. File Contents\n\n")
                
                for rel_path in self.collected_files:
                    abs_path = os.path.join(self.project_root, rel_path)
                    f.write(f"### File: `{rel_path}`\n")
                    _, ext = os.path.splitext(rel_path)
                    lang = EXT_TO_LANG.get(ext, '')
                    
                    try:
                        with open(abs_path, 'r', encoding='utf-8') as src_file:
                            content = src_file.read()
                        f.write(f"```{lang}\n")
                        f.write(content)
                        if not content.endswith('\n'): f.write('\n')
                        f.write("```\n\n")
                    except Exception as e:
                        f.write(f"> ⚠️ Error reading file: {e}\n\n")

            print(f"🎉 成功生成文件: {final_output_path}")

        except Exception as e:
            print(f"❌ 写入失败: {e}")

if __name__ == "__main__":
    packer = ContextPacker(task_name=CURRENT_TASK)
    packer.scan_files()
    packer.generate_markdown()