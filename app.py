from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import json, os, re, urllib.parse, base64
from datetime import datetime, date
import calendar

try:
    import requests
    import zipfile, io
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'melmaga-kanri-itashin-2026')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

CYCLES_FILE    = os.path.join(DATA_DIR, 'cycles.json')
CONFIG_FILE    = os.path.join(DATA_DIR, 'config.json')
TEMPLATES_FILE = os.path.join(DATA_DIR, 'email_templates.json')

# ─── GitHub API によるデータ永続化（Render.com 等クラウド環境用） ──────────────
# ローカル開発時は GITHUB_TOKEN が未設定のため、通常のファイル I/O のみ使用する。
_GH_TOKEN  = os.environ.get('GITHUB_TOKEN', '')
_GH_REPO   = os.environ.get('GITHUB_REPO', 'kim777fk-max/mailmaga')
_GH_BRANCH = os.environ.get('GITHUB_DATA_BRANCH', 'main')
_GH_PREFIX = 'data'          # リポジトリ内のデータフォルダ
_USE_GITHUB = bool(_GH_TOKEN and os.environ.get('RENDER'))  # Render.com 上のみ有効

def _gh_headers():
    return {'Authorization': f'token {_GH_TOKEN}',
            'Accept': 'application/vnd.github.v3+json'}

def _gh_read(filename):
    """GitHub から JSON ファイルを読み込む。(data, sha) を返す。"""
    url = f'https://api.github.com/repos/{_GH_REPO}/contents/{_GH_PREFIX}/{filename}'
    try:
        r = requests.get(url, headers=_gh_headers(),
                         params={'ref': _GH_BRANCH}, timeout=10)
        if r.status_code == 200:
            body = r.json()
            content = base64.b64decode(body['content']).decode('utf-8')
            return json.loads(content), body['sha']
    except Exception:
        pass
    return None, None

def _gh_write(filename, data, sha=None):
    """GitHub に JSON ファイルを書き込む（自動 commit）。"""
    url = f'https://api.github.com/repos/{_GH_REPO}/contents/{_GH_PREFIX}/{filename}'
    content = base64.b64encode(
        json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
    ).decode('utf-8')
    body = {'message': f'data: update {filename}',
            'content': content,
            'branch':  _GH_BRANCH}
    if sha:
        body['sha'] = sha
    try:
        requests.put(url, headers=_gh_headers(), json=body, timeout=10)
    except Exception:
        pass

DEPARTMENTS = [
    'はじめに',
    '会長挨拶',
    '板診塾',
    '研修部',
    '総務部',
    '地域支援部',
    '事業支援部',
    '国際部',
    '会員部',
    '渉外部',
    'コンプライアンス室',
    '広報部',
    '板橋区簡易型BCP策定支援事業',
    'プロジェクト',
    'その他',
]

# 組版時に専用セクションとして扱う部署（各部活動紹介の外に出す）
SPECIAL_DEPTS = {'はじめに', '会長挨拶'}

STEPS = [
    {'key': 'schedule_mail',     'label': 'スケジュール案内',  'icon': '①', 'date_key': 'schedule_mail',     'has_email': True},
    {'key': 'request_mail',      'label': '原稿依頼',          'icon': '②', 'date_key': 'request_mail',      'has_email': True},
    {'key': 'submissions',       'label': '原稿収集',          'icon': '③', 'date_key': 'deadline',           'has_email': False},
    {'key': 'deadline_reminder', 'label': 'リマインド',        'icon': '④', 'date_key': 'deadline_reminder',  'has_email': True},
    {'key': 'deadline',          'label': '締切',              'icon': '⑤', 'date_key': 'deadline',           'has_email': True},
    {'key': 'content_check',     'label': '内容チェック',      'icon': '⑥', 'date_key': 'review_request',     'has_email': False},
    {'key': 'format_transfer',   'label': 'フォーマット転記',  'icon': '⑦', 'date_key': 'test_distribution',  'has_email': False},
    {'key': 'final_check',       'label': '最終チェック',      'icon': '⑧', 'date_key': 'test_deadline',      'has_email': False},
    {'key': 'publish',           'label': '配信',              'icon': '⑨', 'date_key': 'publish',            'has_email': False},
]


# ─── シンプルパスワード認証 ────────────────────────────────────────────────────
# 環境変数 APP_PASSWORD が設定されている場合のみ認証を有効にする。
# ローカル開発時は未設定のままにしておけばスキップされる。
_APP_PASSWORD = os.environ.get('APP_PASSWORD', '')

