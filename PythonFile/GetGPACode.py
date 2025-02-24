from datetime import datetime, timedelta
import os
import sys
import re
import json
import unicodedata
import requests
from bs4 import BeautifulSoup
import ssl
from datetime import datetime, timedelta
from urllib.parse import urlparse
from urllib3.poolmanager import PoolManager
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
import chardet
from collections import defaultdict
import getpass



# 检查重定向的URL是否有问题
def is_authentication_endpoint(redirect_url):
    try:
        parsed_url = urlparse(redirect_url)
        path_segments = parsed_url.path.strip('/').split('/')
        if path_segments and path_segments[0] == 'authenticationendpoint':
            return True
        return False
    except Exception as e:
        print(f"Error parsing URL: {e}")
        return False


# 计算修读完所有课程想要达到的GPA所需要剩余课程的平均GPA
def calculate_required_gpa(current_gpa, completed_credits, remaining_credits, target_gpa):
    if remaining_credits == 0:
        return "N/A"
    required_gpa = (target_gpa * (completed_credits + remaining_credits) - current_gpa * completed_credits) / remaining_credits
    return required_gpa if 0 <= required_gpa <= 4.0 else "不可达到"


# 期末成绩计算GPA
def calculate_gpa(score):
    if 93 <= score <= 100:
        return 4.0
    elif 88 <= score <= 92:
        return 3.7
    elif 83 <= score <= 87:
        return 3.3
    elif 78 <= score <= 82:
        return 3.0
    elif 73 <= score <= 77:
        return 2.7
    elif 68 <= score <= 72:
        return 2.3
    elif 63 <= score <= 67:
        return 2.0
    elif 58 <= score <= 62:
        return 1.7
    elif 53 <= score <= 57:
        return 1.3
    elif 50 <= score <= 52:
        return 1.0
    else:
        return 0.0


def get_display_width(s):
    width = 0
    for char in s:
        if unicodedata.east_asian_width(char) in ('F', 'W', 'A'):  # 全宽字符
            width += 2
        else:  # 半宽字符
            width += 1
    return width


# 填充字符串到指定宽度
def pad_string(s, width):
    current_width = get_display_width(s)
    padding = width - current_width
    return s + ' ' * padding

# 自定义适配器，允许不安全的 SSL 重协商
class UnsafeSSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context()
        context.options |= ssl.OP_LEGACY_SERVER_CONNECT  # 允许不安全的 SSL 重协商
        context.set_ciphers('DEFAULT:@SECLEVEL=0')  # 降低安全级别
        kwargs['ssl_context'] = context
        return super(UnsafeSSLAdapter, self).init_poolmanager(*args, **kwargs)

# 登录页面和重定向页面的 URL
login_url = "https://banner-prod-xe-01.ipm.edu.mo:8446/BannerExtensibility/customPage/page/StudentHomePage"
base_url = "https://account.ipm.edu.mo/commonauth"


# 创建会话并使用自定义的 SSL 适配器
session = requests.Session()
session.mount('https://', UnsafeSSLAdapter())
from colorama import Fore, Back, Style


# 发送 GET 请求，获取登录页面内容
print(Style.BRIGHT + Fore.CYAN + "\n" + "=" * 40)
print(Fore.GREEN + "MPU GPA Tool")
print(Fore.MAGENTA + "你输入的所有信息不会以任何形式传输到第三方平台，仅限用于向学校官网请求课表")
print("=" * 40 + "\n" + Style.RESET_ALL)


print(Style.BRIGHT + Fore.CYAN + """
╔════════════════════════════════╗
║        选择理工  迈向成功      ║
╚════════════════════════════════╝
""" + Style.RESET_ALL)

