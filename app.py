from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import json, os, re, urllib.parse
from datetime import datetime, date
import calendar

app = Flask(__name__)
app.secret_key = 'melmaga-kanri-itashin-2026'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

CYCLES_FILE    = os.path.join(DATA_DIR, 'cycles.json')
CONFIG_FILE    = os.path.join(DATA_DIR, 'config.json')
TEMPLATES_FILE = os.path.join(DATA_DIR, 'email_templates.json')

DEPARTMENTS = [
    '会長挨拶', '板診塾', '副会長', '理事長',
    '研究部', 'セミナー部', '広報部',
    '板橋区簡易型BCP策定支援事業', 'プロジェクト', 'その他',
]

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


# ─── Data helpers ────────────────────────────────────────────────────────────

def load_json(filepath, default):
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default() if callable(default) else default

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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

    config = load_config()
    data   = request.get_json()
    order  = data.get('order', [])   # [{id, dept, body}, ...]
    header = data.get('header', {})

    vol   = header.get('vol',   cycle.get('vol', ''))
    year  = header.get('year',  cycle.get('delivery_year', ''))
    month = header.get('month', cycle.get('delivery_month', ''))
    intro = header.get('intro', '').strip()

    sep = '━' * 20
    parts = []

    # ── ヘッダー ──
    parts.append(sep)
    parts.append(f'メルマガいたしん vol.{vol}')
    parts.append(f'{year}年{month}月')
    parts.append(sep)
    parts.append('')

    # ── はじめに（任意） ──
    if intro:
        parts.append(intro)
        parts.append('')
        parts.append(sep)
        parts.append('')

    # ── 各記事 ──
    for art in order:
        dept = art.get('dept', '')
        body = art.get('body', '').strip()
        if not body:
            continue
        parts.append(f'【{dept}】')
        parts.append('')
        parts.append(body)
        parts.append('')
        parts.append(sep)
        parts.append('')

    # ── フッター ──
    contact = config.get('contact_email', '')
    parts.append('配信停止・変更はこちらへご連絡ください。')
    if contact:
        parts.append(contact)
    parts.append(sep)

    newsletter = '\n'.join(parts)
    return jsonify({'text': newsletter})


if __name__ == '__main__':
    print('=' * 50)
    print('メルマガいたしん 統合管理ツール')
    print('http://localhost:5001 をブラウザで開いてください')
    print('終了: Ctrl+C')
    print('=' * 50)
    app.run(debug=True, port=5001)
