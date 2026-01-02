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
from proxy_manager import parse_proxy_format  # 代理格式解析

# 初始化日志
setup_logging()
import logging

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

# Flask 应用
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
# Session Cookie 配置（确保 POST 请求也发送 cookie）
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # 本地开发不需要 HTTPS

# 配置
config = Config()

# 代理池管理器（全局单例）
_proxy_manager = None

def get_proxy_manager():
    """获取代理池管理器（懒加载）"""
    global _proxy_manager
    if _proxy_manager is None and config.has_proxy_pool():
        from proxy_manager import ProxyManager
        _proxy_manager = ProxyManager(
            proxy_list=config.get_proxy_list(),
            strategy=config.get_proxy_strategy(),
            bad_proxy_ttl=config.get_proxy_bad_ttl()
        )
    return _proxy_manager


def get_proxy_for_task(mode: str = 'camoufox') -> Optional[str]:
    """
    为任务获取代理（智能策略）

    Args:
        mode: 'cdp' 或 'camoufox'

    Returns:
        代理字符串，无代理返回 None
    """
    proxy_mode = config.get_proxy_mode()

    # CDP 模式：不使用代理（浏览器插件处理）
    if mode == 'cdp':
        logger.info(f"[Proxy] CDP 模式 - 不设置代理（由浏览器插件管理）")
        return None

    # Camoufox 模式：根据 proxy_mode 决定策略
    if mode == 'camoufox':
        # 策略 1: main_only - 只使用主代理
        if proxy_mode == 'main_only':
            main_proxy = config.get_proxy_server()
            if main_proxy:
                logger.info(f"[Proxy] 使用主代理（main_only 模式）")
                return main_proxy
            logger.warning(f"[Proxy] main_only 模式但未配置主代理")
            return None

        # 策略 2: pool_only - 只使用代理池
        elif proxy_mode == 'pool_only':
            proxy_manager = get_proxy_manager()
            if proxy_manager:
                proxy = proxy_manager.get_proxy()
                if proxy:
                    logger.info(f"[Proxy] 使用代理池")
                    return proxy
                logger.warning(f"[Proxy] 代理池为空，使用直连")
                return None
            logger.warning(f"[Proxy] pool_only 模式但未配置代理池")
            return None

        # 策略 3: pool_with_fallback - 代理池优先，失败时用主代理（推荐）
        else:  # pool_with_fallback
            proxy_manager = get_proxy_manager()
            if proxy_manager:
                proxy = proxy_manager.get_proxy()
                if proxy:
                    logger.info(f"[Proxy] 使用代理池（优先）")
                    return proxy
                else:
                    # 代理池失败，fallback 到主代理
                    main_proxy = config.get_proxy_server()
                    if main_proxy:
                        logger.warning(f"[Proxy] 代理池为空，切换到主代理（fallback）")
                        return main_proxy
                    logger.warning(f"[Proxy] 代理池和主代理均为空，使用直连")
                    return None
            else:
                # 没有代理池，直接用主代理
                main_proxy = config.get_proxy_server()
                if main_proxy:
                    logger.info(f"[Proxy] 未配置代理池，使用主代理")
                    return main_proxy
                logger.warning(f"[Proxy] 未配置任何代理")
                return None

    return None

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

    # 从邮箱池补充密码和 JWT（仅当数据库字段为空时）
    try:
        pool = get_email_pool()
        for acc in paged_accounts:
            email_addr = acc.get('email', '')
            pool_email = pool.get_by_address(email_addr)
            if pool_email:
                # 只有数据库密码为空时，才用邮箱池补充
                if pool_email.get('password') and not acc.get('password'):
                    acc['password'] = pool_email['password']
                # 补充 JWT
                if pool_email.get('jwt') and not acc.get('jwt'):
                    acc['jwt'] = pool_email['jwt']
    except Exception as e:
        logger.warning(f"[Accounts] 从邮箱池补充数据失败: {e}")

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

    # 补充 JWT（密码以数据库为准，不用邮箱池覆盖）
    try:
        pool = get_email_pool()
        pool_email = pool.get_by_address(email)
        if pool_email:
            # 只补充 JWT，不覆盖密码
            if pool_email.get('jwt') and not account.get('jwt'):
                account['jwt'] = pool_email['jwt']
    except Exception as e:
        logger.warning(f"[Account Detail] 从邮箱池补充 JWT 失败: {e}")

    # 获取该账号的验证记录
    verifications = get_verifications_by_account(account['id'])

    return jsonify({
        'success': True,
        'account': account,
        'verifications': verifications
    })