try:
    response = session.get(login_url, timeout=30)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        
        session_data_key = soup.find('input', {'name': 'sessionDataKey'})['value']

        # 用户信息
        print(Fore.CYAN + "\n请输入以下登录信息:")
        username = input(Fore.YELLOW + "学生账号: ")
        password = getpass.getpass(Fore.YELLOW + "学生账号密码 (输入时不会显示): ")
        print(Fore.GREEN + "密码输入完成！")

        login_payload = {
            'usernameUserInput': username,
            'username': f"{username}@carbon.super",
            'password': password,
            'sessionDataKey': session_data_key,
        }

        response = session.post(base_url, data=login_payload, allow_redirects=False)

        # 检查是否发生重定向 (302 Found)
        if response.status_code == 302:
            # 获取重定向的 URL（CAS 登录页面）
            redirect_url = response.headers['Location']
            print(Fore.CYAN + f"重定向到: {redirect_url}")
            if is_authentication_endpoint(redirect_url):
                print(Style.BRIGHT + Fore.RED + "account.ipm.edu.mo:Login failed! Please recheck the username and password and try again.!!!\n账号或密码错误，请重新运行该文件!!!" + Style.RESET_ALL)
                input("\n按下 Enter 键退出程序...")
                sys.exit()


            # 第二步：发送 GET 请求，访问重定向 URL
            response = session.get(redirect_url, allow_redirects=False)

            # 如果成功重定向到 CAS 登录页面，继续进行登录操作
            if response.status_code == 302:
                # 获取新的 sessionDataKey
                new_session_data_key = response.headers['Location'].split('sessionDataKey=')[-1]
                print(Fore.CYAN + f"新 Session Key: {new_session_data_key}")

        
            # 访问指定页面（time_stud.asp）
            next_page_url = f"https://wapps2.ipm.edu.mo/siweb_cas/siweb.asp?bookmark=grade.asp"
            next_response = session.get(next_page_url, timeout=30)
            next_page_url = f"https://wapps2.ipm.edu.mo/siweb_cas/grade.asp"
            time_data = {
                "sel_year": "ALL",
            }
            next_response = session.get(next_page_url, data=time_data, timeout=30)

            if next_response.status_code == 200:
                print(Fore.WHITE + "成功获取成绩数据！正在整理成績...")
                
                detected_encoding = chardet.detect(next_response.content)['encoding']

                next_response.encoding = detected_encoding
                soup = BeautifulSoup(next_response.text, 'html.parser')
                rows = soup.select('table#result_table tr')
                grades = {}

                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) > 9:  # 确保这一行是数据行
                        year = cols[0].text.strip()
                        if year == "Year":
                            continue  # 跳过表头行

                        sem = cols[1].text.strip()
                        code = cols[2].text.strip()
                        section_code = cols[3].text.strip()
                        learning_module = cols[4].text.strip()

                        # 拆分课程中英文名称
                        if '\n' in learning_module:
                            english_name, chinese_name = learning_module.split('\n', 1)
                        else:
                            english_name = learning_module
                            chinese_name = ""

                        # 获取最终成绩并计算GPA
                        final_grade = cols[8].text.strip()
                        final_grade_numeric = int(re.sub(r'\D', '', final_grade)) if re.sub(r'\D', '', final_grade) else 0
                        gpa = calculate_gpa(final_grade_numeric)

                        # 如果 code 已经存在，则只保存最高分
                        if code in grades:
                            if final_grade_numeric > grades[code]['final_grade_numeric']:
                                grades[code] = {
                                    'year': year,
                                    'sem': sem,
                                    'code': code,
                                    'section_code': section_code,
                                    'english_name': english_name.strip(),
                                    'chinese_name': chinese_name.strip(),
                                    'final_grade_numeric': final_grade_numeric,
                                    'gpa': gpa
                                }
                        else:
                            grades[code] = {
                                'year': year,
                                'sem': sem,
                                'code': code,
                                'section_code': section_code,
                                'english_name': english_name.strip(),
                                'chinese_name': chinese_name.strip(),
                                'final_grade_numeric': final_grade_numeric,
                                'gpa': gpa
                            }

                col_widths = {
                    'Year': 6,
                    'Sem': 3,
                    'Code': 10,
                    'Section Code': 13,
                    'English Name': 40,
                    'Chinese Name': 25,
                    'Final Grade': 11,
                    'GPA': 3,
                }

                header = f"{'Year':<6} | {'Sem':<3} | {'Code':<10} | {'Section Code':<13} | {'English Name':<40} | {'Chinese Name':<25} | {'Final Grade':<11} | {'GPA':<3} | {'Credit':<1}"
                print(header)
                print("-" * get_display_width(header))

                zy_code = input("请输入你的专业代号：")


                with open(f"json/{zy_code}.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
                    courses = data["courses"]
                credit = 0
                user_credit = 0
                weighted_gpa_sum = 0 
                for entry in grades.values():
                    year = pad_string(entry['year'], col_widths['Year'])
                    sem = pad_string(entry['sem'], col_widths['Sem'])
                    code = pad_string(entry['code'], col_widths['Code'])
                    section_code = pad_string(entry['section_code'], col_widths['Section Code'])
                    english_name = pad_string(entry['english_name'], col_widths['English Name'])
                    chinese_name = pad_string(entry['chinese_name'], col_widths['Chinese Name'])
                    final_grade = pad_string(str(entry['final_grade_numeric']), col_widths['Final Grade'])
                    if final_grade.strip() == "0":
                        break
                    gpa = pad_string(f"{entry['gpa']:.1f}", col_widths['GPA'])
                    for course in courses:
                        list_code = course["code"]
                        if list_code.strip() == code.strip():
                            credit = course['credit']
                            user_credit+=credit
                            weighted_gpa_sum +=  float(gpa.strip()) * int(credit)
                            break
 
                    print(f"{year} | {sem} | {code} | {section_code} | {english_name} | {chinese_name} | {final_grade} | {gpa} | {credit} ")

                all_credit = data["totalCredits"]
                need_credit = all_credit - user_credit

                # 计算当前 GPA
                current_gpa = weighted_gpa_sum / user_credit if user_credit > 0 else 0

                # 计算达到目标 GPA 所需的 GPA
                targets = [2.5, 2.6, 2.7, 2.8, 2.9, 3.0, 3.1, 3.2, 3.3, 3.4 , 3.5, 3.6, 3.7, 3.8, 3.9]
                required_gpas = {target: calculate_required_gpa(current_gpa, user_credit, need_credit, target) for target in targets}

                print("专业代号:", data["majorCode"])
                print("专业名称:", data["majorName"])
                print("总学分:", all_credit)
                print("已修读学分:", user_credit)
                print("未修读学分:", need_credit)
                print(f"当前 GPA: {current_gpa:.2f}")

                for target, required_gpa in required_gpas.items():
                    print(f"修复完剩下的课程最终达到 {target} 所需 GPA: {required_gpa if isinstance(required_gpa, str) else f'{required_gpa:.2f}'}")

                

            else:
                print(Fore.RED + f"请求课表页面失败，状态码: {next_response.status_code}")
                input("\n按下 Enter 键退出程序...")

        else:
            print(Fore.RED + "登录失败，请检查用户名和密码！")
            input("\n按下 Enter 键退出程序...")

    else:
        print(Fore.RED + f"登录页面请求失败，状态码: {response.status_code}")
        input("\n按下 Enter 键退出程序...")


except requests.exceptions.SSLError as e:
    print(Fore.RED + "SSL 错误:" + str(e))
    print("请检查电脑是否有代理网络未关闭")
    input("\n按下 Enter 键退出程序...")

except requests.exceptions.RequestException as e:
    print(Fore.RED + "请求错误:" + str(e))
    input("\n按下 Enter 键退出程序...")