from flask import session as flask_session
from datetime import timedelta

app.permanent_session_lifetime = timedelta(hours=12)

@app.before_request
def check_login():
    """パスワード未設定（ローカル）はスルー。設定済みなら /login 以外は認証必須。"""
    if not _APP_PASSWORD:
        return
    if request.endpoint in ('login', 'logout', 'static'):
        return
    if not flask_session.get('logged_in'):
        return redirect(url_for('login', next=request.path))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if not _APP_PASSWORD:
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        if request.form.get('password') == _APP_PASSWORD:
            flask_session.permanent = True
            flask_session['logged_in'] = True
            return redirect(request.args.get('next') or url_for('dashboard'))
        error = 'パスワードが違います'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    flask_session.clear()
    return redirect(url_for('login'))


# ─── Data helpers ────────────────────────────────────────────────────────────

def load_json(filepath, default):
    """
    ローカルファイルから JSON を読み込む。
    クラウド環境（RENDER=true）かつローカルファイルがなければ GitHub から復元する。
    """
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)

    if _USE_GITHUB:
        filename = os.path.basename(filepath)
        data, _ = _gh_read(filename)
        if data is not None:
            # ローカルにキャッシュして次回以降のAPIコールを省く
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return data

    return default() if callable(default) else default

def save_json(filepath, data):
    """
    ローカルに保存し、クラウド環境では GitHub にも同期する。
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    if _USE_GITHUB:
        filename = os.path.basename(filepath)
        _, sha = _gh_read(filename)   # 既存ファイルの SHA を取得（更新に必要）
        _gh_write(filename, data, sha)

def load_cycles():   return load_json(CYCLES_FILE, [])
def save_cycles(c):  save_json(CYCLES_FILE, c)

def load_config():
    defaults = {
        'server_url':    'https://drive.rmc-itabashi.jp/index.php/s/5rX5tfHQep43eZr',
        'contact_email': 'mmp@rmc-itabashi.jp',
        'sender_name':   '木村',
        'sender_email':  'kim777f.k@gmail.com',
    }
    return {**defaults, **load_json(CONFIG_FILE, {})}

def save_config(c): save_json(CONFIG_FILE, c)


# ─── Schedule calculation ─────────────────────────────────────────────────────

def calc_schedule(year, month):
    """配信月・年からスケジュール日程を自動計算する"""
    prev_year  = year  if month > 1 else year - 1
    prev_month = month - 1 if month > 1 else 12

    def fmt(y, m, d):
        last = calendar.monthrange(y, m)[1]
        return date(y, m, min(d, last)).strftime('%Y/%m/%d')

    return {
        'schedule_mail':     fmt(prev_year,  prev_month, 25),
        'request_mail':      fmt(prev_year,  prev_month, 26),
        'deadline_reminder': fmt(year, month, 6),
        'deadline':          fmt(year, month, 7),
        'review_request':    fmt(year, month, 8),
        'review_deadline':   fmt(year, month, 10),
        'test_distribution': fmt(year, month, 11),
        'test_deadline':     fmt(year, month, 13),
        'publish':           fmt(year, month, 15),
    }


# ─── Email templates ──────────────────────────────────────────────────────────

def get_default_templates():
    return {
        'schedule_mail': {
            'label':   'スケジュール案内（内部向け）',
            'to':      '（内部メンバー）',
            'cc':      '',
            'subject': '【広報部】 メルマガ{delivery_month}月',
            'body': (
                '皆様\nお世話になります。\n\n'
                'メルマガは以下のスケジュールで進行します\n\n'
                '{request_mail}　原稿依頼（執行委員/会長）\n'
                '{deadline}　原稿〆切\n'
                '{review_request}　確認依頼（広報部内）\n'
                '{review_deadline}　確認〆切（広報部内）\n'
                '{test_distribution}　テスト配信（執行委員）\n'
                '{test_deadline}　テスト配信確認〆切（執行委員）\n'
                '{publish}　メルマガ発行\n\n'
                'スケジュールはこちらでいければと思います。\n'
                'よろしくお願いいたします。'
            ),
        },
        'request_mail': {
            'label':   '原稿依頼（執行委員・会長宛）',
            'to':      '板診会執行委員会の皆さま\n会長',
            'cc':      '板診会広報部',
            'subject': 'メルマガいたしん vol.{vol} 原稿依頼',
            'body': (
                '板診会執行委員会の皆さま\n会長\nCc:板診会広報部\n\n'
                'いつもお世話になっております。\n'
                '板診会広報部\n{sender_name}です。\n\n'
                '{delivery_month}月号のメルマガ記事寄稿の依頼をさせていただきます。\n'
                '（今月号から、原稿のご提出の方法をXサーバ経由に変更させていただきました）\n\n'
                '【お願い事項】\n'
                '{delivery_year}年{delivery_month}月15日発行の「メルマガいたしん vol.{vol}」につきまして、\n'
                '各部・プロジェクトのリーダーまたはご担当の方に原稿作成をお願いいたします。\n'
                'お忙しいところ恐縮ですが、ご対応のほどよろしくお願い申し上げます。\n\n'
                '【提出方法】\n'
                '以下のサーバにログインの上、原稿をご提出ください。\n'
                '{server_url}\n'
                'PWは別メールでお送りします。\n\n'
                'サーバ内のWordファイルで原稿のご提出をお願いいたします。\n'
                '　※ファイル名の後ろのカッコ内にご担当の部名をご記載ください。\n'
                '　例：メルマガいたしん原稿用テンプレート_（広報部）.docx\n\n'
                '　※原稿記載後は、サーバ内の「原稿提出」フォルダへ保存をお願いいたします。\n'
                '　※保存完了のご連絡は不要です。\n\n'
                '一行20文字で改行される設定となっております。\n'
                '　段落の頭は全角一文字下げ、英数字は基本的に半角にてご記載をお願いいたします。\n\n'
                '字数・字体・行間など、体裁上の編集（エディトリアル）は\n'
                '　事前の許可なく修正させていただく場合があります。あらかじめご了承ください。\n\n'
                '【お問い合わせ】\n'
                '{contact_email}\n'
                'もしくは広報部{sender_name}（{sender_email}）\n\n'
                '【原稿締切】\n'
                '{delivery_year}年{delivery_month}月7日\n\n'
                '【以降の予定】\n'
                '{test_distribution}　テスト配信（執行委員）\n'
                '{test_deadline}　テスト配信確認〆切（執行委員）\n'
                '{publish}　メルマガ発行\n\n'
                '※サーバ内に、掲載内容と前回配信のメルマガも保存しております。必要に応じてご参照ください。\n\n'
                '以上、よろしくお願いいたします。'
            ),
        },
        'deadline_reminder': {
            'label':   'リマインド（〆切前日）',
            'to':      '板診会執行委員会の皆さま\n会長',
            'cc':      '板診会広報部',
            'subject': '【リマインド】メルマガいたしん vol.{vol} 原稿締切は明日です',
            'body': (
                '板診会執行委員会の皆さま\n会長\nCc:板診会広報部\n\n'
                'いつもお世話になっております。\n'
                '板診会広報部 {sender_name}です。\n\n'
                '「メルマガいたしん vol.{vol}」の原稿締切は\n'
                '明日 {deadline} となっております。\n\n'
                'まだご提出いただいていない方は、お早めにご提出をお願いいたします。\n\n'
                '【提出先】\n'
                '{server_url}\n\n'
                'ご不明な点は {contact_email} までお問い合わせください。\n'
                'よろしくお願いいたします。'
            ),
        },
        'deadline': {
            'label':   '締切日メール＋未提出者リマインド',
            'to':      '板診会執行委員会の皆さま\n会長',
            'cc':      '板診会広報部',
            'subject': '【本日締切】メルマガいたしん vol.{vol} 原稿締切日のお知らせ',
            'body': (
                '板診会執行委員会の皆さま\n会長\nCc:板診会広報部\n\n'
                'いつもお世話になっております。\n'
                '板診会広報部 {sender_name}です。\n\n'
                '本日 {deadline} が「メルマガいたしん vol.{vol}」の原稿締切日となっております。\n\n'
                'まだご提出いただいていない方は、本日中にご提出をお願いいたします。\n\n'
                '【提出先】\n'
                '{server_url}\n\n'
                'ご不明な点は {contact_email} までお問い合わせください。\n'
                'よろしくお願いいたします。'
            ),
        },
    }

def load_templates():
    return load_json(TEMPLATES_FILE, get_default_templates)

def render_vars(text, cycle, config):
    if not text:
        return ''
    sched = cycle.get('schedule', {})
    vars = {
        'vol':               cycle.get('vol', ''),
        'delivery_year':     cycle.get('delivery_year', ''),
        'delivery_month':    cycle.get('delivery_month', ''),
        'schedule_mail':     sched.get('schedule_mail', ''),
        'request_mail':      sched.get('request_mail', ''),
        'deadline_reminder': sched.get('deadline_reminder', ''),
        'deadline':          sched.get('deadline', ''),
        'review_request':    sched.get('review_request', ''),
        'review_deadline':   sched.get('review_deadline', ''),
        'test_distribution': sched.get('test_distribution', ''),
        'test_deadline':     sched.get('test_deadline', ''),
        'publish':           sched.get('publish', ''),
        'server_url':        config.get('server_url', ''),
        'contact_email':     config.get('contact_email', ''),
        'sender_name':       config.get('sender_name', ''),
        'sender_email':      config.get('sender_email', ''),
    }
    try:
        return text.format(**vars)
    except (KeyError, ValueError):
        return text


# ─── Article submission scanner ───────────────────────────────────────────────

def scan_submissions(folder_path):
    """ローカルフォルダをスキャンして提出ファイルを返す {dept: [file_info, ...]}"""
    result = {}
    if not folder_path or not os.path.exists(folder_path):
        return result
    try:
        for fname in sorted(os.listdir(folder_path)):
            fpath = os.path.join(folder_path, fname)
            if not os.path.isfile(fpath):
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext not in ('.txt', '.docx', '.doc'):
                continue

            dept = None
            if ext == '.txt':
                # YYYYMMDD_HHMMSS_部署名.txt
                parts = fname[:-4].split('_')
                if len(parts) >= 3:
                    dept = '_'.join(parts[2:])
            else:
                # テンプレート_（部署名）.docx
                m = re.search(r'[（(]([^）)]+)[）)]', fname)
                if m:
                    dept = m.group(1)

            key = dept or fname
            if key not in result:
                result[key] = []
            result[key].append({
                'filename': fname,
                'path':     fpath,
                'size_kb':  round(os.path.getsize(fpath) / 1024, 1),
                'modified': datetime.fromtimestamp(os.path.getmtime(fpath)).strftime('%m/%d %H:%M'),
                'ext':      ext,
            })
    except Exception:
        pass
    return result


# ─── Helpers ──────────────────────────────────────────────────────────────────

def add_progress(cycle):
    completed = sum(
        1 for s in STEPS
        if cycle.get('steps', {}).get(s['key'], {}).get('completed', False)
    )
    total = len(STEPS)
    cycle['progress'] = {
        'completed': completed,
        'total':     total,
        'pct':       int(completed / total * 100) if total else 0,
    }
    return cycle

def get_current_cycle(cycles):
    today = date.today().strftime('%Y/%m/%d')
    for c in sorted(cycles, key=lambda x: (x['delivery_year'], x['delivery_month'])):
        if c['schedule'].get('publish', '') >= today:
            return c
    return cycles[0] if cycles else None

def suggest_next_cycle(cycles):
    today = date.today()
    m, y = today.month, today.year
    # Next odd month after today
    while True:
        m += 1
        if m > 12:
            m = 1
            y += 1
        if m % 2 == 1:
            break
    max_vol = max((c.get('vol', 0) for c in cycles), default=29)
    return y, m, max_vol + 1


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    cycles = load_cycles()
    cycles.sort(key=lambda c: (c['delivery_year'], c['delivery_month']), reverse=True)
    for c in cycles:
        add_progress(c)
    current = get_current_cycle(cycles)
    today   = date.today().strftime('%Y/%m/%d')
    return render_template('dashboard.html', cycles=cycles, current=current,
                           steps=STEPS, today=today)


@app.route('/cycle/new', methods=['GET', 'POST'])
def cycle_new():
    if request.method == 'POST':
        year  = int(request.form['delivery_year'])
        month = int(request.form['delivery_month'])
        vol   = int(request.form['vol'])

        cycle_id = f'{year}-{month:02d}'
        cycles   = load_cycles()

        if any(c['id'] == cycle_id for c in cycles):
            flash(f'{year}年{month}月号はすでに登録されています', 'error')
            return redirect(url_for('cycle_new'))

        new_cycle = {
            'id':             cycle_id,
            'vol':            vol,
            'delivery_year':  year,
            'delivery_month': month,
            'schedule':       calc_schedule(year, month),
            'steps':          {s['key']: {'completed': False, 'completed_at': None} for s in STEPS},
            'submissions_folder': '',
            'notes':          '',
            'created_at':     datetime.now().isoformat(),
        }
        cycles.append(new_cycle)
        save_cycles(cycles)
        return redirect(url_for('cycle_detail', cycle_id=cycle_id))

    cycles = load_cycles()
    sy, sm, sv = suggest_next_cycle(cycles)
    return render_template('cycle_new.html', suggested_year=sy,
                           suggested_month=sm, suggested_vol=sv)


@app.route('/cycle/<cycle_id>')
def cycle_detail(cycle_id):
    cycles = load_cycles()
    cycle  = next((c for c in cycles if c['id'] == cycle_id), None)
    if not cycle:
        flash('指定の号が見つかりません', 'error')
        return redirect(url_for('dashboard'))

    add_progress(cycle)
    config      = load_config()
    today       = date.today().strftime('%Y/%m/%d')
    submissions = scan_submissions(cycle.get('submissions_folder', ''))
    templates   = load_templates()

    # Build email previews for steps that have templates
    email_previews = {}
    for step in STEPS:
        if step['has_email'] and step['key'] in templates:
            tmpl = templates[step['key']]
            email_previews[step['key']] = {
                'subject': render_vars(tmpl.get('subject', ''), cycle, config),
                'to':      render_vars(tmpl.get('to',      ''), cycle, config),
                'cc':      render_vars(tmpl.get('cc',      ''), cycle, config),
            }

    return render_template('cycle_detail.html', cycle=cycle, config=config,
                           steps=STEPS, departments=DEPARTMENTS,
                           submissions=submissions, email_previews=email_previews,
                           today=today)


@app.route('/cycle/<cycle_id>/step/<step_key>/toggle', methods=['POST'])
def toggle_step(cycle_id, step_key):
    cycles = load_cycles()
    cycle  = next((c for c in cycles if c['id'] == cycle_id), None)
    if not cycle:
        return jsonify({'error': 'not found'}), 404
    step = cycle['steps'].get(step_key, {})
    step['completed']    = not step.get('completed', False)
    step['completed_at'] = datetime.now().isoformat() if step['completed'] else None
    cycle['steps'][step_key] = step
    save_cycles(cycles)
    return jsonify({'completed': step['completed']})


@app.route('/cycle/<cycle_id>/update', methods=['POST'])
def cycle_update(cycle_id):
    cycles = load_cycles()
    cycle  = next((c for c in cycles if c['id'] == cycle_id), None)
    if cycle:
        cycle['submissions_folder'] = request.form.get('submissions_folder', '')
        cycle['notes']              = request.form.get('notes', '')
        save_cycles(cycles)
        flash('更新しました', 'success')
    return redirect(url_for('cycle_detail', cycle_id=cycle_id))


@app.route('/cycle/<cycle_id>/email/<step_key>')
def email_compose(cycle_id, step_key):
    cycles = load_cycles()
    cycle  = next((c for c in cycles if c['id'] == cycle_id), None)
    if not cycle:
        return redirect(url_for('dashboard'))

    config    = load_config()
    templates = load_templates()
    tmpl      = templates.get(step_key, {})

    subject  = render_vars(tmpl.get('subject', ''), cycle, config)
    body     = render_vars(tmpl.get('body',    ''), cycle, config)
    to_text  = render_vars(tmpl.get('to',      ''), cycle, config)
    cc_text  = render_vars(tmpl.get('cc',      ''), cycle, config)

    step_label = next((s['label'] for s in STEPS if s['key'] == step_key), step_key)

    # mailto: link (best-effort; long bodies may be truncated by mail clients)
    qs = urllib.parse.urlencode(
        {'subject': subject, 'body': body, 'cc': cc_text},
        quote_via=urllib.parse.quote
    )
    mailto = f'mailto:?{qs}'

    return render_template('email_compose.html', cycle=cycle,
                           step_key=step_key, step_label=step_label,
                           subject=subject, body=body,
                           to_text=to_text, cc_text=cc_text, mailto=mailto,
                           tmpl=tmpl)


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    config    = load_config()
    templates = load_templates()
    if request.method == 'POST':
        config['server_url']    = request.form.get('server_url', '')
        config['contact_email'] = request.form.get('contact_email', '')
        config['sender_name']   = request.form.get('sender_name', '')
        config['sender_email']  = request.form.get('sender_email', '')
        save_config(config)
        flash('設定を保存しました', 'success')
        return redirect(url_for('settings'))
    return render_template('settings.html', config=config,
                           templates=templates, steps=STEPS)


@app.route('/settings/template/<step_key>', methods=['POST'])
def update_template(step_key):
    templates = load_templates()
    if step_key not in templates:
        templates[step_key] = {}
    templates[step_key].update({
        'subject': request.form.get('subject', ''),
        'body':    request.form.get('body',    ''),
        'to':      request.form.get('to',      ''),
        'cc':      request.form.get('cc',      ''),
    })
    save_json(TEMPLATES_FILE, templates)
    flash('テンプレートを保存しました', 'success')
    return redirect(url_for('settings') + f'#tmpl-{step_key}')


# ─── XServer (Nextcloud) ZIP 一括取得連携 ────────────────────────────────────

def _nc_parse_share_url(url):
    """共有URLからトークンとホストを取り出す"""
    m = re.search(r'/s/([^/?#\s]+)', url)
    if not m:
        return None, None
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = f'{parsed.scheme}://{parsed.netloc}'
    return host, m.group(1)

def _nc_decode_text(raw_bytes):
    """バイト列をUTF-8 / Shift-JIS でデコードする"""
    for enc in ('utf-8', 'utf-8-sig', 'shift-jis', 'cp932'):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode('utf-8', errors='replace')

def xserver_fetch_all(share_url, password=''):
    """
    Nextcloud 公開共有リンクにセッション認証してZIPで一括取得し、
    .txt 原稿ファイルをパースして返す。

    戻り値: (articles_list, error_str)
    articles_list = [{filename, dept, body, preview, size_kb, path_in_zip}, ...]
    """
    if not _REQUESTS_OK:
        return None, 'requests ライブラリが未インストールです（pip install requests）'

    host, token = _nc_parse_share_url(share_url)
    if not token:
        return None, 'URLの形式が正しくありません（/s/TOKEN の形式が必要です）'

    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; melmaga-kanri)'})

    try:
        # ── STEP 1: 共有ページを取得して CSRF トークンを得る ──
        r1 = session.get(f'{host}/index.php/s/{token}', timeout=15)
        if r1.status_code != 200:
            return None, f'共有ページにアクセスできません（HTTP {r1.status_code}）'

        m = re.search(r'name="requesttoken"\s+value="([^"]+)"', r1.text)
        if not m:
            # パスワード不要の共有ページ（認証フォームなし）
            rtoken = None
        else:
            rtoken = m.group(1)

        # ── STEP 2: パスワード認証 ──
        if rtoken:
            r2 = session.post(
                f'{host}/index.php/s/{token}/authenticate/showShare',
                data={'requesttoken': rtoken, 'password': password},
                headers={'Referer': f'{host}/index.php/s/{token}'},
                allow_redirects=True,
                timeout=15,
            )
            # 認証後のページに再びパスワードフォームが存在 → パスワード誤り
            if re.search(r'name="requesttoken"\s+value="', r2.text) and \
               'id="password"' in r2.text:
                return None, 'パスワードが違います'

        # ── STEP 3: ZIP一括ダウンロード ──
        r3 = session.get(
            f'{host}/index.php/s/{token}/download',
            timeout=60,
            stream=True,
        )
        if r3.status_code != 200:
            return None, f'ZIPのダウンロードに失敗しました（HTTP {r3.status_code}）'

        content_type = r3.headers.get('Content-Type', '')
        if 'zip' not in content_type and 'octet' not in content_type:
            # テキスト系ならページが返ってきている（認証失敗の可能性）
            return None, 'パスワードが違うか、ダウンロードに失敗しました'

        zip_bytes = r3.content

        # ── STEP 4: ZIPを展開して .txt を読む ──
        articles = []
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except zipfile.BadZipFile:
            return None, 'ZIPファイルの展開に失敗しました'

        dept_order = {d: i for i, d in enumerate(DEPARTMENTS)}

        for entry in zf.namelist():
            # ディレクトリはスキップ
            if entry.endswith('/'):
                continue
            # .txt 以外はスキップ
            if not entry.lower().endswith('.txt'):
                continue

            filename = urllib.parse.unquote(entry.split('/')[-1])
            info = zf.getinfo(entry)
            if info.file_size == 0:
                continue

            raw = zf.read(entry)
            content = _nc_decode_text(raw)
            dept, body = parse_article(content)

            articles.append({
                'filename':    filename,
                'path_in_zip': entry,
                'dept':        dept or filename,
                'body':        body,
                'preview':     body[:80].replace('\n', ' '),
                'size_kb':     round(info.file_size / 1024, 1),
            })

        articles.sort(key=lambda a: dept_order.get(a['dept'], 999))
        return articles, None

    except requests.exceptions.ConnectionError:
        return None, 'サーバーに接続できませんでした。URLを確認してください'
    except requests.exceptions.Timeout:
        return None, 'タイムアウトしました'
    except Exception as e:
        return None, f'エラー: {e}'


@app.route('/api/cycle/<cycle_id>/xserver-save-url', methods=['POST'])
def xserver_save_url(cycle_id):
    """XServer 共有URLをサイクルデータに保存する"""
    cycles = load_cycles()
    cycle  = next((c for c in cycles if c['id'] == cycle_id), None)
    if not cycle:
        return jsonify({'error': 'not found'}), 404
    data = request.get_json()
    cycle['xserver_url'] = data.get('url', '').strip()
    save_json(CYCLES_FILE, cycles)
    return jsonify({'ok': True})


@app.route('/api/cycle/<cycle_id>/xserver-list', methods=['POST'])
def api_xserver_list(cycle_id):
    """XServer からZIPで一括取得してパース済み記事リストを返す"""
    data     = request.get_json()
    url      = data.get('url', '').strip()
    password = data.get('password', '')
    if not url:
        return jsonify({'error': 'URLを入力してください'}), 400

    articles, err = xserver_fetch_all(url, password)
    if err:
        return jsonify({'error': err}), 400

    return jsonify({'articles': articles, 'count': len(articles)})


@app.route('/api/cycle/<cycle_id>/submissions')
def api_submissions(cycle_id):
    cycles = load_cycles()
    cycle  = next((c for c in cycles if c['id'] == cycle_id), None)
    if not cycle:
        return jsonify({'error': 'not found'}), 404
    return jsonify(scan_submissions(cycle.get('submissions_folder', '')))


# ─── Phase 2: 組版ツール ──────────────────────────────────────────────────────

def read_article_file(filepath):
    """テキストファイルを読み込む（UTF-8 → Shift-JIS フォールバック）"""
    for enc in ('utf-8', 'utf-8-sig', 'shift-jis', 'cp932'):
        try:
            with open(filepath, 'r', encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return '（ファイルの読み込みに失敗しました）'

def parse_article(content):
    """
    melmaga.html 出力形式のテキストをパースする。
    形式: 1行目=【部署名】, 空行, 本文
    """
    lines = content.strip().splitlines()
    dept = ''
    body_start = 0
    if lines and lines[0].startswith('【') and lines[0].endswith('】'):
        dept = lines[0][1:-1]
        body_start = 2 if len(lines) > 1 and lines[1] == '' else 1
    body = '\n'.join(lines[body_start:]).strip()
    return dept, body

def load_assemble_articles(cycle):
    """提出フォルダから .txt 原稿を全件読み込み、記事リストを返す"""
    folder = cycle.get('submissions_folder', '')
    submissions = scan_submissions(folder)
    dept_order  = {d: i for i, d in enumerate(DEPARTMENTS)}
    articles = []

    for dept_name, files in submissions.items():
        for f in files:
            if f['ext'] != '.txt':
                continue
            raw     = read_article_file(f['path'])
            parsed_dept, body = parse_article(raw)
            display_dept = parsed_dept or dept_name
            articles.append({
                'id':       f['filename'],
                'filename': f['filename'],
                'dept':     display_dept,
                'body':     body,
                'preview':  body[:80].replace('\n', ' '),
                'modified': f['modified'],
                'size_kb':  f['size_kb'],
            })

    articles.sort(key=lambda a: dept_order.get(a['dept'], 999))
    return articles


@app.route('/cycle/<cycle_id>/assemble')
def assemble(cycle_id):
    cycles = load_cycles()
    cycle  = next((c for c in cycles if c['id'] == cycle_id), None)
    if not cycle:
        flash('見つかりません', 'error')
        return redirect(url_for('dashboard'))

    config   = load_config()
    articles = load_assemble_articles(cycle)
    sep      = '━' * 20

    return render_template('assemble.html', cycle=cycle, config=config,
                           articles=articles, sep=sep)


@app.route('/api/cycle/<cycle_id>/build-newsletter', methods=['POST'])
def build_newsletter_api(cycle_id):
    cycles = load_cycles()
    cycle  = next((c for c in cycles if c['id'] == cycle_id), None)
    if not cycle:
        return jsonify({'error': 'not found'}), 404

    data   = request.get_json()
    order  = data.get('order', [])   # [{dept, body}, ...]
    header = data.get('header', {})

    vol   = header.get('vol',   cycle.get('vol', ''))
    year  = header.get('year',  cycle.get('delivery_year', ''))
    month = header.get('month', cycle.get('delivery_month', ''))
    day   = header.get('day',   '15')

    # フォームから「はじめに」が未提出の場合の代替テキスト
    intro_fallback = header.get('intro_fallback', '').strip()

    SEP_TOP = '〓＝〓＝〓＝〓＝〓＝〓＝〓＝〓＝〓＝〓＝'
    SEP_MID = '=================================='

    # 記事を部署名でマッピング（同一部署が複数ある場合は後者を優先）
    art_map = {}
    for art in order:
        d = art.get('dept', '').strip()
        if d:
            art_map[d] = art.get('body', '').strip()

    P = []   # 最終テキストの行リスト

    # ════════════════════════════════
    # ヘッダーブロック
    # ════════════════════════════════
    P += [
        SEP_TOP,
        '',
        '板診会会員向けメールマガジン',
        '　 ■ メルマガいたしん ■',
        f'　 vol.{vol} {year}年{month}月{day}日',
        '',
        '発行：(一社)板橋中小企業診断士協会広報部',
        'WEB https://rmc-itabashi.jp/',
        'FB https://www.facebook.com/itashinkai/',
        '',
        SEP_TOP,
        '',
        '',
    ]

    # ════════════════════════════════
    # ◆ はじめに
    # ════════════════════════════════
    intro_body = art_map.get('はじめに', intro_fallback) or '（未提出）'
    P += [
        '◆　はじめに　　　---------------------',
        '',
        intro_body,
        '',
        '　　　　　　　　　  　（広報部　木村文彦）',
        '',
        '',
    ]

    # ════════════════════════════════
    # ◆ 会長挨拶
    # ════════════════════════════════
    kaichou_body = art_map.get('会長挨拶', '') or '（未提出）'
    P += [
        '◆　会長挨拶　　　---------------------',
        '',
        kaichou_body,
        '',
        '　　　　　　　　　  　（会長　）',
        '',
        '',
    ]

    # ════════════════════════════════
    # ◆ 各部活動紹介
    # ════════════════════════════════
    P += [
        '◆　各部活動紹介　　　　---------------',
        '',
    ]

    for art in order:
        dept = art.get('dept', '').strip()
        if dept in SPECIAL_DEPTS or not dept:
            continue
        body = art.get('body', '').strip() or '（未提出）'
        P += [
            f'【{dept}】',
            '',
            body,
            '',
            '',
        ]

    # ════════════════════════════════
    # フッターブロック
    # ════════════════════════════════
    P += [
        SEP_MID,
        f'■メルマガいたしんVol.{vol}はいかがでした',
        'でしょうか。',
        '皆様にご活用いただけるよう改善してまいり',
        'たいと思いますので、ぜひ以下よりアンケー',
        'ト回答にご協力ください。',
        '',
        '是非ご意見、ご感想をお聞かせください。',
        'ご質問もお待ちしております。',
        '(所要時間：1-2分)',
        'https://forms.gle/TGdD1f7HGRCpxbjj7',
        '',
        '次回もご期待ください！',
        '',
        '【お問合せ先】mmp@rmc-itabashi.jp',
        '',
        '一般社団法人板橋中小企業診断士協会',
        '会員向けメールマガジン',
        '　　　　　　　「メルマガいたしん」',
        '（奇数月15日発行）',
        '【発行人】　　　会　　長　大東威司',
        '【編集責任者】　広報部長　猿川明',
        '【編集者】　　　広報部　　木村文彦',
        SEP_MID,
    ]

    return jsonify({'text': '\n'.join(P)})


if __name__ == '__main__':
    print('=' * 50)
    print('メルマガいたしん 統合管理ツール')
    print('http://localhost:5001 をブラウザで開いてください')
    print('終了: Ctrl+C')
    print('=' * 50)
    app.run(debug=True, port=5001)
