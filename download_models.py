import ssl
import os
import urllib.request
import easyocr

# 完全禁用SSL证书验证
ssl._create_default_https_context = ssl._create_unverified_context

# 创建SSL不验证上下文
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# 替换默认opener
opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
urllib.request.install_opener(opener)

# 确保模型目录存在
os.makedirs(os.path.expanduser("~/.EasyOCR/model"), exist_ok=True)

# 先创建reader加载模型
print("开始下载EasyOCR模型...")
reader = easyocr.Reader(['en'])
print("模型下载完成！") 