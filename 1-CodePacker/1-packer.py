import os
import json
import argparse
import fnmatch

# ================= 配置与常量 =================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, '1-config.json')

EXT_TO_LANG = {
    '.py': 'python', '.js': 'javascript', '.ts': 'typescript', 
    '.vue': 'html', '.html': 'html', '.css': 'css', 
    '.java': 'java', '.c': 'c', '.cpp': 'cpp', '.go': 'go', 
    '.rs': 'rust', '.json': 'json', '.md': 'markdown', 
    '.sql': 'sql', '.sh': 'bash', '.yaml': 'yaml'
}

# ================= 核心类 =================

class ContextPacker:
    def __init__(self, task_name='default'):
        self.config = self.load_config()
        self.task_name = task_name
        self.task_config = self.get_task_config(task_name)
        
        # 优先级: 任务配置 > 全局配置 > 默认值 "../"
        raw_root = self.task_config.get('project_root', 
                                        self.config.get('project_root', '../'))
        
        self.project_root = os.path.abspath(os.path.join(SCRIPT_DIR, raw_root))
        
        print(f"📂 任务 [{task_name}] 根目录定位为: {self.project_root}")

        self.ignore_patterns = self.config.get('global_ignore', []) + \
                               self.task_config.get('ignore', [])
        
        self.target_extensions = set(self.task_config.get('extensions', []))
        
        # collected_files: 符合后缀要求，将读取内容的文件
        self.collected_files = [] 
        # structure_files: 所有未被忽略的文件，将用于生成目录树
        self.structure_files = [] 

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            print(f"❌ 错误: 找不到配置文件 {CONFIG_FILE}")
            exit(1)
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ 错误: 配置文件格式不正确 - {e}")
            exit(1)

    def get_task_config(self, task_name):
        tasks = self.config.get('tasks', {})
        if task_name not in tasks:
            print(f"❌ 错误: 任务 '{task_name}' 未在配置文件中定义。")
            print(f"可用任务: {', '.join(tasks.keys())}")
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
        
        # ==========================================
        # 修改处：如果 paths 为空列表，则扫描根目录 (".")
        # ==========================================
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
                    # 加入结构列表
                    structure_file_set.add(rel_path)
                    
                    # 检查后缀，加入内容列表
                    _, ext = os.path.splitext(rel_path)
                    if ext in self.target_extensions:
                        content_file_set.add(rel_path)
            
            elif os.path.isdir(full_path):
                for root, dirs, files in os.walk(full_path):
                    rel_root = os.path.relpath(root, self.project_root)
                    dirs[:] = [d for d in dirs if not self.is_ignored(os.path.join(rel_root, d))]
                    
                    for file in files:
                        abs_file_path = os.path.join(root, file)
                        rel_file_path = os.path.relpath(abs_file_path, self.project_root)
                        
                        if self.is_ignored(rel_file_path):
                            continue
                        
                        # 1. 只要不忽略，就加入结构树
                        structure_file_set.add(rel_file_path)
                        
                        # 2. 只有符合后缀，才加入内容列表
                        _, ext = os.path.splitext(file)
                        if ext in self.target_extensions:
                            content_file_set.add(rel_file_path)

        self.collected_files = sorted(list(content_file_set))
        self.structure_files = sorted(list(structure_file_set))
        
        print(f"✅ 找到 {len(self.collected_files)} 个符合内容读取条件的文件：")
        print("-" * 40)
        for idx, f in enumerate(self.collected_files, 1):
            print(f"   {idx}. {f}")
        print("-" * 40)
        
        print(f"📊 统计：")
        print(f"   - 目录树包含文件总数: {len(self.structure_files)} (包含未被读取的文件)")
        print(f"   - 实际打包内容文件数: {len(self.collected_files)}")

    def generate_tree_structure(self):
        tree = {}
        # 使用 structure_files 生成完整的目录树
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
        filename = self.task_config.get('output_file', 
                                        self.config.get('output_file', 'context_bundle.md'))
        
        output_file = os.path.join(SCRIPT_DIR, filename)
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"# Project Context Bundle\n")
                f.write(f"> Task: {self.task_name} | Root: {self.task_config.get('project_root', 'Global')}\n\n")
                
                f.write("## 1. Project Structure\n")
                f.write("Files included (All non-ignored files):\n\n")
                f.write("```text\n")
                f.write(self.generate_tree_structure())
                f.write("\n```\n\n")
                
                f.write("## 2. File Contents\n\n")
                
                # 仅写入符合后缀要求的文件内容
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

            print(f"🎉 成功生成文件: {output_file}")

        except Exception as e:
            print(f"❌ 写入失败: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='打包代码上下文')
    parser.add_argument('task', nargs='?', default='default', help='任务名称')
    args = parser.parse_args()
    
    packer = ContextPacker(task_name=args.task)
    packer.scan_files()
    packer.generate_markdown()