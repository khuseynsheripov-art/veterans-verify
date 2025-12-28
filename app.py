"""
Veterans Verify - Flask 主应用
ChatGPT Veterans 验证自动化系统

参考 test_band_gemini_mail 项目架构
实现批量创建临时邮箱 + 注册 ChatGPT + Veterans 验证
"""
import os
import json
import random
from functools import wraps
from datetime import datetime, timedelta
from typing import Dict, Optional

from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from dotenv import load_dotenv
from pathlib import Path

# 加载环境变量（按顺序：默认值 → 用户配置）
# 1. 先加载 .env.example（默认值）
env_example = Path('.env.example')
if env_example.exists():
    load_dotenv(env_example)

# 2. 再加载 .env.local（用户配置，覆盖默认值）
env_local = Path('.env.local')
if env_local.exists():
    load_dotenv(env_local, override=True)

# 3. 向后兼容：如果存在 .env，也加载
env_file = Path('.env')
if env_file.exists():
    load_dotenv(env_file, override=True)

from config import Config, setup_logging

# 初始化日志
setup_logging()
import logging

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

# Flask 应用
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# 配置
config = Config()

# 导入数据库模块
from database import (
    get_accounts, get_account_by_email, create_account, update_account,
    get_accounts_stats, get_veterans_stats, get_available_veteran,
    mark_veteran_used, get_verifications_by_account, get_latest_verification,
    create_verification, update_verification, get_verifications_stats
)
from automation.config import generate_discharge_date, generate_password


# ==================== 认证 ====================

def check_auth():
    """检查认证"""
    # API Token 认证
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        if token == os.getenv('ADMIN_TOKEN'):
            return True

    # X-API-Key 认证
    api_key = request.headers.get('X-API-Key')
    if api_key and api_key == os.getenv('ADMIN_TOKEN'):
        return True

    # Session 认证
    if session.get('authenticated'):
        return True

    return False


