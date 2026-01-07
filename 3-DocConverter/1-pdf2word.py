import os
from pdf2docx import Converter

def pdf_to_word(pdf_file_path, word_file_path):
    """
    将 PDF 文件转换为 Word (docx) 文件
    :param pdf_file_path: PDF 文件的路径
    :param word_file_path: 输出 Word 文件的路径
    """
    
    # 1. 检查 PDF 文件是否存在
    if not os.path.exists(pdf_file_path):
        print(f"错误：找不到文件 {pdf_file_path}")
        return

    try:
        print(f"正在开始转换: {pdf_file_path} ...")
        
        # 2. 加载 PDF
        cv = Converter(pdf_file_path)
        
        # 3. 执行转换
        # start=0, end=None 表示转换所有页面
        cv.convert(word_file_path, start=0, end=None)
        
        # 4. 关闭转换器释放资源
        cv.close()
        
        print(f"✅ 转换成功！文件已保存为: {word_file_path}")
        
    except Exception as e:
        print(f"❌ 转换过程中发生错误: {e}")

# --- 使用示例 ---
if __name__ == "__main__":
    # 请在这里修改你的文件名
    input_pdf = '3-DocConverter/1-template.pdf'   # 你的 PDF 文件名
    output_word = '3-DocConverter/1-template.docx' # 你想保存的 Word 文件名
    
    pdf_to_word(input_pdf, output_word)