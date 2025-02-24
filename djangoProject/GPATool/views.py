import time
import json
import requests
import re
import chardet
import ssl
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
from django.shortcuts import render, redirect
from django.http import StreamingHttpResponse


# 自定义适配器，允许不安全的 SSL 重协商
class UnsafeSSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context()
        context.options |= ssl.OP_LEGACY_SERVER_CONNECT  # 允许不安全的 SSL 重协商
        context.set_ciphers('DEFAULT:@SECLEVEL=0')  # 降低安全级别
        kwargs['ssl_context'] = context
        return super(UnsafeSSLAdapter, self).init_poolmanager(*args, **kwargs)

def is_authentication_endpoint(redirect_url):
    """判断是否是认证失败的 URL"""
    try:
        parsed_url = urlparse(redirect_url)
        path_segments = parsed_url.path.strip('/').split('/')
        return path_segments and path_segments[0] == 'authenticationendpoint'
    except Exception as e:
        print(f"Error parsing URL: {e}")
        return False

def calculate_required_gpa(current_gpa, completed_credits, remaining_credits, target_gpa):
    if remaining_credits == 0:
        return "N/A"
    required_gpa = (target_gpa * (completed_credits + remaining_credits) - current_gpa * completed_credits) / remaining_credits
    return required_gpa if 0 <= required_gpa <= 4.0 else "不可达到"


def calculate_gpa(score):
    """根据成绩计算 GPA"""
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

def login_view(request):
    """渲染登录页面，存储用户输入的账号、密码和专业"""
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        major = request.POST.get("major")  # 获取用户选择的专业

        request.session["username"] = username
        request.session["password"] = password
        request.session["major"] = major  # 存储专业

        return redirect("fetch_gpa_page")  # 跳转到 GPA 计算页面

    return render(request, "login.html")  # 渲染登录页面

def fetch_gpa_page(request):
    """渲染 GPA 计算进度页面"""
    return render(request, "fetch_gpa.html")

def fetch_gpa_view(request):
    """实时获取 GPA 计算进度并返回前端"""
    username = request.session.get("username", "")
    password = request.session.get("password", "")
    major = request.session.get("major", "未选择")  # 获取专业


    def event_stream():
        session = requests.Session()
        session.mount('https://', UnsafeSSLAdapter())  # 使用不安全的 SSL 适配器

        login_url = "https://banner-prod-xe-01.ipm.edu.mo:8446/BannerExtensibility/customPage/page/StudentHomePage"
        base_url = "https://account.ipm.edu.mo/commonauth"

        try:
            with open(f"json/{major}.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                courses = data["courses"]



            yield "开始请求......"
            time.sleep(1)

            response = session.get(login_url, timeout=30)
            if response.status_code != 200:
                yield "❌ 失败: 登录页面请求失败!\n"
                return

            soup = BeautifulSoup(response.text, 'html.parser')
            session_data_key = soup.find('input', {'name': 'sessionDataKey'})['value']

            yield "✅ 正在提交用户信息...（1/4）\n"

            login_payload = {
                'usernameUserInput': username,
                'username': f"{username}@carbon.super",
                'password': password,
                'sessionDataKey': session_data_key,
            }

            response = session.post(base_url, data=login_payload, allow_redirects=False)
            if response.status_code != 302:
                yield "❌ 失败: 登录失败，请检查用户名和密码!\n"
                return

            redirect_url = response.headers['Location']

            if is_authentication_endpoint(redirect_url):
                yield "❌ 失败: 账号或密码错误!\n"
                return

            response = session.get(redirect_url, allow_redirects=False)
            if response.status_code != 302:
                yield "❌ 失败: 登录验证失败!\n"
                return

            yield "✅ 登录成功，正在获取 GPA 数据...（2/4）\n"
            time.sleep(1)

            next_page_url = f"https://wapps2.ipm.edu.mo/siweb_cas/siweb.asp?bookmark=grade.asp"
            next_response = session.get(next_page_url, timeout=30)
            next_page_url = f"https://wapps2.ipm.edu.mo/siweb_cas/grade.asp"
            time_data = {
                "sel_year": "ALL",
            }
            gpa_response = session.get(next_page_url, data=time_data, timeout=30)

            if gpa_response.status_code != 200:
                yield "❌ 失败: GPA 数据获取失败!\n"
                return

            yield "✅ 数据获取成功，正在计算...（3/4）\n"
            time.sleep(1)

            detected_encoding = chardet.detect(gpa_response.content)['encoding']
            gpa_response.encoding = detected_encoding
            soup = BeautifulSoup(gpa_response.text, 'html.parser')

            rows = soup.select('table#result_table tr')
            if not rows:
                yield "❌ 失败: GPA 解析失败!\n"
                return

            yield "✅ 正在解析 GPA 数据...（4/4）\n"

            final_grades_list = []  # 存储最终成绩的列表
            semester_gpa = []  # 存储每学期的 GPA 数据
            user_credit = 0
            weighted_gpa_sum = 0


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
                    if final_grade_numeric < 50:
                        continue
                    gpa = calculate_gpa(final_grade_numeric)
                    credit = 0

                    for course in courses:
                        if course["code"] == code:
                            credit = course['credit']
                            user_credit += credit
                            weighted_gpa_sum += float(gpa) * int(credit)
                            break

                    if credit == 0:

                        yield f"❌ 失败: 专业课程列表搜索失败 课程：{chinese_name}\n"
                        return

                        # 整合到列表
                    final_grades_list.append({
                        'year': year,
                        'sem': sem,
                        'code': code,
                        'section_code': section_code,
                        'english_name': english_name.strip(),
                        'chinese_name': chinese_name.strip(),
                        'final_grade_numeric': final_grade_numeric,
                        'gpa': gpa,
                        'credit': credit,
                    })

                    # 每个学期的 GPA 存入 semester_gpa 列表
                    semester_gpa.append({
                        'year': year,
                        'semester': sem,
                        'chinese_name': chinese_name,
                        'gpa': gpa
                    })

            for entry in final_grades_list:
                yield json.dumps(entry) + "\n"  # 逐条发送课程数据
                time.sleep(0.1)

            all_credit = data["totalCredits"]
            user_credit = sum(entry["credit"] for entry in final_grades_list)
            need_credit = all_credit - user_credit
            weighted_gpa_sum = sum(entry["gpa"] * entry["credit"] for entry in final_grades_list)
            current_gpa = round(weighted_gpa_sum / user_credit, 2) if user_credit > 0 else 0  # **保留两位小数**

            targets = [2.5, 2.6, 2.7, 2.8, 2.9, 3.0, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9]
            required_gpas = {
                target: round(calculate_required_gpa(current_gpa, user_credit, need_credit, target), 2)
                if isinstance(calculate_required_gpa(current_gpa, user_credit, need_credit, target), float)
                else "不可达到"
                for target in targets
            }  # **确保目标 GPA 计算值保留两位小数**


            # 发送 GPA 总览数据
            gpa_summary = {
                "majorCode": data["majorCode"],
                "majorName": data["majorName"],
                "totalCredits": all_credit,
                "completedCredits": user_credit,
                "remainingCredits": need_credit,
                "currentGpa": round(current_gpa, 2),  # **保留两位小数**
                "requiredGpas": required_gpas,
                "GPAChart": semester_gpa
            }

            yield json.dumps(gpa_summary) + "\n"

        except requests.exceptions.RequestException as e:
            yield f"❌ 失败: 网络错误 {str(e)}\n"
        except Exception as e:
            yield f"❌ 失败: {str(e)}\n"

    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")
