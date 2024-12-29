# bilibili自动切片工具

## 简介
一个基于[Bilibili API](https://github.com/nemo2011/bilibili-api)的自动切片工具，可以自动下载B站视频并按需求切片。

**注意：本项目使用 Python 3.11**

## 使用方法

### 安装依赖
```
pip install asyncio aiohttp bilibili-api-python os ffmpy subprocess dotenv
```

### 配置
在项目根目录下创建`.env`文件，按照[获取 Credential 类所需信息](https://nemo2011.github.io/bilibili-api/#/get-credential?id=%e8%8e%b7%e5%8f%96-credential-%e7%b1%bb%e6%89%80%e9%9c%80%e4%bf%a1%e6%81%af)获取`SESSDATA`, `BILI_JCT`, `BUVID3`并填入`.env`文件中。格式为
```
SESSDATA="..."
BILI_JCT="..."
BUVID3="..."
```

### 运行
```
python main.py
```