def require_auth(f):
    """认证装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not check_auth():
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': 'Unauthorized'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ==================== 页面路由 ====================

@app.route('/')
def index():
    """首页"""
    if not check_auth():
        return redirect(url_for('login'))
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        expected_username = os.getenv('ADMIN_USERNAME', 'admin')
        expected_password = os.getenv('ADMIN_PASSWORD', '')

        # 调试日志
        logger.info(f"[Login] 尝试登录: username={username}")
        logger.debug(f"[Login] 期望: username={expected_username}, password={'*' * len(expected_password) if expected_password else '(空)'}")

        if (username == expected_username and password == expected_password):
            session['authenticated'] = True
            logger.info(f"[Login] 登录成功: {username}")
            return redirect(url_for('index'))
        else:
            logger.warning(f"[Login] 登录失败: {username}")
            return render_template('login.html', error='Invalid credentials')

    return render_template('login.html')


@app.route('/api/login', methods=['POST'])
def api_login():
    """API 登录"""
    data = request.get_json() or {}
    username = data.get('username', '')
    password = data.get('password', '')

    if (username == os.getenv('ADMIN_USERNAME', 'admin') and
        password == os.getenv('ADMIN_PASSWORD')):
        return jsonify({
            'success': True,
            'token': os.getenv('ADMIN_TOKEN', ''),
            'message': '登录成功'
        })

    return jsonify({
        'success': False,
        'message': '用户名或密码错误'
    }), 401


@app.route('/logout')
def logout():
    """登出"""
    session.pop('authenticated', None)
    return redirect(url_for('login'))


# ==================== 账号 API ====================

@app.route('/api/accounts', methods=['GET'])
@require_auth
def api_get_accounts():
    """获取账号列表"""
    status_filter = request.args.get('status')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))

    # 直接使用数据库
    accounts = get_accounts(status=status_filter, limit=per_page * page)

    # 简单分页
    start = (page - 1) * per_page
    end = start + per_page
    paged_accounts = accounts[start:end]

    stats = get_accounts_stats()
    total = stats.get('total', 0)
    total_pages = max(1, (total + per_page - 1) // per_page)

    return jsonify({
        'success': True,
        'accounts': paged_accounts,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
        'stats': stats.get('by_status', {})
    })


@app.route('/api/accounts/<path:email>', methods=['GET'])
@require_auth
def api_get_account(email: str):
    """获取单个账号"""
    account = get_account_by_email(email)
    if not account:
        return jsonify({'success': False, 'error': '账号不存在'}), 404

    # 获取该账号的验证记录
    verifications = get_verifications_by_account(account['id'])

    return jsonify({
        'success': True,
        'account': account,
        'verifications': verifications
    })


@app.route('/api/accounts/export', methods=['GET'])
@require_auth
def api_export_accounts():
    """导出成功的账号（包含完整信息）"""
    accounts = get_accounts(status='verified', limit=10000)

    # 为每个账号添加验证成功的军人信息
    enriched_accounts = []
    for acc in accounts:
        account_data = {
            # ChatGPT 登录信息
            'email': acc.get('email'),
            'password': acc.get('password'),
            'status': acc.get('status'),

            # 临时邮箱凭证
            'email_login_url': 'https://one.009025.xyz/',
            'jwt': acc.get('jwt') or '',

            # 注册时填写的信息
            'profile_name': acc.get('profile_name'),
            'profile_birthday': acc.get('profile_birthday'),

            # 时间戳
            'created_at': acc.get('created_at'),
            'updated_at': acc.get('updated_at'),

            # 备注
            'note': acc.get('note'),

            # 验证成功的军人信息
            'verified_veteran': None
        }

        # 获取成功的验证记录
        try:
            verifications = get_verifications_by_account(acc.get('id'))
            success_ver = next((v for v in verifications if v.get('status') == 'success'), None)
            if success_ver:
                account_data['verified_veteran'] = {
                    'first_name': success_ver.get('first_name'),
                    'last_name': success_ver.get('last_name'),
                    'branch': success_ver.get('branch'),
                    'birth_date': f"{success_ver.get('birth_month')} {success_ver.get('birth_day')}, {success_ver.get('birth_year')}",
                    'discharge_date': f"{success_ver.get('discharge_month')} {success_ver.get('discharge_day')}, {success_ver.get('discharge_year')}",
                    'verified_at': success_ver.get('completed_at') or success_ver.get('created_at')
                }
        except Exception as e:
            logger.warning(f"获取验证记录失败: {e}")

        enriched_accounts.append(account_data)

    export_data = {
        'exported_at': datetime.now().isoformat(),
        'count': len(enriched_accounts),
        'accounts': enriched_accounts
    }

    return jsonify(export_data)


# ==================== 验证 API ====================

@app.route('/api/verify/prepare', methods=['POST'])
@require_auth
def api_verify_prepare():
    """
    准备验证：获取下一条军人数据

    请求: { "email": "xxx@009025.xyz" }
    返回: 表单数据 + 验证记录 ID
    """
    data = request.get_json() or {}
    email = data.get('email', '')

    if not email:
        return jsonify({'success': False, 'error': '邮箱必填'}), 400

    account = get_account_by_email(email)
    if not account:
        return jsonify({'success': False, 'error': '账号不存在'}), 404

    # 获取可用军人数据
    veteran = get_available_veteran()
    if not veteran:
        return jsonify({'success': False, 'error': '没有可用的军人数据'}), 400

    # 生成退伍日期
    discharge = generate_discharge_date()

    # 创建验证记录
    verification_id = create_verification(
        account_id=account['id'],
        veteran_id=veteran['id'],
        discharge_month=discharge['month'],
        discharge_day=discharge['day'],
        discharge_year=discharge['year']
    )

    # 构建表单数据
    form_data = {
        'status': 'Military Veteran or Retiree',
        'branch': veteran['branch'],
        'first_name': veteran['first_name'],
        'last_name': veteran['last_name'],
        'birth_month': veteran['birth_month'],
        'birth_day': veteran['birth_day'],
        'birth_year': veteran['birth_year'],
        'discharge_month': discharge['month'],
        'discharge_day': discharge['day'],
        'discharge_year': discharge['year'],
        'email': email,
    }

    return jsonify({
        'success': True,
        'verification_id': verification_id,
        'veteran_id': veteran['id'],
        'form_data': form_data
    })


@app.route('/api/verify/result', methods=['POST'])
@require_auth
def api_verify_result():
    """
    报告验证结果

    请求: {
        "verification_id": 123,
        "veteran_id": "xxx",
        "result": "success|verification_limit|not_approved|check_email|...",
        "message": "可选消息"
    }
    """
    data = request.get_json() or {}
    verification_id = data.get('verification_id')
    veteran_id = data.get('veteran_id')
    result = data.get('result', '')
    message = data.get('message', '')

    if not verification_id or not result:
        return jsonify({'success': False, 'error': '参数不完整'}), 400

    # 需要消耗军人数据的结果
    consume_results = ['verification_limit', 'not_approved', 'unable_to_verify']

    if result == 'success':
        update_verification(verification_id, status='success')
        # 更新账号状态
        verification = get_latest_verification(verification_id)
        if verification:
            account = get_account_by_email(verification.get('email', ''))
            if account:
                update_account(account['email'], status='verified')
        return jsonify({'success': True, 'action': 'done', 'message': '验证成功！'})

    elif result in consume_results:
        # 标记军人数据为已使用
        if veteran_id:
            mark_veteran_used(veteran_id, f"verification_{verification_id}: {result}")
        update_verification(verification_id, status='failed', error_type=result.upper(), error_message=message)
        return jsonify({'success': True, 'action': 'next', 'message': '换下一条数据继续'})

    elif result == 'check_email':
        update_verification(verification_id, status='pending_email')
        return jsonify({'success': True, 'action': 'wait_email', 'message': '等待邮件验证'})

    else:
        update_verification(verification_id, status='failed', error_type='UNKNOWN', error_message=message)
        return jsonify({'success': True, 'action': 'retry', 'message': '未知错误，请重试'})


@app.route('/api/verify/stats', methods=['GET'])
@require_auth
def api_verify_stats():
    """获取验证统计"""
    v_stats = get_verifications_stats()
    vet_stats = get_veterans_stats()

    return jsonify({
        'success': True,
        'verifications': v_stats,
        'veterans': vet_stats
    })


# ==================== 系统 API ====================

@app.route('/api/status', methods=['GET'])
@require_auth
def api_status():
    """系统状态"""
    acc_stats = get_accounts_stats()
    vet_stats = get_veterans_stats()
    ver_stats = get_verifications_stats()

    return jsonify({
        'success': True,
        'accounts': acc_stats.get('by_status', {}),
        'veterans': {
            'total': vet_stats.get('total', 0),
            'used': vet_stats.get('used', 0),
            'available': vet_stats.get('available', 0)
        },
        'verifications': ver_stats.get('by_status', {}),
        'queue_size': 0  # 兼容旧前端
    })


@app.route('/api/settings', methods=['GET'])
@require_auth
def get_settings():
    """获取设置"""
    return jsonify({
        'success': True,
        'settings': {
            'max_workers': config.get_max_workers(),
            'headless': config.get_headless(),
            'email_configs': config.get_email_configs(),
            'human_delay': config.get_human_delay(),
            'request_interval': config.get_request_interval(),
            'cooldown_range': config.get_cooldown_range(),
        }
    })


@app.route('/api/email-configs', methods=['GET'])
@require_auth
def get_email_configs():
    """获取邮箱配置"""
    configs = config.get_email_configs()
    # 隐藏敏感信息
    safe_configs = []
    for cfg in configs:
        safe_configs.append({
            'worker_domain': cfg.get('worker_domain', ''),
            'email_domain': cfg.get('email_domain', ''),
            'admin_password': '***' if cfg.get('admin_password') else ''
        })
    return jsonify({
        'success': True,
        'configs': safe_configs
    })


@app.route('/api/veteran-data/stats', methods=['GET'])
@require_auth
def api_get_veteran_stats():
    """获取军人数据统计"""
    stats = get_veterans_stats()
    return jsonify({
        'success': True,
        'stats': stats
    })


# ==================== 邮箱池 API ====================

# 延迟初始化邮箱池管理器
_email_pool = None


def get_email_pool():
    """获取邮箱池管理器"""
    global _email_pool
    if _email_pool is None:
        from email_pool import EmailPoolManager
        _email_pool = EmailPoolManager()
        logger.info("[App] EmailPoolManager 初始化完成")
    return _email_pool


def reload_email_pool():
    """重新加载邮箱池（强制从文件读取）"""
    global _email_pool
    from email_pool import EmailPoolManager
    _email_pool = EmailPoolManager()
    logger.info("[App] EmailPoolManager 已重新加载")
    return _email_pool


@app.route('/api/email-pool/reload', methods=['POST'])
@require_auth
def api_reload_email_pool():
    """重新加载邮箱池数据"""
    pool = reload_email_pool()
    return jsonify({
        'success': True,
        'message': '邮箱池已重新加载',
        'stats': pool.get_stats()
    })


@app.route('/api/email-pool', methods=['GET'])
@require_auth
def get_email_pool_list():
    """获取邮箱池列表"""
    pool = get_email_pool()
    status_filter = request.args.get('status')

    if status_filter:
        from email_pool import EmailStatus
        try:
            status_enum = EmailStatus(status_filter)
            emails = pool.list_by_status(status_enum)
        except ValueError:
            emails = pool.list_all()
    else:
        emails = pool.list_all()

    stats = pool.get_stats()

    return jsonify({
        'success': True,
        'emails': emails,
        'stats': stats
    })


@app.route('/api/email-pool', methods=['POST'])
@require_auth
def create_emails():
    """批量创建邮箱"""
    data = request.get_json() or {}

    try:
        count = int(data.get('count', 1))
    except (ValueError, TypeError):
        count = 1

    count = max(1, min(50, count))  # 限制 1-50

    # 获取邮箱配置
    email_config = config.get_random_email_config()
    if not email_config:
        return jsonify({
            'success': False,
            'error': '未配置邮箱服务'
        }), 400

    from email_manager import EmailManager
    email_manager = EmailManager(
        worker_domain=email_config['worker_domain'],
        email_domain=email_config['email_domain'],
        admin_password=email_config['admin_password']
    )

    pool = get_email_pool()
    created = pool.create_emails(email_manager, count)

    return jsonify({
        'success': True,
        'message': f'成功创建 {len(created)} 个邮箱',
        'created': created,
        'stats': pool.get_stats()
    })


@app.route('/api/email-pool/add', methods=['POST'])
@require_auth
def add_external_email():
    """添加外部邮箱（用于半自动模式）"""
    data = request.get_json() or {}

    address = (data.get('address') or '').strip()
    jwt = (data.get('jwt') or '').strip()

    if not address or not jwt:
        return jsonify({
            'success': False,
            'error': '邮箱地址和 JWT 都是必填的'
        }), 400

    pool = get_email_pool()
    if pool.add_external(address, jwt):
        return jsonify({
            'success': True,
            'message': '邮箱添加成功',
            'email': pool.get_by_address(address)
        })

    return jsonify({
        'success': False,
        'error': '添加失败'
    }), 500


@app.route('/api/email-pool/<path:address>', methods=['DELETE'])
@require_auth
def delete_email(address: str):
    """删除邮箱"""
    pool = get_email_pool()
    if pool.delete(address):
        return jsonify({
            'success': True,
            'message': '邮箱已删除'
        })
    return jsonify({
        'success': False,
        'error': '邮箱不存在'
    }), 404


@app.route('/api/email-pool/<path:address>/reset', methods=['POST'])
@require_auth
def reset_email(address: str):
    """重置邮箱状态为可用"""
    pool = get_email_pool()
    if pool.reset_to_available(address):
        return jsonify({
            'success': True,
            'message': '邮箱已重置为可用'
        })
    return jsonify({
        'success': False,
        'error': '邮箱不存在'
    }), 404


# ==================== 验证任务 API ====================

import threading
import subprocess

# 当前运行的验证任务
_running_tasks = {}
_task_lock = threading.Lock()


@app.route('/api/verify/start', methods=['POST'])
@require_auth
def api_start_verify():
    """
    启动验证任务（模式4: 手动登录后接管）

    请求: {
        "email": "xxx@009025.xyz",     # 必填: 用于填写 SheerID 表单
        "jwt": "xxx",                  # 可选: 用于自动获取验证链接（如果在邮箱池中有则自动获取）
        "mode": "cdp" | "camoufox",    # 可选: 默认 cdp
        "headless": false              # 可选: 是否无头模式
    }

    注意:
    - 模式4 只需要邮箱地址，不需要账号存在于数据库
    - JWT 可选，有则自动点击验证链接，无则手动点击
    """
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    jwt = data.get('jwt', '').strip()  # 可选
    mode = data.get('mode', 'cdp')  # cdp=连接已打开浏览器, camoufox=无头自动化
    headless = data.get('headless', False)

    if not email:
        return jsonify({'success': False, 'error': '邮箱必填'}), 400

    # 如果提供了 JWT，添加到邮箱池
    if jwt:
        try:
            pool = get_email_pool()
            pool.add_external(email, jwt)
            logger.info(f"[Verify] 邮箱已添加到池: {email}")
        except Exception as e:
            logger.warning(f"[Verify] 添加邮箱到池失败: {e}")

    # 检查是否已有运行中的任务
    with _task_lock:
        if email in _running_tasks and _running_tasks[email].get('status') == 'running':
            return jsonify({
                'success': False,
                'error': f'任务已在运行中: {email}'
            }), 400

    # 启动后台任务
    def run_verify_task(email, mode, headless):
        import sys

        with _task_lock:
            _running_tasks[email] = {
                'status': 'running',
                'started_at': datetime.now().isoformat(),
                'mode': mode,
                'logs': ['任务已启动...']
            }

        def update_log(msg):
            """更新任务日志"""
            with _task_lock:
                if email in _running_tasks:
                    logs = _running_tasks[email].get('logs', [])
                    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
                    _running_tasks[email]['logs'] = logs[-50:]  # 保留最后50条

        try:
            if mode == 'cdp':
                update_log("模式: CDP (连接已打开的 Chrome)")

                # 使用当前 Python 解释器
                python_exe = sys.executable
                script_path = os.path.join(os.path.dirname(__file__), 'run_verify.py')

                update_log(f"执行: {python_exe} {script_path}")

                # 使用 Popen 实时读取输出
                process = subprocess.Popen(
                    [python_exe, '-u', script_path, '--email', email],  # -u 禁用缓冲
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,  # 行缓冲
                    cwd=os.path.dirname(__file__)
                )

                # 存储进程引用以便停止
                with _task_lock:
                    _running_tasks[email]['process'] = process

                # 实时读取输出
                output_lines = []
                try:
                    for line in iter(process.stdout.readline, ''):
                        if line:
                            line = line.strip()[:200]
                            output_lines.append(line)
                            update_log(line)
                        # 检查是否被请求停止
                        with _task_lock:
                            if _running_tasks.get(email, {}).get('stop_requested'):
                                process.terminate()
                                update_log("任务被用户停止")
                                break
                except Exception as e:
                    update_log(f"读取输出错误: {e}")

                process.wait(timeout=1800)
                success = process.returncode == 0
                output = '\n'.join(output_lines)

                update_log(f"脚本退出码: {process.returncode}")

            else:
                # 使用 Camoufox 无头自动化
                update_log("模式: Camoufox (无头自动化)")

                import asyncio
                from automation.camoufox_verify import CamoufoxVerifier

                async def run():
                    verifier = CamoufoxVerifier(
                        account_email=email,
                        headless=headless,
                        screenshot_dir="screenshots"
                    )
                    return await verifier.run_verify_loop()

                success = asyncio.run(run())
                output = "Camoufox 任务完成"
                update_log(output)

            with _task_lock:
                _running_tasks[email].update({
                    'status': 'success' if success else 'failed',
                    'completed_at': datetime.now().isoformat(),
                    'output': output[-2000:] if isinstance(output, str) else str(output)
                })

            update_log(f"任务完成: {'成功' if success else '失败'}")

        except subprocess.TimeoutExpired:
            update_log("错误: 任务超时 (30分钟)")
            with _task_lock:
                _running_tasks[email].update({
                    'status': 'timeout',
                    'error': '任务超时',
                    'completed_at': datetime.now().isoformat()
                })

        except Exception as e:
            import traceback
            error_msg = str(e)
            update_log(f"错误: {error_msg}")

            with _task_lock:
                _running_tasks[email].update({
                    'status': 'error',
                    'error': error_msg,
                    'traceback': traceback.format_exc(),
                    'completed_at': datetime.now().isoformat()
                })

    # 在后台线程运行
    thread = threading.Thread(target=run_verify_task, args=(email, mode, headless))
    thread.daemon = True
    thread.start()

    return jsonify({
        'success': True,
        'message': f'验证任务已启动: {email}',
        'mode': mode
    })


@app.route('/api/verify/status/<path:email>', methods=['GET'])
@require_auth
def api_verify_task_status(email: str):
    """获取验证任务状态"""
    with _task_lock:
        if email in _running_tasks:
            # 排除不可序列化的 process 对象
            task = {k: v for k, v in _running_tasks[email].items() if k != 'process'}
            return jsonify({
                'success': True,
                'task': task
            })

    return jsonify({
        'success': False,
        'error': '没有找到任务'
    }), 404


@app.route('/api/verify/stop/<path:email>', methods=['POST'])
@require_auth
def api_stop_verify(email: str):
    """停止验证任务"""
    with _task_lock:
        if email in _running_tasks:
            task = _running_tasks[email]
            task['stop_requested'] = True
            task['status'] = 'stopping'

            # 尝试终止进程
            process = task.get('process')
            if process:
                try:
                    process.terminate()
                    logger.info(f"[Verify] 终止进程: {email}")
                except Exception as e:
                    logger.warning(f"[Verify] 终止进程失败: {e}")

            task['status'] = 'stopped'
            task['completed_at'] = datetime.now().isoformat()

            return jsonify({
                'success': True,
                'message': '任务已停止'
            })

    return jsonify({
        'success': False,
        'error': '没有找到任务'
    }), 404


@app.route('/api/verify/running', methods=['GET'])
@require_auth
def api_get_running_tasks():
    """获取所有运行中的任务"""
    with _task_lock:
        running = []
        for email, task in _running_tasks.items():
            if task.get('status') in ['running', 'stopping']:
                running.append({
                    'email': email,
                    'status': task.get('status'),
                    'started_at': task.get('started_at'),
                    'mode': task.get('mode'),
                    'logs': task.get('logs', [])[-10:]  # 最后10条日志
                })
        return jsonify({
            'success': True,
            'tasks': running
        })


@app.route('/api/verify/restart/<path:email>', methods=['POST'])
@require_auth
def api_restart_verify(email: str):
    """重启验证任务：先停止再启动"""
    # 先停止当前任务
    with _task_lock:
        if email in _running_tasks:
            task = _running_tasks[email]
            task['stop_requested'] = True
            process = task.get('process')
            if process:
                try:
                    process.terminate()
                except:
                    pass

    # 等待进程结束
    import time
    time.sleep(1)

    # 获取原任务的模式
    mode = 'cdp'
    with _task_lock:
        if email in _running_tasks:
            mode = _running_tasks[email].get('mode', 'cdp')
            del _running_tasks[email]

    # 重新启动
    logger.info(f"[Verify] 重启任务: {email}")

    # 调用启动逻辑
    data = {'email': email, 'mode': mode}
    with app.test_request_context(json=data):
        # 直接调用启动函数的逻辑
        return api_start_verify_internal(email, mode)


def api_start_verify_internal(email: str, mode: str = 'cdp'):
    """内部启动验证任务函数"""
    import sys

    def run_verify_task(email, mode):
        with _task_lock:
            _running_tasks[email] = {
                'status': 'running',
                'started_at': datetime.now().isoformat(),
                'mode': mode,
                'logs': ['任务已启动...']
            }

        def update_log(msg):
            with _task_lock:
                if email in _running_tasks:
                    logs = _running_tasks[email].get('logs', [])
                    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
                    _running_tasks[email]['logs'] = logs[-50:]

        try:
            update_log(f"模式: {mode}")
            python_exe = sys.executable
            script_path = os.path.join(os.path.dirname(__file__), 'run_verify.py')

            process = subprocess.Popen(
                [python_exe, '-u', script_path, '--email', email],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=os.path.dirname(__file__)
            )

            with _task_lock:
                _running_tasks[email]['process'] = process

            for line in iter(process.stdout.readline, ''):
                if line:
                    update_log(line.strip()[:200])
                with _task_lock:
                    if _running_tasks.get(email, {}).get('stop_requested'):
                        process.terminate()
                        update_log("任务被用户停止")
                        break

            process.wait(timeout=1800)
            success = process.returncode == 0

            with _task_lock:
                _running_tasks[email].update({
                    'status': 'success' if success else 'failed',
                    'completed_at': datetime.now().isoformat()
                })
            update_log(f"任务完成: {'成功' if success else '失败'}")

        except Exception as e:
            with _task_lock:
                _running_tasks[email].update({
                    'status': 'error',
                    'error': str(e),
                    'completed_at': datetime.now().isoformat()
                })

    thread = threading.Thread(target=run_verify_task, args=(email, mode))
    thread.daemon = True
    thread.start()

    return jsonify({
        'success': True,
        'message': f'任务已重启: {email}',
        'mode': mode
    })


# ==================== 退出登录 ====================

@app.route('/api/logout/chatgpt', methods=['POST'])
@require_auth
def api_logout_chatgpt():
    """
    退出 ChatGPT 登录（通过 CDP 连接到已打开的 Chrome）

    前端调用场景：
    - 半自动模式验证成功后，用户想要退出登录
    - 手动清除登录状态
    """
    try:
        import asyncio

        async def do_logout():
            from playwright.async_api import async_playwright

            CDP_URL = "http://127.0.0.1:9488"

            async with async_playwright() as p:
                try:
                    browser = await p.chromium.connect_over_cdp(CDP_URL, timeout=10000)
                except Exception as e:
                    return False, f"无法连接 Chrome (确保已运行 start-chrome-devtools.bat): {e}"

                try:
                    contexts = browser.contexts
                    if not contexts:
                        return False, "没有找到浏览器上下文"

                    context = contexts[0]
                    pages = context.pages

                    # 找到 ChatGPT 页面
                    page = None
                    for pg in pages:
                        if "chatgpt.com" in pg.url or "openai.com" in pg.url:
                            page = pg
                            break

                    if not page:
                        # 如果没找到，使用第一个页面
                        if pages:
                            page = pages[0]
                        else:
                            return False, "没有找到可用页面"

                    # 退出方法1：访问登出 URL
                    try:
                        await page.goto("https://chatgpt.com/auth/logout", wait_until="domcontentloaded", timeout=10000)
                        await asyncio.sleep(2)
                        return True, "已通过登出 URL 退出"
                    except:
                        pass

                    # 退出方法2：清除 Cookies
                    try:
                        await context.clear_cookies()
                        await page.reload()
                        await asyncio.sleep(2)
                        return True, "已清除 Cookies"
                    except:
                        pass

                    return False, "退出登录失败"

                finally:
                    # 不关闭浏览器，只断开连接
                    pass

        success, message = asyncio.run(do_logout())

        return jsonify({
            'success': success,
            'message': message
        })

    except Exception as e:
        logger.error(f"[Logout] 错误: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== 服务控制 ====================

@app.route('/api/service/restart', methods=['POST'])
@require_auth
def api_restart_service():
    """重启 Flask 服务"""
    import sys
    import signal

    logger.info("[Service] 收到重启请求，3秒后重启...")

    def restart():
        time.sleep(3)
        logger.info("[Service] 正在重启服务...")
        # Windows 和 Unix 兼容的重启方式
        python = sys.executable
        os.execl(python, python, *sys.argv)

    # 在后台线程执行重启
    thread = threading.Thread(target=restart)
    thread.daemon = True
    thread.start()

    return jsonify({
        'success': True,
        'message': '服务将在 3 秒后重启，请刷新页面'
    })


# ==================== 健康检查 ====================

@app.route('/health')
def health():
    """健康检查"""
    return jsonify({'status': 'ok'})


@app.route('/api/health')
def api_health():
    """API 健康检查"""
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})


# ==================== 启动 ====================

if __name__ == '__main__':
    port = int(os.getenv('PORT', '7870'))
    debug = os.getenv('DEBUG', 'false').lower() == 'true'

    logger.info(f"[App] Veterans Verify 启动于端口 {port}")
    logger.info(f"[App] 访问 http://127.0.0.1:{port}")

    app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)
