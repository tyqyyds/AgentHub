"""
简单测试版本 - 用于验证 Streamlit 是否正常工作
"""
import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.title("测试页面")
st.write("如果你能看到这个页面，说明 Streamlit 正常工作！")
st.write("当前目录：", os.getcwd())
st.write("Python 版本：", sys.version)

st.sidebar.title("侧边栏")
st.sidebar.write("侧边栏内容")

st.button("测试按钮")