@app.route('/api/accounts/<path:email>/tag', methods=['PUT'])
@require_auth
def api_update_account_tag(email: str):
    """更新账号标签"""
    data = request.get_json()
    tag = data.get('tag', 'unused')

    # 验证标签值
    valid_tags = ['unused', 'sold', 'used']
    if tag not in valid_tags:
        return jsonify({'success': False, 'error': f'无效标签，可选: {valid_tags}'}), 400

    try:
        update_account(email, tag=tag)
        return jsonify({'success': True, 'message': f'标签已更新为 {tag}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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

    # 代理池状态
    proxy_manager = get_proxy_manager()
    proxy_stats = proxy_manager.get_stats() if proxy_manager else {
        'total': 0,
        'available': 0,
        'bad': 0,
        'strategy': 'none',
        'proxies': []
    }

    return jsonify({
        'success': True,
        'accounts': acc_stats.get('by_status', {}),
        'veterans': {
            'total': vet_stats.get('total', 0),
            'used': vet_stats.get('used', 0),
            'available': vet_stats.get('available', 0)
        },
        'verifications': ver_stats.get('by_status', {}),
        'proxy_pool': proxy_stats,
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
        # 迁移旧数据：为没有密码的邮箱生成密码
        migrated = _email_pool.migrate_add_passwords()
        if migrated > 0:
            logger.info(f"[App] 邮箱池迁移完成: 为 {migrated} 个邮箱生成密码")
        # 迁移旧数据：为没有注册信息的邮箱生成信息
        migrated_profiles = _email_pool.migrate_add_profiles()
        if migrated_profiles > 0:
            logger.info(f"[App] 邮箱池迁移完成: 为 {migrated_profiles} 个邮箱生成注册信息")
        # 同步数据库状态到邮箱池（修复验证成功后邮箱池没更新的问题）
        synced = _email_pool.sync_from_database()
        if synced > 0:
            logger.info(f"[App] 邮箱池同步完成: {synced} 个邮箱状态更新")
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


# ==================== 代理池 API ====================

def _save_proxies_to_pool(proxies: list, protocol: str = 'http') -> dict:
    """
    保存代理到代理池文件并重新加载

    Args:
        proxies: 解析后的代理列表
        protocol: 协议类型

    Returns:
        {added: int, duplicates: int, file_path: str}
    """
    import os
    from pathlib import Path

    # 确定保存文件路径
    data_dir = Path('./data')
    data_dir.mkdir(exist_ok=True)

    file_map = {
        'http': 'proxies_http.txt',
        'https': 'proxies_https.txt',
        'socks5': 'proxies_socks5.txt',
    }
    file_name = file_map.get(protocol, 'proxies_http.txt')
    file_path = data_dir / file_name

    # 读取现有代理（如果存在）
    existing_proxies = set()
    if file_path.exists():
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        existing_proxies.add(line)
        except Exception as e:
            logger.warning(f"[Proxy] 读取现有代理文件失败: {e}")

    # 去重，找出新代理
    new_proxies = [p for p in proxies if p not in existing_proxies]
    duplicates = len(proxies) - len(new_proxies)

    # 追加新代理到文件
    if new_proxies:
        try:
            with open(file_path, 'a', encoding='utf-8') as f:
                for proxy in new_proxies:
                    f.write(proxy + '\n')
            logger.info(f"[Proxy] 保存 {len(new_proxies)} 个新代理到 {file_path}")
        except Exception as e:
            logger.error(f"[Proxy] 保存代理失败: {e}")
            return {'added': 0, 'duplicates': duplicates, 'file_path': str(file_path), 'error': str(e)}

    # 重新加载代理池
    global _proxy_manager
    _proxy_manager = None  # 清除缓存，下次使用时重新加载
    logger.info(f"[Proxy] 代理池已刷新")

    return {
        'added': len(new_proxies),
        'duplicates': duplicates,
        'file_path': str(file_path)
    }


@app.route('/api/proxy/parse', methods=['POST'])
@require_auth
def api_parse_proxy():
    """
    解析粘贴的代理列表（支持多种格式）

    请求: {
        "text": "ip:port\\nip2:port2\\n...",
        "protocol": "http" | "https" | "socks5",  # 默认 http
        "save": true  # 是否保存到代理池（默认 false，只解析预览）
    }

    返回: {
        "success": true,
        "proxies": ["http://ip:port", ...],
        "parsed": 10,  # 成功解析数量
        "failed": 2,   # 失败数量
        "added": 8,    # 新增数量（save=true 时）
        "duplicates": 2 # 重复跳过数量（save=true 时）
    }
    """
    data = request.get_json() or {}
    text = data.get('text', '').strip()
    protocol = data.get('protocol', 'http')
    save = data.get('save', False)  # 是否保存

    if not text:
        return jsonify({
            'success': False,
            'error': '代理列表为空'
        }), 400

    from proxy_manager import parse_proxy_format

    lines = [line.strip() for line in text.split('\n') if line.strip() and not line.startswith('#')]
    proxies = []
    failed_count = 0

    for line in lines:
        proxy = parse_proxy_format(line, protocol)
        if proxy:
            proxies.append(proxy)
        else:
            failed_count += 1

    result = {
        'success': True,
        'proxies': proxies,
        'parsed': len(proxies),
        'failed': failed_count,
        'total': len(lines)
    }

    # 如果需要保存
    if save and proxies:
        save_result = _save_proxies_to_pool(proxies, protocol)
        result.update(save_result)

    return jsonify(result)


@app.route('/api/proxy/upload', methods=['POST'])
@require_auth
def api_upload_proxy_file():
    """
    上传代理文件并解析

    请求（multipart/form-data）:
        file: 代理文件（txt）
        protocol: http | https | socks5（默认 http）
        save: true | false（是否保存到代理池，默认 true）
    """
    if 'file' not in request.files:
        return jsonify({
            'success': False,
            'error': '未上传文件'
        }), 400

    file = request.files['file']
    protocol = request.form.get('protocol', 'http')
    save = request.form.get('save', 'true').lower() == 'true'  # 默认保存

    if file.filename == '':
        return jsonify({
            'success': False,
            'error': '文件名为空'
        }), 400

    # 读取文件内容（处理 BOM）
    try:
        content = file.read().decode('utf-8-sig')  # utf-8-sig 自动处理 BOM
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'文件读取失败: {str(e)}'
        }), 400

    from proxy_manager import parse_proxy_format

    lines = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('#')]
    proxies = []
    failed_count = 0

    for line in lines:
        proxy = parse_proxy_format(line, protocol)
        if proxy:
            proxies.append(proxy)
        else:
            failed_count += 1

    result = {
        'success': True,
        'proxies': proxies,
        'parsed': len(proxies),
        'failed': failed_count,
        'total': len(lines),
        'filename': file.filename
    }

    # 如果需要保存
    if save and proxies:
        save_result = _save_proxies_to_pool(proxies, protocol)
        result.update(save_result)

    return jsonify(result)


@app.route('/api/proxy/stats', methods=['GET'])
@require_auth
def api_proxy_stats():
    """获取代理池统计信息"""
    proxy_manager = get_proxy_manager()
    main_proxy = config.get_proxy_server()

    stats = {
        'pool': proxy_manager.get_stats() if proxy_manager else {
            'total': 0,
            'available': 0,
            'bad': 0,
            'strategy': config.get_proxy_strategy(),
            'proxies': []
        },
        'main_proxy': main_proxy if main_proxy else None,
        'mode': config.get_proxy_mode(),
        'prefer_type': config.get_proxy_prefer_type()
    }

    return jsonify({
        'success': True,
        **stats
    })


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
    启动验证任务

    请求: {
        "email": "xxx@009025.xyz",     # 必填: ChatGPT 账号邮箱
        "password": "xxx",             # 可选: 账号密码（自有账号模式必填）
        "temp_email": "yyy@009025.xyz",# 可选: 临时邮箱（自有账号模式用于接收 SheerID 链接）
        "temp_jwt": "xxx",             # 可选: 临时邮箱 JWT
        "jwt": "xxx",                  # 可选: 用于自动获取验证链接
        "mode": "cdp" | "camoufox",    # 可选: 默认 camoufox
        "headless": true,              # 可选: 是否无头模式
        "proxy_mode": "none" | "fixed" | "pool",  # 可选: 代理模式（默认 none=直连）
        "fixed_proxy": "http://..."    # 可选: 固定代理地址（proxy_mode=fixed 时必填）
    }

    两种模式:
    - 临时邮箱账号: email=临时邮箱，验证码自动获取
    - 自有账号: email=Gmail等，password必填，temp_email用于接收SheerID链接

    代理模式:
    - none: 直连，不使用代理
    - fixed: 使用指定的固定代理
    - pool: 从代理池轮换
    """
    data = request.get_json() or {}
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()  # 账号密码
    temp_email = data.get('temp_email', '').strip()  # 临时邮箱（自有账号模式）
    temp_jwt = data.get('temp_jwt', '').strip()  # 临时邮箱 JWT
    jwt = data.get('jwt', '').strip()  # 兼容旧参数
    mode = data.get('mode', 'camoufox')  # 默认 camoufox
    headless = data.get('headless', True)  # 默认无头
    proxy_mode = data.get('proxy_mode', 'none')  # 代理模式: none/fixed/pool
    fixed_proxy = data.get('fixed_proxy', '').strip()  # 固定代理地址

    if not email:
        return jsonify({'success': False, 'error': '邮箱必填'}), 400

    # 判断是否自有账号模式
    is_own_account = bool(password and temp_email)

    # 如果是临时邮箱账号模式，尝试从邮箱池获取 JWT
    if not is_own_account:
        if not jwt:
            try:
                pool = get_email_pool()
                email_data = pool.get_by_address(email)
                if email_data:
                    jwt = email_data.get('jwt', '')
                    logger.info(f"[Verify] 从邮箱池获取 JWT: {email}")
            except Exception as e:
                logger.warning(f"[Verify] 获取邮箱 JWT 失败: {e}")
    else:
        # 自有账号模式，添加临时邮箱到池
        if temp_jwt:
            try:
                pool = get_email_pool()
                pool.add_external(temp_email, temp_jwt)
                logger.info(f"[Verify] 临时邮箱已添加到池: {temp_email}")
            except Exception as e:
                logger.warning(f"[Verify] 添加临时邮箱失败: {e}")

    # 检查是否已有运行中的任务
    with _task_lock:
        if email in _running_tasks and _running_tasks[email].get('status') == 'running':
            return jsonify({
                'success': False,
                'error': f'任务已在运行中: {email}'
            }), 400

    # 启动后台任务
    def run_verify_task(email, mode, headless, password_param=None, temp_email_param=None, is_own_account=False, proxy_mode_param='none', fixed_proxy_param=None):
        import sys

        with _task_lock:
            _running_tasks[email] = {
                'status': 'running',
                'started_at': datetime.now().isoformat(),
                'mode': mode,
                'is_own_account': is_own_account,
                'temp_email': temp_email_param,
                'proxy_mode': proxy_mode_param,
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
            if mode in ('cdp', 'cdp_auto', 'cdp_manual'):
                if mode == 'cdp_manual':
                    update_log("模式: CDP 手动登录 (你已登录，脚本自动验证)")
                else:
                    update_log("模式: CDP 全自动 (脚本自动登录)")

                # 使用当前 Python 解释器
                python_exe = sys.executable
                script_path = os.path.join(os.path.dirname(__file__), 'run_verify.py')

                # 构建命令参数
                cmd_args = [python_exe, '-u', script_path, '--email', email]
                if mode == 'cdp_manual':
                    cmd_args.append('--skip-login')  # 跳过登录步骤
                    update_log("跳过登录步骤，直接进行验证...")

                update_log(f"执行: {' '.join(cmd_args)}")

                # 使用 Popen 实时读取输出
                process = subprocess.Popen(
                    cmd_args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
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
                # 使用 Camoufox 自动化（支持自动登录）
                if is_own_account:
                    update_log(f"模式: Camoufox 自有账号 (有窗口，需手动输入验证码)")
                    update_log(f"临时邮箱: {temp_email_param} (接收 SheerID 链接)")
                else:
                    update_log("模式: Camoufox 临时邮箱账号 (全自动)")

                import asyncio
                from automation.camoufox_verify import CamoufoxVerifier
                from database import get_account_by_email
                from automation.config import generate_password

                # 获取或生成密码（优先级：用户提供 > 邮箱池 > 数据库 > 生成新密码）
                if password_param:
                    # 自有账号模式，使用传入的密码
                    task_password = password_param
                    update_log("使用用户提供的密码")
                else:
                    # 临时邮箱账号模式
                    # 1. 优先从邮箱池获取（密码在创建邮箱时预生成）
                    pool = get_email_pool()
                    pool_email = pool.get_by_address(email)
                    if pool_email and pool_email.get('password'):
                        task_password = pool_email['password']
                        update_log(f"使用邮箱池中的密码")
                    else:
                        # 2. 从数据库获取
                        account = get_account_by_email(email)
                        if account and account.get('password'):
                            task_password = account['password']
                            update_log("使用数据库中的密码")
                        else:
                            # 3. 生成新密码并保存到邮箱池
                            task_password = generate_password()
                            pool.update_password(email, task_password)
                            update_log("生成新密码并保存到邮箱池")

                # 根据代理模式选择代理
                proxy = None
                if proxy_mode_param == 'none':
                    update_log("代理模式: 直连（不使用代理）")
                elif proxy_mode_param == 'fixed':
                    if fixed_proxy_param:
                        proxy = fixed_proxy_param
                        from proxy_manager import ProxyManager
                        masked_proxy = ProxyManager._mask_proxy(None, proxy)
                        update_log(f"代理模式: 固定代理 - {masked_proxy}")
                    else:
                        update_log("警告: 固定代理模式但未提供代理地址，使用直连")
                elif proxy_mode_param == 'pool':
                    proxy = get_proxy_for_task(mode='camoufox')
                    if proxy:
                        from proxy_manager import ProxyManager
                        masked_proxy = ProxyManager._mask_proxy(None, proxy)
                        update_log(f"代理模式: 代理池 - {masked_proxy}")
                    else:
                        update_log("警告: 代理池为空，使用直连")
                else:
                    update_log(f"未知代理模式: {proxy_mode_param}，使用直连")

                async def run():
                    # 确定 SheerID 表单用的邮箱
                    # 自有账号模式：用临时邮箱接收链接
                    # 临时邮箱账号模式：用同一个邮箱
                    sheerid_email = temp_email_param if is_own_account else email

                    verifier = CamoufoxVerifier(
                        account_email=email,
                        headless=headless,
                        proxy=proxy,
                        screenshot_dir="screenshots"
                    )
                    success = await verifier.run_verify_loop(
                        password=task_password,
                        auto_login=True,
                        sheerid_email=sheerid_email  # SheerID 表单用的邮箱
                    )

                    # 根据结果更新代理状态
                    proxy_manager = get_proxy_manager()
                    if proxy_manager and proxy:
                        if success:
                            proxy_manager.mark_success(proxy)
                            update_log(f"代理验证成功: {masked_proxy}")
                        else:
                            proxy_manager.mark_bad(proxy)
                            update_log(f"代理验证失败: {masked_proxy}")

                    return success

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
    thread = threading.Thread(
        target=run_verify_task,
        args=(email, mode, headless, password, temp_email, is_own_account, proxy_mode, fixed_proxy)
    )
    thread.daemon = True
    thread.start()

    return jsonify({
        'success': True,
        'message': f'验证任务已启动: {email}',
        'mode': mode,
        'proxy_mode': proxy_mode,
        'fixed_proxy': fixed_proxy if proxy_mode == 'fixed' else None
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


@app.route('/api/verify/emergency/<path:email>', methods=['GET'])
@require_auth
def api_get_emergency_info(email: str):
    """
    获取应急登录信息（当脚本卡住时，用户可手动登录）

    返回:
    {
        "success": true,
        "email": "xxx@009025.xyz",
        "password": "xxxx",  # ChatGPT 登录密码
        "email_login_url": "https://one.009025.xyz/",  # 查看验证码的邮箱前端
        "jwt": "xxx",  # 邮箱 JWT（可选）
        "instructions": "..."  # 手动登录说明
    }
    """
    # 从邮箱池获取密码
    password = None
    jwt = None

    try:
        pool = get_email_pool()
        email_data = pool.get_by_address(email)
        if email_data:
            password = email_data.get('password')
            jwt = email_data.get('jwt')
    except Exception as e:
        logger.warning(f"[Emergency] 获取邮箱数据失败: {e}")

    # 如果邮箱池没有密码，从数据库获取
    if not password:
        try:
            account = get_account_by_email(email)
            if account:
                password = account.get('password')
        except Exception as e:
            logger.warning(f"[Emergency] 获取账号数据失败: {e}")

    # 如果都没有，生成一个新密码
    if not password:
        password = generate_password()
        logger.info(f"[Emergency] 生成新密码: {email}")

        # 保存到邮箱池
        try:
            pool = get_email_pool()
            pool.update_password(email, password)
        except:
            pass

    # 获取邮箱的注册信息（姓名、生日）
    profile_data = None
    try:
        pool = get_email_pool()
        email_data = pool.get_by_address(email)
        if email_data:
            # 从邮箱池获取注册信息
            profile_data = {
                'first_name': email_data.get('first_name', ''),
                'last_name': email_data.get('last_name', ''),
                'birth_month': email_data.get('birth_month', ''),
                'birth_day': email_data.get('birth_day', ''),
                'birth_year': email_data.get('birth_year', '')
            }
            if profile_data['first_name']:
                logger.info(f"[Emergency] 获取注册信息: {profile_data['first_name']} {profile_data['last_name']}")
            else:
                # 邮箱池中没有注册信息（旧数据），生成新的
                from email_pool import generate_random_profile
                profile = generate_random_profile()
                profile_data = profile
                # 保存到邮箱池
                pool.update_profile(email, profile['first_name'], profile['last_name'],
                                   profile['birth_month'], profile['birth_day'], profile['birth_year'])
                logger.info(f"[Emergency] 生成注册信息: {profile['first_name']} {profile['last_name']}")
    except Exception as e:
        logger.warning(f"[Emergency] 获取注册信息失败: {e}")

    return jsonify({
        'success': True,
        'email': email,
        'password': password,
        'email_login_url': 'https://one.009025.xyz/',
        'jwt': jwt or '',
        'profile_data': profile_data,  # 注册时填写的姓名和生日
        'instructions': '''手动登录步骤：
1. 打开 https://chatgpt.com/veterans-claim
2. 点击 "登录"
3. 输入邮箱和密码
4. 如果需要验证码，访问邮箱前端获取
5. 注册时如果要求填姓名/生日，使用下方信息
6. 登录成功后，点击下方"我已登录，继续验证"按钮'''
    })


@app.route('/api/verify/manual-continue/<path:email>', methods=['POST'])
@require_auth
def api_manual_continue_verify(email: str):
    """
    用户手动登录后，继续执行验证流程（跳过登录步骤）

    请求: {
        "mode": "cdp"  # 目前只支持 CDP 模式
    }

    流程:
    1. 停止当前卡住的任务（如果有）
    2. 启动新任务，但跳过登录步骤，直接从验证页面开始
    """
    data = request.get_json() or {}
    mode = data.get('mode', 'cdp')

    logger.info(f"[ManualContinue] 用户手动登录后继续: {email}")

    # 停止当前任务
    with _task_lock:
        if email in _running_tasks:
            task = _running_tasks[email]
            task['stop_requested'] = True
            process = task.get('process')
            if process:
                try:
                    process.terminate()
                    logger.info(f"[ManualContinue] 终止旧任务: {email}")
                except:
                    pass
            # 清除任务记录
            del _running_tasks[email]

    import time
    time.sleep(1)

    # 启动新任务（跳过登录）
    def run_continue_task(email):
        import sys
        import subprocess

        with _task_lock:
            _running_tasks[email] = {
                'status': 'running',
                'started_at': datetime.now().isoformat(),
                'mode': 'cdp',
                'manual_continue': True,  # 标记为手动继续
                'logs': ['用户手动登录后继续验证...']
            }

        def update_log(msg):
            with _task_lock:
                if email in _running_tasks:
                    logs = _running_tasks[email].get('logs', [])
                    logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
                    _running_tasks[email]['logs'] = logs[-50:]

        try:
            update_log("模式: CDP (跳过登录，直接验证)")

            python_exe = sys.executable
            script_path = os.path.join(os.path.dirname(__file__), 'run_verify.py')

            # 添加 --skip-login 参数（需要在 run_verify.py 中支持）
            process = subprocess.Popen(
                [python_exe, '-u', script_path, '--email', email, '--skip-login'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
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
            update_log(f"错误: {e}")
            with _task_lock:
                _running_tasks[email].update({
                    'status': 'error',
                    'error': str(e),
                    'completed_at': datetime.now().isoformat()
                })

    thread = threading.Thread(target=run_continue_task, args=(email,))
    thread.daemon = True
    thread.start()

    return jsonify({
        'success': True,
        'message': f'验证任务已继续（跳过登录）: {email}'
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
